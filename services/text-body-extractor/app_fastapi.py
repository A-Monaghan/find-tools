import os
import json
import re
import time
import queue
import threading
import requests
from typing import List, Dict, Any, Optional, Callable
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl
import pandas as pd
from dotenv import load_dotenv
import openai
import httpx
from bs4 import BeautifulSoup
import io
import tempfile

# Neo4j driver for direct graph push
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# Docling imports for hierarchical chunking
try:
    from docling.chunking import HybridChunker
    from docling.document_converter import DocumentConverter
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    print("Warning: Docling not available. Install with: pip install docling transformers torch")

# Try to import DoclingDocument for fallback chunking
try:
    from docling.datamodel.document import DoclingDocument
except ImportError:
    DoclingDocument = None

load_dotenv()

# FastAPI app initialization
app = FastAPI(
    title="Text Body Relationship Extractor",
    description="Extract entities and relationships from text content using OpenRouter LLM",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="templates")

# Default prompts for entity/relationship extraction (customizable via API)
# Stricter prompts improve JSON reliability across models (unified app may send Kimi/Claude etc.)
DEFAULT_SYSTEM_PROMPT = (
    "You are a JSON-only extraction assistant. You must respond with exactly one valid JSON object and nothing else: "
    "no markdown, no code fences, no explanation before or after. Output only the raw JSON."
)
CONTENT_PLACEHOLDER = "__TEXT_TO_ANALYZE__"
EXTRACTION_ENTITY_LABELS = [
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "EVENT",
    "DOCUMENT",
    "CONCEPT",
]
EXTRACTION_RELATIONSHIP_TYPES = [
    "EMPLOYED_BY",
    "OWNED_BY",
    "INVOLVED_IN",
    "LOCATED_IN",
    "MENTIONED_IN",
    "RELATED_TO",
]
# FTM Lite schema entity/relationship types (from ftm_lite_schema.json)
FTM_ENTITY_LABELS = [
    "PERSON", "ORGANIZATION", "COMPANY", "LEGAL_ENTITY", "ADDRESS",
    "DOCUMENT", "EVENT", "CONCEPT",
]
FTM_RELATIONSHIP_TYPES = [
    "OWNERSHIP", "DIRECTORSHIP", "MEMBERSHIP", "ASSOCIATION",
    "LOCATED_AT", "INVOLVED_IN", "MENTIONED_IN", "RELATED_TO",
]
FTM_USER_PROMPT_TEMPLATE = f"""Extract entities and relationships from the text below using the FTM (Follow The Money) schema. Reply with ONLY a single JSON object in this exact shape (no other text, no markdown):
{{
    "entities": [{{"name": "string", "label": "string"}}],
    "relationships": [{{"source": "string", "target": "string", "type": "string"}}]
}}

Rules:
- Use only these entity labels: {", ".join(FTM_ENTITY_LABELS)}.
- Use only these relationship types: {", ".join(FTM_RELATIONSHIP_TYPES)}.
- Map to FTM concepts: Person (individuals), Organization/Company/LegalEntity (corporate structures), Address (locations), Document (records), Event (incidents), Concept (topics).
- Relationships: Ownership (owns/controls), Directorship (directs/manages), Membership (member of), Association (linked), LocatedAt (at address), InvolvedIn (in event), MentionedIn (in document), RelatedTo (general).
- Create relationships only when both source and target appear in the text.
- Prefer specificity; do not output generic placeholders.

Text to analyze:
{CONTENT_PLACEHOLDER}"""
DEFAULT_USER_PROMPT_TEMPLATE = f"""Extract entities and relationships from the text below. Reply with ONLY a single JSON object in this exact shape (no other text, no markdown):
{{
    "entities": [{{"name": "string", "label": "string"}}],
    "relationships": [{{"source": "string", "target": "string", "type": "string"}}]
}}

Rules:
- Use only these entity labels: {", ".join(EXTRACTION_ENTITY_LABELS)}.
- Use only these relationship types: {", ".join(EXTRACTION_RELATIONSHIP_TYPES)}.
- Create relationships only when both source and target appear in the text.
- Prefer specificity; do not output generic placeholders like "entity" or "unknown".

Example:
Input: John Smith works at Acme Corp in London.
Output:
{{
    "entities": [
        {{"name": "John Smith", "label": "PERSON"}},
        {{"name": "Acme Corp", "label": "ORGANIZATION"}},
        {{"name": "London", "label": "LOCATION"}}
    ],
    "relationships": [
        {{"source": "John Smith", "target": "Acme Corp", "type": "EMPLOYED_BY"}},
        {{"source": "Acme Corp", "target": "London", "type": "LOCATED_IN"}}
    ]
}}

Text to analyze:
{CONTENT_PLACEHOLDER}"""

# Pydantic models for request/response
class AnalyzeRequest(BaseModel):
    api_key: Optional[str] = Field(default=None, description="OpenRouter API key (uses OPENROUTER_API_KEY env if not set)")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (when model_type=openai). Uses OPENAI_API_KEY env if not set.")
    model_type: str = Field(default="openrouter", description="Model provider: openrouter, openai, or ollama")
    openrouter_model: Optional[str] = Field(default=None, description="OpenRouter model ID (e.g. openai/gpt-4o-mini). Uses default if not set.")
    openai_model: Optional[str] = Field(default=None, description="OpenAI model (e.g. gpt-4o-mini). Uses default if not set.")
    ollama_model: Optional[str] = Field(default=None, description="Ollama model name (e.g. qwen2.5). Uses default if not set.")
    url: Optional[HttpUrl] = Field(default=None, description="URL to extract content from")
    text: Optional[str] = Field(default=None, description="Direct text input")
    input_mode: str = Field(default="text", description="Input mode: url or text")
    system_prompt: Optional[str] = Field(default=None, description="Optional custom system message (tone/role). If omitted, default is used.")
    user_prompt_template: Optional[str] = Field(default=None, description="Optional custom user prompt. Use __TEXT_TO_ANALYZE__ where content should be inserted.")
    two_pass: Optional[bool] = Field(
        default=None,
        description="Set true for higher quality, false for faster single-pass. If omitted, backend env default is used.",
    )
    extraction_method: Optional[str] = Field(
        default=None,
        description="Extraction mode: default, ftm. Use ftm for FTM Lite schema-guided extraction.",
    )
    chunking_method: Optional[str] = Field(
        default=None,
        description="Chunking mode: auto, docling, sliding, character. Default auto.",
    )

class EntityResponse(BaseModel):
    id: str
    name: str
    label: str

class RelationshipResponse(BaseModel):
    id: str
    source: str
    target: str
    type: str

class AnalyzeResponse(BaseModel):
    success: bool
    data: Dict[str, List]
    extracted_text: Optional[str] = None

class DownloadRequest(BaseModel):
    entities: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]


class PushToNeo4jRequest(BaseModel):
    entities: List[Dict[str, Any]] = Field(..., description="List of {id, name, label}")
    relationships: List[Dict[str, Any]] = Field(..., description="List of {id, source, target, type}")
    neo4j_uri: Optional[str] = Field(default=None, description="Override Neo4j URI (e.g. neo4j+s://xxx.databases.neo4j.io for Aura)")
    neo4j_username: Optional[str] = Field(default=None, description="Override Neo4j username")
    neo4j_password: Optional[str] = Field(default=None, description="Override Neo4j password")

# Configuration
class Config:
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_DEFAULT_MODEL = os.getenv('OPENROUTER_DEFAULT_MODEL', 'openai/gpt-4o-mini')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_DEFAULT_MODEL = os.getenv('OPENAI_DEFAULT_MODEL', 'gpt-4o-mini')
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    DEFAULT_OLLAMA_MODEL = os.getenv('DEFAULT_OLLAMA_MODEL', 'qwen2.5')
    # Docling chunking settings
    DOCLING_MAX_TOKENS = int(os.getenv('DOCLING_MAX_TOKENS', '512'))
    DOCLING_OVERLAP_TOKENS = int(os.getenv('DOCLING_OVERLAP_TOKENS', '50'))
    DOCLING_ENABLED = os.getenv('DOCLING_ENABLED', 'true').lower() == 'true'
    TWO_PASS_DEFAULT = os.getenv('TWO_PASS_DEFAULT', 'true').lower() == 'true'
    MAX_CHUNKS = int(os.getenv('MAX_CHUNKS', '10'))
    # Neo4j connection for direct push
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USERNAME = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')


# Docling Chunking Service
class DoclingChunker:
    """
    Hierarchical chunking using Docling for semantic document splitting.
    Preserves document structure and prevents entity boundary cuts.
    """
    
    def __init__(self, max_tokens: int = None, overlap_tokens: int = None):
        self.max_tokens = max_tokens or Config.DOCLING_MAX_TOKENS
        self.overlap_tokens = overlap_tokens or Config.DOCLING_OVERLAP_TOKENS
        self.chunker = None
        self.tokenizer = None
        self._initialize_chunker()
    
    def _initialize_chunker(self):
        """Initialize the HybridChunker with custom tokenizer for overlap control."""
        # Allow fast mode to disable Docling without uninstalling it.
        if not DOCLING_AVAILABLE or not Config.DOCLING_ENABLED:
            return
        
        try:
            # Use sentence-transformers tokenizer for consistent token counting
            hf_tokenizer = AutoTokenizer.from_pretrained(
                "sentence-transformers/all-MiniLM-L6-v2",
                use_fast=True
            )
            self.tokenizer = HuggingFaceTokenizer(
                tokenizer=hf_tokenizer,
                max_tokens=self.max_tokens
            )
            self.chunker = HybridChunker(
                tokenizer=self.tokenizer,
                merge_peers=True  # Merge small adjacent chunks
            )
        except Exception as e:
            print(f"Failed to initialize Docling chunker: {e}")
            # Fallback: use default HybridChunker without custom tokenizer
            try:
                self.chunker = HybridChunker(merge_peers=True)
            except Exception as e2:
                print(f"Fallback chunker also failed: {e2}")
                self.chunker = None
    
    def chunk_text_with_method(self, text: str, method: Optional[str] = None) -> List[str]:
        """Chunk text using specified method: auto, docling, sliding, character."""
        m = (method or "auto").lower()
        if m == "sliding":
            return self.chunk_sliding_window(text)
        if m == "character":
            return self._fallback_chunk(text)
        if m == "docling":
            if not DOCLING_AVAILABLE or not self.chunker:
                raise Exception("Docling chunking requested but Docling is not available")
            return self._chunk_docling_only(text)
        return self.chunk_text(text)  # auto: use default (Docling or fallback)

    def _chunk_docling_only(self, text: str) -> List[str]:
        """Chunk using Docling only; no fallback."""
        if DoclingDocument is None:
            raise Exception("DoclingDocument not available")
        doc = DoclingDocument(name="extracted")
        doc.add_text(label="section", text=text)
        chunks = list(self.chunker.chunk(dl_doc=doc))
        result = []
        for chunk in chunks:
            try:
                enriched = self.chunker.contextualize(chunk=chunk)
                if enriched and len(enriched.strip()) > 20:
                    result.append(enriched.strip())
            except Exception:
                if hasattr(chunk, 'text') and chunk.text:
                    result.append(chunk.text.strip())
        return result if result else [text]

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into semantic chunks with hierarchical awareness.
        Returns list of chunk strings.
        """
        if not DOCLING_AVAILABLE or not self.chunker:
            # Fallback: simple character-based chunking with overlap
            return self._fallback_chunk(text)
        
        try:
            # Create a minimal document from text for chunking
            if DoclingDocument is not None:
                # Create document with the text as body
                doc = DoclingDocument(name="extracted")
                doc.add_text(label="section", text=text)
            else:
                # Fallback to simple chunking if DoclingDocument not available
                return self._fallback_chunk(text)
            
            # Perform hierarchical chunking
            chunks = list(self.chunker.chunk(dl_doc=doc))
            
            # Extract contextualized text from each chunk
            result = []
            for chunk in chunks:
                try:
                    # Get enriched text with context
                    enriched_text = self.chunker.contextualize(chunk=chunk)
                    if enriched_text and len(enriched_text.strip()) > 20:
                        result.append(enriched_text.strip())
                except Exception as e:
                    # If contextualize fails, use raw text
                    if hasattr(chunk, 'text') and chunk.text:
                        result.append(chunk.text.strip())
            
            if not result:
                return self._fallback_chunk(text)
            
            return result
            
        except Exception as e:
            print(f"Docling chunking failed: {e}")
            return self._fallback_chunk(text)
    
    def _fallback_chunk(self, text: str) -> List[str]:
        """
        Fallback chunking when Docling is unavailable.
        Uses character-based splitting with sentence-aware boundaries.
        """
        max_chars = self.max_tokens * 4  # Rough estimate: 4 chars per token
        overlap_chars = self.overlap_tokens * 4
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            # Find a good end point (end of sentence or max_chars)
            end = min(start + max_chars, text_len)
            
            # Try to break at sentence boundary
            if end < text_len:
                # Look for sentence ending punctuation followed by space
                for i in range(end, max(start + max_chars // 2, start), -1):
                    if i < text_len and text[i-1] in '.!?' and (i == text_len or text[i].isspace()):
                        end = i
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start with overlap
            start = end - overlap_chars if end < text_len else end
            if start <= 0:
                start = end
        
        return chunks if chunks else [text]

    def chunk_sliding_window(self, text: str) -> List[str]:
        """Token-based sliding window chunking (approx 4 chars/token)."""
        max_chars = self.max_tokens * 4
        overlap_chars = self.overlap_tokens * 4
        step = max(1, max_chars - overlap_chars)
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += step
        return chunks if chunks else [text]
    
    def chunk_url(self, url: str) -> List[str]:
        """
        Convert URL to document and chunk hierarchically.
        Returns list of chunk strings with document structure preserved.
        """
        if not DOCLING_AVAILABLE:
            # Fallback: extract text then chunk
            return self._fallback_chunk_url(url)
        
        try:
            # Use Docling's DocumentConverter for proper HTML parsing
            converter = DocumentConverter()
            result = converter.convert(url)
            
            if not result or not result.document:
                return self._fallback_chunk_url(url)
            
            # Perform hierarchical chunking on the document
            chunks = list(self.chunker.chunk(dl_doc=result.document))
            
            # Extract contextualized text
            result_texts = []
            for chunk in chunks:
                try:
                    enriched_text = self.chunker.contextualize(chunk=chunk)
                    if enriched_text and len(enriched_text.strip()) > 20:
                        result_texts.append(enriched_text.strip())
                except Exception:
                    if hasattr(chunk, 'text') and chunk.text:
                        result_texts.append(chunk.text.strip())
            
            return result_texts if result_texts else self._fallback_chunk_url(url)
            
        except Exception as e:
            print(f"Docling URL chunking failed: {e}")
            return self._fallback_chunk_url(url)
    
    def _fallback_chunk_url(self, url: str) -> List[str]:
        """Fallback: extract text via existing method then chunk."""
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.0'
            }
            # Prefer bypassing env proxy settings, but fall back for managed SSL/cert setups.
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    resp = session.get(url, headers=headers, timeout=15)
            except requests.exceptions.SSLError:
                # Last-resort fallback for environments missing local CA bundles.
                resp = requests.get(url, headers=headers, timeout=15, verify=False)
            soup = BeautifulSoup(resp.content, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            return self.chunk_text(text)
        except Exception as e:
            print(f"Fallback URL chunking failed: {e}")
            return [f"Failed to extract content from {url}"]


# Data models
class Entity:
    def __init__(self, id: str, name: str, label: str):
        self.id = id
        self.name = name
        self.label = label
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'label': self.label
        }

class Relationship:
    def __init__(self, id: str, source: str, target: str, type: str):
        self.id = id
        self.source = source
        self.target = target
        self.type = type
    
    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'target': self.target,
            'type': self.type
        }

class RawEntity:
    def __init__(self, name: str, label: str):
        self.name = name
        self.label = label

class RawRelationship:
    def __init__(self, source: str, target: str, type: str):
        self.source = source
        self.target = target
        self.type = type

# LLM Service Classes
class LLMService:
    def __init__(
        self,
        api_key: str = None,
        openai_api_key: str = None,
        openrouter_model: str = None,
        openai_model: str = None,
        model_type: str = "openrouter",
        ollama_model: str = None,
    ):
        self.api_key = api_key
        self.openai_api_key = openai_api_key or Config.OPENAI_API_KEY
        self.model_type = (model_type or "openrouter").lower()
        self.openrouter_model = openrouter_model or Config.OPENROUTER_DEFAULT_MODEL
        self.openai_model = openai_model or Config.OPENAI_DEFAULT_MODEL
        self.ollama_model = ollama_model or Config.DEFAULT_OLLAMA_MODEL
    
    def extract_text_from_url(self, url: str) -> str:
        """Extract main text content from a URL using parallel extraction and intelligent merging"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Bypass proxy: corporate proxies often block news/investigative sites (e.g. occrp.org)
            # Prefer bypassing env proxy settings, but fall back for managed SSL/cert setups.
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get(url, headers=headers, timeout=15)
            except requests.exceptions.SSLError:
                # Last-resort fallback for environments missing local CA bundles.
                response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            html_content = response.content
            
            # --- PARALLEL EXTRACTION ---
            extraction_results = {}
            
            # 1. Try newspaper3k
            try:
                import newspaper
                article = newspaper.Article(url)
                article.download()
                article.parse()
                if article.text and len(article.text.strip()) > 50:
                    extraction_results['newspaper3k'] = self._clean_text(article.text)
            except Exception as e:
                print(f"Newspaper3k extraction failed: {e}")
            
            # 2. Try trafilatura
            try:
                import trafilatura
                extracted = trafilatura.extract(html_content, include_comments=False, include_tables=False)
                if extracted and len(extracted.strip()) > 50:
                    extraction_results['trafilatura'] = self._clean_text(extracted)
            except Exception as e:
                print(f"Trafilatura extraction failed: {e}")
            
            # 3. Try BeautifulSoup paragraph combination
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove unwanted elements
                unwanted_tags = [
                    'script', 'style', 'noscript', 'iframe', 'embed', 'object', 'applet',
                    'form', 'button', 'input', 'select', 'textarea', 'meta', 'link', 'title', 'head'
                ]
                for tag in unwanted_tags:
                    for element in soup.find_all(tag):
                        element.decompose()

                # Combine all <p> tags in reading order
                paragraphs = []
                for p in soup.find_all('p'):
                    text = p.get_text(separator=' ', strip=True)
                    if len(text) > 30 and not any(
                        kw in text.lower() for kw in [
                            'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 'sign up', 'login', 
                            'advertisement', 'ad', 'footer', 'header', 'copyright', 'all rights reserved', 
                            'share', 'comment', 'related', 'recommended', 'popular', 'trending', 'newsletter', 
                            'disclaimer', 'contact', 'home', 'about']
                    ):
                        paragraphs.append(text)
                
                # Add <div> and <section> blocks with enough text
                for tag in soup.find_all(['div', 'section']):
                    text = tag.get_text(separator=' ', strip=True)
                    if len(text) > 100 and not any(
                        kw in text.lower() for kw in [
                            'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 'sign up', 'login', 
                            'advertisement', 'ad', 'footer', 'header', 'copyright', 'all rights reserved', 
                            'share', 'comment', 'related', 'recommended', 'popular', 'trending', 'newsletter', 
                            'disclaimer', 'contact', 'home', 'about']
                    ):
                        paragraphs.append(text)
                
                combined_text = '\n'.join(paragraphs)
                if len(combined_text.strip()) > 50:
                    extraction_results['beautifulsoup'] = self._clean_text(combined_text)
            except Exception as e:
                print(f"BeautifulSoup extraction failed: {e}")
            
            # --- INTELLIGENT MERGING ---
            if not extraction_results:
                raise Exception("All extraction methods failed")
            
            # If we have multiple results, merge them intelligently
            if len(extraction_results) > 1:
                return self._merge_extraction_results(extraction_results)
            else:
                # Return the single result
                return list(extraction_results.values())[0]
            
        except Exception as e:
            raise Exception(f"Failed to extract content from URL: {str(e)}")
    
    def _merge_extraction_results(self, results: dict) -> str:
        """Intelligently merge multiple extraction results"""
        # Sort by length (longer is usually better)
        sorted_results = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Use the longest result as base
        base_text = sorted_results[0][1]
        base_method = sorted_results[0][0]
        
        print(f"Using {base_method} as base (length: {len(base_text)})")
        
        # For each other result, find differences and evaluate if they're relevant
        merged_text = base_text
        
        for method, text in sorted_results[1:]:
            print(f"Analyzing differences from {method} (length: {len(text)})")
            
            # Find text that's in the other result but not in base
            differences = self._find_text_differences(base_text, text)
            
            # Evaluate which differences are relevant
            relevant_differences = self._evaluate_differences(differences, base_text)
            
            # Insert relevant text into the merged result
            if relevant_differences:
                merged_text = self._insert_relevant_text(merged_text, relevant_differences)
        
        return merged_text
    
    def _find_text_differences(self, base_text: str, other_text: str) -> list:
        """Find text blocks that are in other_text but not in base_text"""
        def split_into_sentences(text):
            # Simple sentence splitting
            sentences = re.split(r'[.!?]+', text)
            return [s.strip() for s in sentences if len(s.strip()) > 20]
        
        base_sentences = set(split_into_sentences(base_text))
        other_sentences = split_into_sentences(other_text)
        
        differences = []
        for sentence in other_sentences:
            if sentence not in base_sentences:
                # Check if it's not just a minor variation
                is_different = True
                for base_sent in base_sentences:
                    if len(sentence) > 50 and len(base_sent) > 50:
                        # Check for high similarity
                        common_words = set(sentence.lower().split()) & set(base_sent.lower().split())
                        if len(common_words) / max(len(sentence.split()), len(base_sent.split())) > 0.8:
                            is_different = False
                            break
                
                if is_different:
                    differences.append(sentence)
        
        return differences
    
    def _evaluate_differences(self, differences: list, base_text: str) -> list:
        """Evaluate which differences are relevant and should be included"""
        relevant_differences = []
        
        for diff in differences:
            # Skip very short differences
            if len(diff) < 30:
                continue
            
            # Skip common boilerplate
            skip_keywords = [
                'cookie', 'privacy', 'terms', 'navigation', 'menu', 'subscribe', 
                'sign up', 'login', 'advertisement', 'ad', 'footer', 'header', 
                'copyright', 'all rights reserved', 'share', 'comment', 'related', 
                'recommended', 'popular', 'trending', 'newsletter', 'disclaimer', 
                'contact', 'home', 'about', 'read more', 'continue reading'
            ]
            
            if any(keyword in diff.lower() for keyword in skip_keywords):
                continue
            
            # Check if it contains meaningful content (names, dates, numbers, etc.)
            meaningful_patterns = [
                r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',  # Names
                r'\b\d{4}\b',  # Years
                r'\b\d+%\b',  # Percentages
                r'\$\d+',  # Money
                r'\b[A-Z]{2,}\b',  # Acronyms
            ]
            
            has_meaningful_content = any(re.search(pattern, diff) for pattern in meaningful_patterns)
            
            if has_meaningful_content or len(diff) > 100:
                relevant_differences.append(diff)
        
        return relevant_differences
    
    def _insert_relevant_text(self, base_text: str, relevant_differences: list) -> str:
        """Insert relevant differences into the base text"""
        if not relevant_differences:
            return base_text
        
        # Add differences at the end, separated by double newlines
        return base_text + '\n\n' + '\n\n'.join(relevant_differences)
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common web artifacts
        text = re.sub(r'\[.*?\]', '', text)  # Remove square brackets
        text = re.sub(r'\(.*?\)', '', text)  # Remove parentheses
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)  # Remove URLs
        
        # Remove multiple periods
        text = re.sub(r'\.{2,}', '.', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text

    def _extract_entities_pass(
        self, text: str, system: str,
        entity_labels: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Pass 1: extract entities only using constrained labels."""
        labels = entity_labels or EXTRACTION_ENTITY_LABELS
        user_message = f"""Extract entities from the text below.
Return ONLY valid JSON in this exact shape:
{{
  "entities": [{{"name": "string", "label": "string"}}]
}}

Rules:
- Use only these labels: {", ".join(labels)}.
- Keep canonical names where possible.
- No explanations, no markdown, no extra keys.

Text to analyze:
{text[:8000]}"""
        result = self._extract_with_selected_provider(text, system, user_message)
        raw_entities = result.get("entities", []) if isinstance(result, dict) else []
        entities: List[Dict[str, str]] = []
        for entity in raw_entities:
            if not isinstance(entity, dict):
                continue
            name = (entity.get("name") or "").strip()
            label = (entity.get("label") or "ENTITY").strip().upper().replace(" ", "_")
            if not name:
                continue
            entities.append({"name": name, "label": label})
        return entities

    def _extract_relationships_pass(
        self, text: str, entities: List[Dict[str, str]], system: str,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Pass 2: extract relationships constrained to entity names from pass 1."""
        if not entities:
            return []
        rel_types = relationship_types or EXTRACTION_RELATIONSHIP_TYPES
        entity_names = [e["name"] for e in entities if isinstance(e, dict) and e.get("name")]
        if not entity_names:
            return []

        user_message = f"""Extract relationships from the text below using ONLY these entity names:
{json.dumps(entity_names, ensure_ascii=True)}

Return ONLY valid JSON in this exact shape:
{{
  "relationships": [{{"source": "string", "target": "string", "type": "string"}}]
}}

Rules:
- source and target must be names from the provided list.
- Use only these relationship types: {", ".join(rel_types)}.
- No explanations, no markdown, no extra keys.

Text to analyze:
{text[:8000]}"""
        result = self._extract_with_selected_provider(text, system, user_message)
        raw_relationships = result.get("relationships", []) if isinstance(result, dict) else []
        valid_names = {name.lower() for name in entity_names}

        relationships: List[Dict[str, str]] = []
        for rel in raw_relationships:
            if not isinstance(rel, dict):
                continue
            source = (rel.get("source") or "").strip()
            target = (rel.get("target") or "").strip()
            rel_type = (rel.get("type") or "").strip().upper().replace(" ", "_")
            if not source or not target or not rel_type:
                continue
            if source.lower() not in valid_names or target.lower() not in valid_names:
                continue
            relationships.append({"source": source, "target": target, "type": rel_type})
        return relationships

    def _extract_two_pass(
        self, text: str, system: str,
        entity_labels: Optional[List[str]] = None,
        relationship_types: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """Run entities pass then constrained relationships pass."""
        entities = self._extract_entities_pass(text, system, entity_labels=entity_labels)
        relationships = self._extract_relationships_pass(
            text, entities, system, relationship_types=relationship_types
        )
        return {"entities": entities, "relationships": relationships}
    
    def extract_graph_data(
        self,
        text: str,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        is_url: bool = False,
        two_pass: bool = True,
        extraction_method: Optional[str] = None,
        chunking_method: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, List]:
        """
        Extract entities and relationships from text using hierarchical chunking.
        
        Splits text into semantic chunks (using Docling if available), extracts
        from each chunk, then merges/deduplicates results.
        
        Optional system_prompt and user_prompt_template override defaults.
        User template should contain __TEXT_TO_ANALYZE__ where content is inserted.
        """
        system = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip() or DEFAULT_SYSTEM_PROMPT
        if user_prompt_template and user_prompt_template.strip():
            template = user_prompt_template.strip()
        elif (extraction_method or "").lower() == "ftm":
            template = FTM_USER_PROMPT_TEMPLATE
        else:
            template = DEFAULT_USER_PROMPT_TEMPLATE
        
        # Initialize chunker
        chunker = DoclingChunker()
        
        # Get chunks - use URL-specific chunking if appropriate, else text chunking
        chunk_method = (chunking_method or "auto").lower()
        if is_url and len(text) < 1000 and text.startswith('http'):
            try:
                chunks = chunker.chunk_url(text)
            except Exception:
                chunks = chunker.chunk_text_with_method(text, chunk_method)
        else:
            chunks = chunker.chunk_text_with_method(text, chunk_method)
        
        # If custom template is provided, keep single-pass behaviour so caller intent is preserved.
        use_two_pass = two_pass and not bool(user_prompt_template)

        # If text is short enough, process as single chunk.
        if len(chunks) == 1 or len(text) <= 4000:
            if use_two_pass:
                ee_labels = FTM_ENTITY_LABELS if (extraction_method or "").lower() == "ftm" else None
                rel_types = FTM_RELATIONSHIP_TYPES if (extraction_method or "").lower() == "ftm" else None
                return self._extract_two_pass(text, system, entity_labels=ee_labels, relationship_types=rel_types)
            content = text[:8000]
            user_message = template.replace(CONTENT_PLACEHOLDER, content)
            return self._extract_with_selected_provider(text, system, user_message)
        
        # Process multiple chunks and aggregate results
        total = min(len(chunks), max(1, Config.MAX_CHUNKS))
        if progress_callback:
            progress_callback({"stage": "start", "total": total, "message": f"Processing {total} chunks for entity extraction..."})
        print(f"Processing {len(chunks)} chunks for entity extraction...")
        all_entities = []
        all_relationships = []
        
        # Process chunks with rate limiting consideration
        # Bound LLM calls to keep latency predictable.
        max_chunks = min(len(chunks), max(1, Config.MAX_CHUNKS))
        
        for i, chunk in enumerate(chunks[:max_chunks]):
            try:
                # Skip very small chunks
                if len(chunk.strip()) < 100:
                    continue

                # Pace requests to avoid rate-limiting on multi-chunk extraction
                if i > 0:
                    time.sleep(0.5)

                entities = []
                relationships = []

                if use_two_pass:
                    ee_labels = FTM_ENTITY_LABELS if (extraction_method or "").lower() == "ftm" else None
                    rel_types = FTM_RELATIONSHIP_TYPES if (extraction_method or "").lower() == "ftm" else None
                    result = self._extract_two_pass(chunk, system, entity_labels=ee_labels, relationship_types=rel_types)
                else:
                    content = chunk[:8000]  # Stay within token limits
                    user_message = template.replace(CONTENT_PLACEHOLDER, content)
                    result = self._extract_with_selected_provider(chunk, system, user_message)

                if result and isinstance(result, dict):
                    entities = result.get('entities', []) or []
                    relationships = result.get('relationships', []) or []
                    if entities:
                        all_entities.extend(entities)
                    if relationships:
                        all_relationships.extend(relationships)
                
                msg = f"  Chunk {i+1}/{max_chunks}: extracted {len(entities)} entities, {len(relationships)} relationships"
                print(msg)
                if progress_callback:
                    progress_callback({"chunk": i + 1, "total": max_chunks, "entities": len(entities), "relationships": len(relationships), "message": msg.strip()})
                
            except Exception as e:
                msg = f"  Chunk {i+1}/{max_chunks} failed: {e}"
                print(msg)
                if progress_callback:
                    progress_callback({"message": msg.strip()})
                continue
        
        # Deduplicate and merge results
        processed_result = self._merge_chunk_results(all_entities, all_relationships)
        msg = f"Final result: {len(processed_result['entities'])} unique entities, {len(processed_result['relationships'])} unique relationships"
        print(msg)
        if progress_callback:
            progress_callback({"stage": "complete", "entities": len(processed_result["entities"]), "relationships": len(processed_result["relationships"]), "message": msg})
        
        return processed_result
    
    def _merge_chunk_results(self, entities: List[Dict], relationships: List[Dict]) -> Dict[str, List]:
        """
        Deduplicate and merge entities and relationships from multiple chunks.
        Uses name-based deduplication for entities and (source, target, type) for relationships.
        """
        # Deduplicate entities by name (case-insensitive)
        entity_map = {}
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = entity.get('name', '').strip()
            if not name:
                continue
            
            key = name.lower()
            if key not in entity_map:
                entity_map[key] = {
                    'name': name,
                    'label': entity.get('label', 'ENTITY')
                }
            else:
                # Keep more specific label if current one is generic
                existing_label = entity_map[key]['label']
                new_label = entity.get('label', 'ENTITY')
                if existing_label.upper() in ['ENTITY', 'OTHER', 'UNKNOWN'] and new_label.upper() not in ['ENTITY', 'OTHER', 'UNKNOWN']:
                    entity_map[key]['label'] = new_label
        
        # Backfill missing entities from relationships so valid cross-chunk links are not dropped.
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            source_name = rel.get('source', '').strip()
            target_name = rel.get('target', '').strip()
            for name in (source_name, target_name):
                if not name:
                    continue
                key = name.lower()
                if key not in entity_map:
                    entity_map[key] = {'name': name, 'label': 'ENTITY'}

        # Deduplicate relationships by (source, target, type)
        rel_map = {}
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            source = rel.get('source', '').strip()
            target = rel.get('target', '').strip()
            rel_type = rel.get('type', '').strip().upper().replace(' ', '_')
            
            if not source or not target or not rel_type:
                continue
            
            # Normalize entity names for matching
            source_key = source.lower()
            target_key = target.lower()
            
            # Keep only relationships whose endpoints are known after backfilling.
            if source_key not in entity_map or target_key not in entity_map:
                continue
            
            rel_key = (source_key, target_key, rel_type)
            if rel_key not in rel_map:
                rel_map[rel_key] = {
                    'source': source,
                    'target': target,
                    'type': rel_type
                }
        
        return {
            'entities': list(entity_map.values()),
            'relationships': list(rel_map.values())
        }
    
    def _extract_with_openrouter(self, text: str, system: str, user_message: str) -> Dict[str, List]:
        """Extract using OpenRouter (OpenAI-compatible API; any model via openrouter.ai)"""
        try:
            api_key = self.api_key if self.api_key else Config.OPENROUTER_API_KEY
            if not api_key:
                raise Exception("OpenRouter API key is required. Set OPENROUTER_API_KEY or pass api_key.")
            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                http_client=httpx.Client(),
            )

            # Retry with exponential backoff — empty responses are usually transient
            # (rate-limit, model overload, cold start).
            max_retries = 3
            last_error = None

            for attempt in range(max_retries):
                try:
                    try:
                        response = client.chat.completions.create(
                            model=self.openrouter_model,
                            messages=[
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_message}
                            ],
                            temperature=0.1,
                            max_tokens=2000,
                            response_format={"type": "json_object"},
                        )
                    except Exception:
                        response = client.chat.completions.create(
                            model=self.openrouter_model,
                            messages=[
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_message}
                            ],
                            temperature=0.1,
                            max_tokens=2000,
                        )

                    choice = response.choices[0] if response.choices else None
                    finish_reason = getattr(choice, "finish_reason", "unknown") if choice else "no_choices"
                    result_text = (choice.message.content or "").strip() if choice else ""

                    if not result_text:
                        print(f"  [OpenRouter] attempt {attempt+1}/{max_retries}: empty response "
                              f"(model={self.openrouter_model}, finish_reason={finish_reason})")
                        last_error = Exception(
                            f"Empty response from {self.openrouter_model} (finish_reason={finish_reason})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        raise last_error

                    # Successful non-empty response — break retry loop
                    break

                except openai.RateLimitError as e:
                    print(f"  [OpenRouter] attempt {attempt+1}/{max_retries}: rate limited")
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    raise
                except openai.APIStatusError as e:
                    if e.status_code in (502, 503, 529):
                        print(f"  [OpenRouter] attempt {attempt+1}/{max_retries}: {e.status_code} overloaded")
                        last_error = e
                        if attempt < max_retries - 1:
                            time.sleep(2 ** (attempt + 1))
                            continue
                    raise

            # Parse the response
            candidates = [
                result_text,
                self._extract_markdown_json(result_text),
                self._extract_json_block(result_text),
                self._fix_json_issues(result_text),
            ]
            for raw in candidates:
                if not raw:
                    continue
                try:
                    result = json.loads(raw)
                    if isinstance(result, dict) and ("entities" in result or "relationships" in result):
                        return result
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue

            manual_result = self._extract_manual_from_response(result_text)
            if manual_result:
                return manual_result

            preview = result_text[:300].replace("\n", " ")
            raise Exception(
                f"Failed to parse OpenRouter response as JSON. Preview: {preview}..."
            )
        except Exception as e:
            _debug_log("app_fastapi.py:_extract_with_openrouter", "exception", {"error": str(e)}, "H1")
            raise Exception(f"OpenRouter extraction failed: {str(e)}")

    def _extract_with_ollama(self, text: str, system: str, user_message: str) -> Dict[str, List]:
        """Extract using local Ollama with JSON output."""
        prompt = f"{system}\n\n{user_message}"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        try:
            response = requests.post(
                f"{Config.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            raw_text = (data.get("response") or "").strip()
            if not raw_text:
                raise Exception("Ollama returned empty response")
            parsed = json.loads(raw_text)
            if not isinstance(parsed, dict):
                raise Exception("Ollama response is not a JSON object")
            return {
                "entities": parsed.get("entities", []) or [],
                "relationships": parsed.get("relationships", []) or [],
            }
        except Exception as e:
            raise Exception(f"Ollama extraction failed: {str(e)}")

    def _extract_with_openai(self, text: str, system: str, user_message: str) -> Dict[str, List]:
        """Extract using OpenAI API directly (api.openai.com)."""
        api_key = self.openai_api_key
        if not api_key or api_key == 'your_openai_api_key_here':
            raise Exception("OpenAI API key is required. Set OPENAI_API_KEY or pass openai_api_key.")
        client = openai.OpenAI(api_key=api_key, http_client=httpx.Client())
        try:
            response = client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
        except Exception:
            response = client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1,
                max_tokens=2000,
            )
        choice = response.choices[0] if response.choices else None
        result_text = (choice.message.content or "").strip() if choice else ""
        if not result_text:
            raise Exception(f"OpenAI returned empty response (model={self.openai_model})")
        for raw in [result_text, self._extract_markdown_json(result_text), self._extract_json_block(result_text)]:
            if not raw:
                continue
            try:
                result = json.loads(raw)
                if isinstance(result, dict) and ("entities" in result or "relationships" in result):
                    return result
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue
        manual = self._extract_manual_from_response(result_text)
        if manual:
            return manual
        raise Exception(f"Failed to parse OpenAI response as JSON. Preview: {result_text[:200]}...")

    def _extract_with_selected_provider(self, text: str, system: str, user_message: str) -> Dict[str, List]:
        """Dispatch extraction to the configured provider."""
        if self.model_type == "ollama":
            return self._extract_with_ollama(text, system, user_message)
        if self.model_type == "openai":
            return self._extract_with_openai(text, system, user_message)
        return self._extract_with_openrouter(text, system, user_message)
    
    def _extract_markdown_json(self, text: str) -> str:
        """Extract content from ```json ... ``` or ``` ... ``` anywhere in the response."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_json_block(self, text: str) -> str:
        """Extract a JSON object from markdown or surrounding text."""
        # Strip markdown code fence at start/end if present
        stripped = text.strip()
        for prefix in ("```json", "```JSON", "```"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].lstrip()
                if stripped.endswith("```"):
                    stripped = stripped[:-3].rstrip()
                break
        # Find first balanced { ... }
        start = stripped.find("{")
        if start == -1:
            return ""
        depth = 0
        in_string = None
        escape = False
        for i in range(start, len(stripped)):
            c = stripped[i]
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if in_string:
                if c == in_string:
                    in_string = None
                continue
            if c in ('"', "'"):
                in_string = c
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return stripped[start : i + 1]
        return ""

    def _fix_json_issues(self, json_str: str) -> str:
        """Fix common JSON formatting issues (do not break valid JSON)."""
        s = self._extract_json_block(json_str) or json_str
        # Remove markdown if still present
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
        # Fix trailing commas
        s = re.sub(r",\s*}", "}", s)
        s = re.sub(r",\s*]", "]", s)
        return s.strip()
    
    def _extract_manual_from_response(self, response_text: str) -> Dict[str, List]:
        """Manually extract entities and relationships from response text when JSON parsing fails"""
        entities = []
        relationships = []
        
        # Look for entity patterns
        entity_patterns = [
            r'"name":\s*"([^"]+)"[^}]*"label":\s*"([^"]+)"',
            r'name["\s]*:["\s]*([^",\n]+)["\s,]*label["\s]*:["\s]*([^",\n]+)',
            r'Entity:\s*([^,\n]+)[^,\n]*Type:\s*([^,\n]+)',
        ]
        
        for pattern in entity_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if len(match) >= 2:
                    entities.append({
                        'name': match[0].strip(),
                        'label': match[1].strip()
                    })
        
        # Look for relationship patterns
        rel_patterns = [
            r'"source":\s*"([^"]+)"[^}]*"target":\s*"([^"]+)"[^}]*"type":\s*"([^"]+)"',
            r'source["\s]*:["\s]*([^",\n]+)["\s,]*target["\s]*:["\s]*([^",\n]+)["\s,]*type["\s]*:["\s]*([^",\n]+)',
            r'([^,\n]+)\s*->\s*([^,\n]+)\s*:\s*([^,\n]+)',
        ]
        
        for pattern in rel_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if len(match) >= 3:
                    relationships.append({
                        'source': match[0].strip(),
                        'target': match[1].strip(),
                        'type': match[2].strip().upper().replace(' ', '_')
                    })
        
        if entities or relationships:
            print(f"Manual extraction found {len(entities)} entities and {len(relationships)} relationships")
            return {
                'entities': entities,
                'relationships': relationships
            }
        
        return None

# Utility functions
def normalize_id(name: str) -> str:
    """Normalize entity name to ID format"""
    return re.sub(r'\s+', '_', name.lower())

# #region agent log
def _debug_log(location: str, message: str, data: dict, hypothesis_id: str = ""):
    import json as _json
    try:
        with open("/Users/andymonaghan/Projects/Data Science /OCCRP/.cursor/debug.log", "a") as _f:
            _f.write(_json.dumps({"location": location, "message": message, "data": data, "hypothesisId": hypothesis_id, "timestamp": __import__("time").time() * 1000}) + "\n")
    except Exception:
        pass
# #endregion

def process_graph_results(raw_data: Dict[str, List]) -> Dict[str, List]:
    """Process raw graph data and normalize IDs"""
    # #region agent log
    _debug_log("app_fastapi.py:process_graph_results", "entry raw_data", {"is_none": raw_data is None, "type": type(raw_data).__name__, "keys": list(raw_data.keys()) if isinstance(raw_data, dict) else "n/a", "entities_len": len(raw_data.get("entities", [])) if isinstance(raw_data, dict) else 0, "relationships_len": len(raw_data.get("relationships", [])) if isinstance(raw_data, dict) else 0}, "H3")
    # #endregion
    entity_map = {}
    entities = []
    relationships = []
    
    # Process entities
    for raw_entity in raw_data.get('entities', []):
        # #region agent log
        _debug_log("app_fastapi.py:process_graph_results", "entity item", {"is_dict": isinstance(raw_entity, dict), "keys": list(raw_entity.keys()) if isinstance(raw_entity, dict) else "n/a", "has_name": raw_entity.get("name") is not None if isinstance(raw_entity, dict) else False, "has_label": raw_entity.get("label") is not None if isinstance(raw_entity, dict) else False}, "H4")
        # #endregion
        entity_id = normalize_id(raw_entity['name'])
        if entity_id not in entity_map:
            entity = Entity(entity_id, raw_entity['name'], raw_entity['label'])
            entity_map[entity_id] = entity
            entities.append(entity)
    
    # Process relationships
    relationship_map = {}
    for raw_rel in raw_data.get('relationships', []):
        # #region agent log
        _debug_log("app_fastapi.py:process_graph_results", "rel item", {"is_dict": isinstance(raw_rel, dict), "keys": list(raw_rel.keys()) if isinstance(raw_rel, dict) else "n/a"}, "H4")
        # #endregion
        source_id = normalize_id(raw_rel['source'])
        target_id = normalize_id(raw_rel['target'])
        
        if source_id in entity_map and target_id in entity_map:
            rel_id = f"{source_id}_{normalize_id(raw_rel['type'])}_{target_id}"
            if rel_id not in relationship_map:
                relationship = Relationship(
                    rel_id, source_id, target_id, 
                    raw_rel['type'].upper().replace(' ', '_')
                )
                relationship_map[rel_id] = relationship
                relationships.append(relationship)
    
    return {
        'entities': [e.to_dict() for e in entities],
        'relationships': [r.to_dict() for r in relationships]
    }

# FastAPI routes
@app.get("/", response_class=HTMLResponse, tags=["Root"])
async def root(request: Request):
    """Root endpoint - returns the web interface"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api", tags=["API"])
async def api_info():
    """API information endpoint"""
    return {
        "message": "Text Body Relationship Extractor API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/api/prompt-defaults", tags=["API"])
async def get_prompt_defaults():
    """Return default system prompt and user prompt template for the extractor.
    Use __TEXT_TO_ANALYZE__ in the user template where content should be inserted."""
    return {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE,
        "content_placeholder": CONTENT_PLACEHOLDER,
    }

@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
def analyze(request: AnalyzeRequest):
    """
    Analyze text or URL content to extract entities and relationships.
    
    - **model_type**: Provider to use (`openrouter` or `ollama`)
    - **api_key**: Optional for OpenRouter. Uses OPENROUTER_API_KEY env if not set.
    - **openrouter_model**: Optional OpenRouter model ID (e.g. openai/gpt-4o-mini).
    - **ollama_model**: Optional Ollama model name (e.g. qwen2.5).
    - **url**: URL to extract content from (when input_mode is 'url')
    - **text**: Direct text input (when input_mode is 'text')
    - **input_mode**: Either 'url' or 'text'
    """
    # #region agent log
    _debug_log("app_fastapi.py:analyze", "entry", {"input_mode": request.input_mode, "has_url": bool(request.url), "text_len": len(request.text or "")}, "H4")
    # #endregion
    try:
        model_type = (request.model_type or "openrouter").lower()
        if model_type not in ("openrouter", "openai", "ollama"):
            raise HTTPException(status_code=400, detail="Invalid model_type. Use 'openrouter', 'openai', or 'ollama'.")

        api_key = request.api_key or Config.OPENROUTER_API_KEY
        openai_api_key = request.openai_api_key or Config.OPENAI_API_KEY
        if model_type == "openrouter" and (not api_key or api_key == 'your_openrouter_api_key_here'):
            raise HTTPException(status_code=400, detail="OpenRouter API key is required. Set OPENROUTER_API_KEY or pass api_key.")
        if model_type == "openai" and (not openai_api_key or openai_api_key == 'your_openai_api_key_here'):
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Set OPENAI_API_KEY or pass openai_api_key.")
        
        llm_service = LLMService(
            api_key=api_key,
            openai_api_key=openai_api_key,
            openrouter_model=request.openrouter_model,
            openai_model=request.openai_model,
            model_type=model_type,
            ollama_model=request.ollama_model,
        )
        
        # Get content to analyze
        if request.input_mode == 'url':
            if not request.url:
                raise HTTPException(status_code=400, detail="Please enter a valid URL")
            
            try:
                content_to_process = llm_service.extract_text_from_url(str(request.url))
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            if not request.text or not request.text.strip():
                raise HTTPException(status_code=400, detail="Please enter text to analyze")
            content_to_process = request.text
        
        # Extract graph data
        try:
            # #region agent log
            _debug_log("app_fastapi.py:analyze", "before extract_graph_data", {"content_len": len(content_to_process)}, "H4")
            # #endregion
            raw_graph_data = llm_service.extract_graph_data(
                content_to_process,
                system_prompt=request.system_prompt,
                user_prompt_template=request.user_prompt_template,
                is_url=(request.input_mode == 'url'),
                two_pass=request.two_pass if request.two_pass is not None else Config.TWO_PASS_DEFAULT,
                extraction_method=request.extraction_method,
                chunking_method=request.chunking_method,
            )
            # #region agent log
            _debug_log("app_fastapi.py:analyze", "raw_graph_data received", {"type": type(raw_graph_data).__name__, "keys": list(raw_graph_data.keys()) if isinstance(raw_graph_data, dict) else "n/a", "entities_len": len(raw_graph_data.get("entities", [])) if isinstance(raw_graph_data, dict) else 0, "relationships_len": len(raw_graph_data.get("relationships", [])) if isinstance(raw_graph_data, dict) else 0}, "H3")
            # #endregion
            processed_data = process_graph_results(raw_graph_data)
            # #region agent log
            _debug_log("app_fastapi.py:analyze", "after process_graph_results", {"entities": len(processed_data.get("entities", [])), "relationships": len(processed_data.get("relationships", [])), "data_keys": list(processed_data.keys())}, "H4")
            # #endregion
            # #region agent log
            _debug_log("app_fastapi.py:analyze", "building AnalyzeResponse", {"data_keys": list(processed_data.keys())}, "H5")
            # #endregion
            return AnalyzeResponse(
                success=True,
                data=processed_data,
                extracted_text=content_to_process if request.input_mode == 'url' else None
            )
            
        except Exception as e:
            # #region agent log
            _debug_log("app_fastapi.py:analyze", "extract exception", {"error": str(e)}, "H4")
            # #endregion
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException:
        raise
    except Exception as e:
        # #region agent log
        _debug_log("app_fastapi.py:analyze", "outer exception", {"error": str(e)}, "H4")
        # #endregion
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


def _analyze_stream_generator(request: AnalyzeRequest):
    """Generator that yields SSE progress events then final result."""
    q = queue.Queue()

    def run_extraction():
        try:
            model_type = (request.model_type or "openrouter").lower()
            api_key = request.api_key or Config.OPENROUTER_API_KEY
            openai_api_key = request.openai_api_key or Config.OPENAI_API_KEY
            if model_type == "openrouter" and (not api_key or api_key == "your_openrouter_api_key_here"):
                q.put(("error", {"detail": "OpenRouter API key is required"}))
                return
            if model_type == "openai" and (not openai_api_key or openai_api_key == "your_openai_api_key_here"):
                q.put(("error", {"detail": "OpenAI API key is required"}))
                return
            llm_service = LLMService(
                api_key=api_key,
                openai_api_key=openai_api_key,
                openrouter_model=request.openrouter_model,
                openai_model=request.openai_model,
                model_type=model_type,
                ollama_model=request.ollama_model,
            )
            if request.input_mode == "url":
                if not request.url:
                    q.put(("error", {"detail": "Please enter a valid URL"}))
                    return
                content_to_process = llm_service.extract_text_from_url(str(request.url))
            else:
                if not request.text or not request.text.strip():
                    q.put(("error", {"detail": "Please enter text to analyze"}))
                    return
                content_to_process = request.text

            def on_progress(p: dict):
                q.put(("progress", p))

            raw_graph_data = llm_service.extract_graph_data(
                content_to_process,
                system_prompt=request.system_prompt,
                user_prompt_template=request.user_prompt_template,
                is_url=(request.input_mode == "url"),
                two_pass=request.two_pass if request.two_pass is not None else Config.TWO_PASS_DEFAULT,
                extraction_method=request.extraction_method,
                chunking_method=request.chunking_method,
                progress_callback=on_progress,
            )
            processed_data = process_graph_results(raw_graph_data)
            q.put(("result", {
                "success": True,
                "data": processed_data,
                "extracted_text": content_to_process if request.input_mode == "url" else None,
            }))
        except Exception as e:
            q.put(("error", {"detail": str(e)}))

    threading.Thread(target=run_extraction, daemon=True).start()

    while True:
        msg_type, payload = q.get()
        if msg_type == "progress":
            yield f"data: {json.dumps(payload)}\n\n"
        elif msg_type == "result":
            yield f"data: {json.dumps({'type': 'result', **payload})}\n\n"
            break
        elif msg_type == "error":
            yield f"data: {json.dumps({'type': 'error', **payload})}\n\n"
            break


@app.post("/api/analyze-stream", tags=["Analysis"])
def analyze_stream(request: AnalyzeRequest):
    """Stream extraction progress via SSE, then return final result as last event."""
    return StreamingResponse(
        _analyze_stream_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _push_to_neo4j(
    entities: List[Dict],
    relationships: List[Dict],
    uri: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Push entities and relationships to Neo4j using parameterised Cypher MERGE.
    Maps entity labels (PERSON, ORGANIZATION, etc.) to Neo4j node labels.
    Use uri/username/password overrides for Aura or per-request connection.
    """
    if not NEO4J_AVAILABLE:
        raise Exception("Neo4j driver not installed. Run: pip install neo4j")
    neo4j_uri = uri or Config.NEO4J_URI
    neo4j_user = username or Config.NEO4J_USERNAME
    neo4j_pass = password or Config.NEO4J_PASSWORD
    if not neo4j_uri or not neo4j_pass or neo4j_pass == "password":
        raise Exception(
            "Neo4j not configured. Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env, "
            "or pass neo4j_uri, neo4j_username, neo4j_password in the request."
        )
    driver = GraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_pass),
    )
    try:
        with driver.session() as session:
            # Map extraction labels to valid Neo4j labels (alphanumeric only)
            # Includes both default and FTM Lite schema labels
            label_map = {
                "PERSON": "Person",
                "ORGANIZATION": "Organization",
                "ORGANISATION": "Organization",
                "COMPANY": "Company",
                "LEGAL_ENTITY": "LegalEntity",
                "ADDRESS": "Address",
                "LOCATION": "Location",
                "EVENT": "Event",
                "DOCUMENT": "Document",
                "CONCEPT": "Concept",
                "ENTITY": "Entity",
                "OTHER": "Entity",
                "UNKNOWN": "Entity",
            }
            nodes_created = 0
            rels_created = 0
            # Create nodes: MERGE on id, set name and label
            for e in entities:
                eid = e.get("id") or normalize_id(e.get("name", ""))
                name = e.get("name", "")
                label_raw = (e.get("label") or "ENTITY").strip().upper().replace(" ", "_")
                label = label_map.get(label_raw, "Entity")
                # MERGE node by id, set name, add label (Neo4j 5+)
                session.run(
                    f"MERGE (n:{label} {{id: $id}}) SET n.name = $name",
                    id=eid,
                    name=name,
                )
                nodes_created += 1
            # Create relationships (source/target are entity IDs)
            valid_ids = {e.get("id") or normalize_id(e.get("name", "")) for e in entities}
            for r in relationships:
                src = r.get("source", "")
                tgt = r.get("target", "")
                rel_type = (r.get("type") or "RELATED_TO").strip().upper().replace(" ", "_")
                if src not in valid_ids or tgt not in valid_ids:
                    continue
                session.run(
                    f"""
                    MATCH (a {{id: $src}}), (b {{id: $tgt}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    """,
                    src=src,
                    tgt=tgt,
                )
                rels_created += 1
        return {"nodes_created": nodes_created, "relationships_created": rels_created}
    finally:
        driver.close()


@app.get("/api/neo4j-status", tags=["Neo4j"])
def neo4j_status():
    """Check if Neo4j is configured and reachable. Used by UI to show connection status."""
    if not NEO4J_AVAILABLE:
        return {"connected": False, "error": "Neo4j driver not installed. Run: pip install neo4j"}
    if not Config.NEO4J_URI or not Config.NEO4J_PASSWORD or Config.NEO4J_PASSWORD == "password":
        return {"connected": False, "error": "Neo4j not configured. Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env"}
    try:
        driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD),
        )
        driver.verify_connectivity()
        driver.close()
        return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.post("/api/push-to-neo4j", tags=["Neo4j"])
def push_to_neo4j(request: PushToNeo4jRequest):
    """
    Push extracted entities and relationships directly to Neo4j.
    Uses NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD from env, or override via
    neo4j_uri, neo4j_username, neo4j_password in request body (e.g. for Aura).
    """
    try:
        result = _push_to_neo4j(
            request.entities,
            request.relationships,
            uri=request.neo4j_uri,
            username=request.neo4j_username,
            password=request.neo4j_password,
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download/{file_type}", tags=["Download"])
async def download_csv(file_type: str, request: DownloadRequest):
    """
    Download entities or relationships as CSV files compatible with Neo4j
    
    - **file_type**: Either 'entities' or 'relationships'
    - **request**: Contains the entities and relationships data
    """
    try:
        if file_type == 'entities':
            entities = request.entities
            df = pd.DataFrame(entities)
            df = df[['id', 'name', 'label']]
            df.columns = ['entityId:ID', 'name', ':LABEL']
            filename = 'entities.csv'
            
        elif file_type == 'relationships':
            relationships = request.relationships
            df = pd.DataFrame(relationships)
            df = df[['source', 'target', 'type']]
            df.columns = [':START_ID', ':END_ID', ':TYPE']
            filename = 'relationships.csv'
            
        else:
            raise HTTPException(status_code=400, detail="Invalid file type")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            df.to_csv(tmp_file.name, index=False)
            tmp_file_path = tmp_file.name
        
        return FileResponse(
            path=tmp_file_path,
            filename=filename,
            media_type='text/csv',
            background=BackgroundTask(os.unlink, tmp_file_path),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000) 
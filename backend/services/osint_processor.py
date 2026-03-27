"""
OSINT document processing service.
Supports multiple document formats and includes entity extraction.
"""

import asyncio
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """Document metadata for OSINT purposes."""
    title: str = ""
    author: str = ""
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    source_type: str = "pdf"  # pdf, docx, html, email, txt
    url: Optional[str] = None
    entities: Dict[str, List[str]] = field(default_factory=dict)
    credibility_score: float = 0.5  # 0-1, updated after analysis


class OSINTDocumentProcessor:
    """
    Multi-format document processor for OSINT workflows.
    Supports: PDF, DOCX, HTML, Email, TXT
    """
    
    def __init__(self):
        self._spacy_model = None
    
    @property
    def spacy_model(self):
        """Lazy-load spaCy model."""
        if self._spacy_model is None:
            try:
                import spacy
                self._spacy_model = spacy.load("en_core_web_sm")
            except Exception as e:
                logger.warning(f"spaCy model not available: {e}")
                self._spacy_model = False
        return self._spacy_model
    
    async def process_file(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """
        Process any supported document format.
        
        Returns:
            Tuple of (extracted text, metadata)
        """
        suffix = file_path.suffix.lower()
        
        if suffix == ".pdf":
            return await self._process_pdf(file_path)
        elif suffix in [".docx", ".doc"]:
            return await self._process_docx(file_path)
        elif suffix in [".html", ".htm"]:
            return await self._process_html(file_path)
        elif suffix == ".txt":
            return await self._process_txt(file_path)
        elif suffix in [".eml", ".msg"]:
            return await self._process_email(file_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    async def _process_pdf(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """Process PDF using PyMuPDF (existing logic)."""
        from services.pdf_service import PDFProcessor
        
        processor = PDFProcessor()
        parsed, _ = await processor.process_file(file_path)
        
        # Extract text
        full_text = "\n\n".join(
            "\n".join(block.text for block in page.blocks)
            for page in parsed.pages
        )
        
        # Extract metadata
        metadata = DocumentMetadata(source_type="pdf")
        
        # Try to extract title from first lines
        if parsed.pages and parsed.pages[0].blocks:
            first_block = parsed.pages[0].blocks[0].text
            if len(first_block) < 200:
                metadata.title = first_block[:100]
        
        return full_text, metadata
    
    async def _process_docx(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """Process DOCX using unstructured."""
        try:
            from unstructured.partition.docx import partition_docx
        except ImportError:
            return "", DocumentMetadata(source_type="docx")
        
        loop = asyncio.get_event_loop()
        
        def extract():
            elements = partition_docx(filename=str(file_path))
            return "\n\n".join(str(el) for el in elements)
        
        text = await loop.run_in_executor(None, extract)
        
        metadata = DocumentMetadata(source_type="docx")
        return text, metadata
    
    async def _process_html(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """Process HTML using unstructured."""
        try:
            from unstructured.partition.html import partition_html
        except ImportError:
            return "", DocumentMetadata(source_type="html")
        
        loop = asyncio.get_event_loop()
        
        def extract():
            elements = partition_html(filename=str(file_path))
            return "\n\n".join(str(el) for el in elements)
        
        text = await loop.run_in_executor(None, extract)
        
        metadata = DocumentMetadata(source_type="html")
        return text, metadata
    
    async def _process_txt(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """Process plain text."""
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, lambda: file_path.read_text(encoding="utf-8"))
        
        metadata = DocumentMetadata(source_type="txt")
        # Use first line as title
        first_line = text.split("\n")[0][:100]
        if first_line:
            metadata.title = first_line
        
        return text, metadata
    
    async def _process_email(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """Process email files."""
        try:
            from unstructured.partition.email import partition_email
        except ImportError:
            return "", DocumentMetadata(source_type="email")
        
        loop = asyncio.get_event_loop()
        
        def extract():
            elements = partition_email(filename=str(file_path))
            return "\n\n".join(str(el) for el in elements)
        
        text = await loop.run_in_executor(None, extract)
        
        metadata = DocumentMetadata(source_type="email")
        return text, metadata
    
    async def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text using spaCy.
        
        Returns:
            Dict with keys: persons, organizations, locations, dates
        """
        if not self.spacy_model:
            return {"persons": [], "organizations": [], "locations": [], "dates": []}
        
        loop = asyncio.get_event_loop()
        
        def extract():
            doc = self.spacy_model(text[:100000])  # Limit text length
            entities = {
                "persons": list(set(ent.text for ent in doc.ents if ent.label_ == "PERSON")),
                "organizations": list(set(ent.text for ent in doc.ents if ent.label_ == "ORG")),
                "locations": list(set(ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"])),
                "dates": list(set(ent.text for ent in doc.ents if ent.label_ in ["DATE", "TIME"]))
            }
            return entities
        
        return await loop.run_in_executor(None, extract)
    
    def calculate_credibility_score(
        self,
        metadata: DocumentMetadata,
        entity_count: int,
        text_length: int
    ) -> float:
        """
        Calculate source credibility score (0-1).
        
        Factors:
        - Source type (official > web > social)
        - Has author
        - Has date
        - Text length (too short = suspicious)
        """
        score = 0.5
        
        # Source type scoring
        source_scores = {
            "pdf": 0.8,
            "docx": 0.7,
            "email": 0.6,
            "html": 0.5,
            "txt": 0.4
        }
        score = source_scores.get(metadata.source_type, 0.5) * 0.3
        
        # Author presence
        if metadata.author:
            score += 0.2
        
        # Date presence
        if metadata.created_date:
            score += 0.1
        
        # Text length (reasonable length = more credible)
        if 1000 < text_length < 100000:
            score += 0.2
        elif text_length < 100:
            score += 0.05
        
        # Entity richness (has entities = likely structured content)
        if entity_count > 10:
            score += 0.2
        
        return min(score, 1.0)
    
    async def process_for_osint(
        self,
        file_path: Path,
        extract_entities_flag: bool = True
    ) -> Tuple[str, DocumentMetadata]:
        """
        Full OSINT processing pipeline.
        
        Extracts text, metadata, entities, and calculates credibility.
        """
        text, metadata = await self.process_file(file_path)
        
        # Extract entities if requested
        if extract_entities_flag:
            entities = await self.extract_entities(text)
            metadata.entities = entities
        
        # Calculate credibility
        entity_count = sum(len(v) for v in metadata.entities.values())
        metadata.credibility_score = self.calculate_credibility_score(
            metadata, entity_count, len(text)
        )
        
        return text, metadata

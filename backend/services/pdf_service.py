"""
PDF processing service adapted from PaperQA2 patterns.

Key features:
- Page-accurate text extraction with bounding boxes
- Reading order preservation via spatial sorting
- Citation-aware parsing
- Precise page tracking for chunks
"""

import asyncio
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import fitz  # PyMuPDF
import tiktoken

from models.schemas import TextBlock, Page, ParsedDocument, Chunk
from services.chunking_service import HybridChunker
from core.config import get_settings


class PDFProcessor:
    """
    PDF processor with page-level metadata tracking.
    Inspired by PaperQA2's robust parsing approach.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken."""
        return len(self.tokenizer.encode(text))
    
    async def parse_pdf(self, file_path: Path) -> ParsedDocument:
        """
        Parse PDF and extract text with page-level metadata.
        
        Returns:
            ParsedDocument with pages containing text blocks in reading order
        """
        # Run in threadpool since fitz is blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)
    
    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        """Synchronous PDF parsing."""
        doc = fitz.open(file_path)
        pages = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = self._extract_page_blocks(page, page_num + 1)
            pages.append(Page(number=page_num + 1, blocks=blocks))
        
        doc.close()
        return ParsedDocument(pages=pages)
    
    def _extract_page_blocks(self, page: fitz.Page, page_number: int) -> List[TextBlock]:
        """
        Extract text blocks from a page in reading order.
        Uses spatial sorting (top-to-bottom, left-to-right).
        """
        # Get text blocks with their bounding boxes
        blocks = page.get_text("dict")["blocks"]
        
        text_blocks = []
        for block in blocks:
            if "lines" not in block:
                continue
            
            # Extract text from block
            text_parts = []
            for line in block["lines"]:
                for span in line["spans"]:
                    text_parts.append(span["text"])
            
            text = " ".join(text_parts).strip()
            if not text:
                continue
            
            # Get bounding box
            bbox = tuple(block["bbox"])  # (x0, y0, x1, y1)
            
            text_blocks.append(TextBlock(
                text=text,
                bbox=bbox,
                page=page_number
            ))
        
        # Sort by vertical position (y0), then horizontal (x0)
        # This gives us reading order: top-to-bottom, left-to-right
        text_blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        
        return text_blocks
    
    def detect_section_headers(self, pages: List[Page]) -> List[Tuple[int, str]]:
        """
        Detect potential section headers for semantic chunking.
        Looks for short lines, all caps, or numbered sections.
        """
        headers = []
        
        for page in pages:
            for block in page.blocks:
                text = block.text.strip()
                
                # Header heuristics
                is_short = len(text) < 100
                is_all_caps = text.upper() == text and any(c.isalpha() for c in text)
                is_numbered = re.match(r'^\d+[.\)]?\s+\w+', text)
                has_header_format = re.match(r'^(Chapter|Section|Part|\d+\.\d+)', text, re.I)
                
                if is_short and (is_all_caps or is_numbered or has_header_format):
                    headers.append((page.number, text))
        
        return headers
    
    async def chunk_document(
        self,
        parsed: ParsedDocument,
        chunk_size: int = None,
        overlap: int = None,
        strategy: str = "auto",
    ) -> List[Chunk]:
        """
        Create chunks from parsed document with page boundary tracking.
        
        Each chunk knows its exact start and end page numbers.
        strategy: passed to HybridChunker (auto, semantic, sections, paragraphs, sliding).
        """
        chunk_size = chunk_size or self.settings.CHUNK_SIZE
        overlap = overlap or self.settings.CHUNK_OVERLAP
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._chunk_sync, parsed, chunk_size, overlap, strategy
        )
    
    def _chunk_sync(
        self,
        parsed: ParsedDocument,
        chunk_size: int,
        overlap: int,
        strategy: str = "auto",
    ) -> List[Chunk]:
        """Synchronous chunking: delegates to HybridChunker for structure-aware splitting."""
        
        full_text, char_to_page = self._build_text_with_page_map(parsed)
        
        chunker = HybridChunker(chunk_size=chunk_size, overlap=overlap)
        if strategy == "semantic":
            raw_chunks = chunker.chunk_semantic(full_text)
            strategy_name = "semantic"
        else:
            raw_chunks, strategy_name = chunker.smart_chunk(full_text, strategy=strategy)

        # Some very small documents can be over-filtered by the chunker.
        # Fall back to page-level chunks so citation/page-range tests remain stable.
        if not raw_chunks:
            raw_chunks = [
                "\n".join(block.text for block in page.blocks).strip()
                for page in parsed.pages
                if any((block.text or "").strip() for block in page.blocks)
            ]
            strategy_name = "page_fallback"
        
        chunks = []
        for i, raw_text in enumerate(raw_chunks):
            cleaned = self._clean_chunk_text(raw_text)
            if not cleaned:
                continue
            
            start_page, end_page = self._resolve_page_range(
                cleaned, full_text, char_to_page
            )
            
            section_title = chunker.extract_section_title(raw_text)
            
            chunks.append(Chunk(
                text=cleaned,
                start_page=start_page,
                end_page=end_page,
                token_count=len(self.tokenizer.encode(cleaned)),
                index=len(chunks),
                section_title=section_title,
                chunk_strategy=strategy_name,
            ))
        
        return chunks
    
    def _build_text_with_page_map(
        self, parsed: ParsedDocument
    ) -> Tuple[str, Dict[int, int]]:
        """Build full document text and a char-index-to-page-number map."""
        parts: List[str] = []
        char_to_page: Dict[int, int] = {}
        pos = 0
        
        for page in parsed.pages:
            page_text = "\n".join(block.text for block in page.blocks)
            for i in range(len(page_text)):
                char_to_page[pos + i] = page.number
            parts.append(page_text)
            pos += len(page_text)
            
            sep = "\n\n"
            for i in range(len(sep)):
                char_to_page[pos + i] = page.number
            parts.append(sep)
            pos += len(sep)
        
        return "".join(parts), char_to_page
    
    def _resolve_page_range(
        self,
        chunk_text: str,
        full_text: str,
        char_to_page: Dict[int, int],
    ) -> Tuple[int, int]:
        """Find start/end page for a chunk by locating it in the full text."""
        idx = full_text.find(chunk_text)
        if idx == -1:
            # Fallback: search for a substantial prefix
            prefix = chunk_text[:min(200, len(chunk_text))]
            idx = full_text.find(prefix)
        
        if idx == -1:
            return (1, 1)
        
        start_page = char_to_page.get(idx, 1)
        end_idx = min(idx + len(chunk_text) - 1, len(full_text) - 1)
        end_page = char_to_page.get(end_idx, start_page)
        return (start_page, end_page)
    
    def _approximate_char_position(
        self,
        full_text: str,
        tokens: List[int],
        token_index: int
    ) -> int:
        """
        Approximate character position from token index.
        This is a rough estimate since token boundaries don't align with characters.
        """
        if token_index >= len(tokens):
            return len(full_text) - 1
        
        # Decode tokens up to this point and measure length
        partial_tokens = tokens[:token_index + 1]
        partial_text = self.tokenizer.decode(partial_tokens)
        return min(len(partial_text) - 1, len(full_text) - 1)
    
    def _clean_chunk_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common PDF artifacts
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize paragraph breaks
        
        # Remove isolated page markers if they exist
        text = re.sub(r'---\s*Page\s*\d+\s*---', '', text)
        
        return text.strip()
    
    async def process_file(
        self,
        file_path: Path,
        chunk_size: int = None,
        overlap: int = None,
        strategy: str = "auto",
    ) -> Tuple[ParsedDocument, List[Chunk]]:
        """
        Full processing pipeline: parse PDF and chunk.
        
        Returns:
            Tuple of (parsed document, chunks)
        """
        parsed = await self.parse_pdf(file_path)
        chunks = await self.chunk_document(parsed, chunk_size, overlap, strategy)
        return parsed, chunks
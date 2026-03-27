"""
Docling-based document ingestion service.

Replaces raw PyMuPDF with Docling for superior PDF parsing:
- Table structure extraction
- Layout-aware reading order
- Multi-format support (PDF, DOCX, PPTX, XLSX, HTML, images)
- OCR for scanned documents
- Unified DoclingDocument intermediate representation

Falls back to PyMuPDF if Docling is unavailable.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Tuple, Optional

import tiktoken

from models.schemas import TextBlock, Page, ParsedDocument, Chunk
from services.chunking_service import HybridChunker
from core.config import get_settings

logger = logging.getLogger(__name__)

# Supported extensions beyond PDF when Docling is available
DOCLING_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
    ".md", ".tex",
}


def _docling_available() -> bool:
    """Check whether the docling package is installed."""
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


class DoclingProcessor:
    """
    Document processor powered by Docling.

    Why Docling over raw PyMuPDF?
    - Docling uses vision models for layout analysis, so it preserves
      reading order across columns, sidebars, and footnotes.
    - It extracts tables as structured data rather than garbled text.
    - It handles scanned PDFs via built-in OCR.
    - It supports multiple file formats with a single API.
    """

    def __init__(self):
        self.settings = get_settings()
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self._converter = None

    def _get_converter(self):
        """Lazy-init the Docling converter (heavy import)."""
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
        return self._converter

    @staticmethod
    def supports(file_path: Path) -> bool:
        """Return True if this processor can handle the file type."""
        return (
            _docling_available()
            and file_path.suffix.lower() in DOCLING_EXTENSIONS
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    async def parse_document(self, file_path: Path) -> ParsedDocument:
        """Parse any supported document via Docling and return our standard ParsedDocument."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        converter = self._get_converter()
        result = converter.convert(str(file_path))
        doc = result.document

        # Docling exposes pages for PDFs; for other formats we synthesise
        # a single logical page from the markdown export.
        pages: List[Page] = []

        if hasattr(doc, "pages") and doc.pages:
            for pg_idx, pg in enumerate(doc.pages, start=1):
                blocks = self._page_to_blocks(pg, pg_idx)
                pages.append(Page(number=pg_idx, blocks=blocks))
        else:
            # Non-paginated formats — treat entire doc as one page
            md_text = result.document.export_to_markdown()
            blocks = [TextBlock(text=md_text, bbox=(0, 0, 0, 0), page=1)]
            pages.append(Page(number=1, blocks=blocks))

        return ParsedDocument(pages=pages)

    @staticmethod
    def _page_to_blocks(page, page_number: int) -> List[TextBlock]:
        """Convert a Docling page object into our TextBlock list."""
        blocks: List[TextBlock] = []
        # Docling pages expose items or cells depending on version
        items = getattr(page, "items", None) or getattr(page, "cells", [])
        for item in items:
            text = getattr(item, "text", "") or ""
            text = text.strip()
            if not text:
                continue
            bbox = getattr(item, "bbox", (0, 0, 0, 0))
            if hasattr(bbox, "as_tuple"):
                bbox = bbox.as_tuple()
            elif not isinstance(bbox, tuple):
                bbox = tuple(bbox) if bbox else (0, 0, 0, 0)
            blocks.append(TextBlock(text=text, bbox=bbox, page=page_number))

        # Reading-order sort: top-to-bottom, left-to-right
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        return blocks

    # ------------------------------------------------------------------
    # Chunking (delegates to shared HybridChunker)
    # ------------------------------------------------------------------

    async def chunk_document(
        self,
        parsed: ParsedDocument,
        chunk_size: int = None,
        overlap: int = None,
        strategy: str = "auto",
    ) -> List[Chunk]:
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
        full_text, char_to_page = self._build_text_with_page_map(parsed)
        chunker = HybridChunker(chunk_size=chunk_size, overlap=overlap)

        if strategy == "semantic":
            raw_chunks = chunker.chunk_semantic(full_text)
            strategy_name = "semantic"
        else:
            raw_chunks, strategy_name = chunker.smart_chunk(full_text, strategy=strategy)

        chunks: List[Chunk] = []
        for raw_text in raw_chunks:
            cleaned = self._clean(raw_text)
            if not cleaned:
                continue
            sp, ep = self._resolve_page_range(cleaned, full_text, char_to_page)
            section_title = chunker.extract_section_title(raw_text)
            chunks.append(Chunk(
                text=cleaned,
                start_page=sp,
                end_page=ep,
                token_count=len(self.tokenizer.encode(cleaned)),
                index=len(chunks),
                section_title=section_title,
                chunk_strategy=strategy_name,
            ))
        return chunks

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def process_file(
        self,
        file_path: Path,
        chunk_size: int = None,
        overlap: int = None,
        strategy: str = "auto",
    ) -> Tuple[ParsedDocument, List[Chunk]]:
        parsed = await self.parse_document(file_path)
        chunks = await self.chunk_document(parsed, chunk_size, overlap, strategy)
        return parsed, chunks

    # ------------------------------------------------------------------
    # Helpers (shared logic with PDFProcessor to avoid duplication)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_text_with_page_map(parsed: ParsedDocument):
        parts, char_to_page, pos = [], {}, 0
        for page in parsed.pages:
            page_text = "\n".join(b.text for b in page.blocks)
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

    @staticmethod
    def _resolve_page_range(chunk_text, full_text, char_to_page):
        idx = full_text.find(chunk_text)
        if idx == -1:
            idx = full_text.find(chunk_text[:min(200, len(chunk_text))])
        if idx == -1:
            return 1, 1
        sp = char_to_page.get(idx, 1)
        ep = char_to_page.get(min(idx + len(chunk_text) - 1, len(full_text) - 1), sp)
        return sp, ep

    @staticmethod
    def _clean(text: str) -> str:
        import re
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'---\s*Page\s*\d+\s*---', '', text)
        return text.strip()


def get_document_processor(file_path: Path):
    """Factory: return DoclingProcessor when possible, else PDFProcessor."""
    from core.config import get_settings
    settings = get_settings()
    if not settings.ENABLE_DOCLING:
        from services.pdf_service import PDFProcessor
        logger.info("Docling disabled; using PyMuPDF for %s", file_path.name)
        return PDFProcessor()
    if DoclingProcessor.supports(file_path):
        logger.info("Using Docling processor for %s", file_path.name)
        return DoclingProcessor()

    from services.pdf_service import PDFProcessor
    logger.info("Falling back to PyMuPDF processor for %s", file_path.name)
    return PDFProcessor()

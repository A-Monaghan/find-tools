"""
PDF service tests — OSINT: chunking preserves page boundaries for citations.
"""
import pytest
from pathlib import Path

from models.schemas import TextBlock, Page, ParsedDocument, Chunk
from services.pdf_service import PDFProcessor


@pytest.fixture
def processor():
    return PDFProcessor()


def test_estimate_tokens(processor):
    text = "The threat actor TA-404 was observed targeting financial sector."
    n = processor.estimate_tokens(text)
    assert n >= 8 and n <= 25


def test_clean_chunk_text(processor):
    dirty = "  Multiple   spaces  \n\n--- Page 3 ---\n\n  and page marker  "
    out = processor._clean_chunk_text(dirty)
    assert "--- Page" not in out
    assert out.strip() == out


def test_chunk_sync_preserves_page_range(processor):
    """OSINT: Chunks must have correct start_page/end_page for citations."""
    # Build a minimal parsed doc: two pages of text
    page1 = Page(number=1, blocks=[TextBlock("Page one content here for chunking.", (0, 0, 100, 20), 1)])
    page2 = Page(number=2, blocks=[TextBlock("Page two content here for attribution.", (0, 0, 100, 20), 2)])
    parsed = ParsedDocument(pages=[page1, page2])
    # Small chunk size so we get multiple chunks
    chunks = processor._chunk_sync(parsed, chunk_size=8, overlap=2)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.start_page >= 1 and c.end_page >= 1
        assert c.start_page <= 2 and c.end_page <= 2
        assert c.token_count > 0
        assert c.text.strip()


def test_chunk_page_range_property():
    """Chunk.page_range string for single vs multi-page."""
    c1 = Chunk("text", 5, 5, 10, 0)
    c2 = Chunk("text", 5, 7, 30, 0)
    assert c1.page_range == "Page 5"
    assert "5" in c2.page_range and "7" in c2.page_range

"""
Citation service tests — OSINT use cases: source attribution, refusal when not in docs.
"""
from uuid import uuid4
import pytest

from services.citation_service import CitationService, RetrievedChunk


def test_refusal_when_info_not_in_docs():
    """OSINT: Answer that correctly states info not in documents is valid."""
    svc = CitationService()
    chunks = [
        RetrievedChunk("c1", uuid4(), "Report.pdf", "Unrelated content.", 1, 1, 0.5),
    ]
    answer = "The information is not found in the provided documents."
    result = svc.validate_answer(answer, chunks)
    assert result.is_valid is True
    assert "not found" in result.issues[0].lower() or len(result.citations) == 0


def test_citation_extraction_osint_style(osint_source_chunk):
    """OSINT: Answer grounded in report excerpt gets citation with page."""
    svc = CitationService(similarity_threshold=0.6)
    answer = "TA-404 uses infrastructure linked to IP 192.0.2.1 and example-c2.net. Activity was first observed in Q3 2023."
    result = svc.validate_answer(answer, [osint_source_chunk])
    assert len(result.citations) >= 1
    assert result.citations[0].start_page == 12
    assert "OSINT" in result.citations[0].document_name or "Report" in result.citations[0].document_name


def test_multi_document_citation_deduplication(osint_source_chunks):
    """OSINT: Multiple chunks from same doc yield deduplicated citations."""
    svc = CitationService(similarity_threshold=0.5)
    answer = (
        "TA-404 uses infrastructure at 192.0.2.1 and example-c2.net. "
        "They target the financial sector and use spear-phishing with document macros. IOCs are in Appendix B."
    )
    result = svc.validate_answer(answer, osint_source_chunks)
    assert len(result.citations) >= 1
    # Dedupe keeps one per (document_id, chunk_id)
    seen = set((c.document_id, c.chunk_id) for c in result.citations)
    assert len(seen) == len(result.citations)


def test_format_citations_for_display(osint_source_chunk):
    """Citation display includes document name and page for audit trail."""
    svc = CitationService()
    from services.citation_service import Citation
    c = Citation(
        document_id=osint_source_chunk.document_id,
        document_name=osint_source_chunk.document_name,
        chunk_id=osint_source_chunk.chunk_id,
        start_page=12,
        end_page=14,
        evidence_quote="TA-404 uses 192.0.2.1",
        relevance_score=0.9,
    )
    out = svc.format_citations_for_display([c])
    assert "12" in out
    assert "14" in out or "Page" in out

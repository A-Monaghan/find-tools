"""
Citation validation service adapted from PaperQA2.

Ensures answers are grounded in retrieved context and provides
citation extraction with evidence quotes.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from difflib import SequenceMatcher
from uuid import UUID

from core.config import get_settings


@dataclass
class Citation:
    """A validated citation with evidence."""
    document_id: UUID
    document_name: str
    chunk_id: str
    start_page: int
    end_page: int
    evidence_quote: str
    relevance_score: float


@dataclass
class RetrievedChunk:
    """Chunk retrieved from vector search."""
    chunk_id: str
    document_id: UUID
    document_name: str
    text: str
    start_page: int
    end_page: int
    score: float


@dataclass
class ValidationResult:
    """Result of citation validation."""
    is_valid: bool
    citations: List[Citation]
    unsupported_claims: List[str]
    confidence: float
    issues: List[str] = field(default_factory=list)


class CitationService:
    """
    Validates that LLM answers are grounded in source documents.
    Extracts and scores citations.
    """
    
    def __init__(self, similarity_threshold: float = None):
        settings = get_settings()
        self.threshold = similarity_threshold or settings.CITATION_SIMILARITY_THRESHOLD
    
    def validate_answer(
        self,
        answer: str,
        source_chunks: List[RetrievedChunk]
    ) -> ValidationResult:
        """
        Validate that answer is supported by source chunks.
        
        Returns:
            ValidationResult with citations and any unsupported claims
        """
        issues = []
        
        # Check for refusal patterns
        refusal_patterns = [
            r"not found in (?:the )?(?:provided )?document",
            r"information is not available",
            r"cannot find.*in the context",
            r"no information.*in (?:the )?(?:provided )?source",
        ]
        
        for pattern in refusal_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                # Answer admits it doesn't know - this is valid
                return ValidationResult(
                    is_valid=True,
                    citations=[],
                    unsupported_claims=[],
                    confidence=1.0,
                    issues=["Answer indicates information not found in documents"]
                )
        
        # Extract citations
        citations = self._extract_citations(answer, source_chunks)
        
        if not citations:
            issues.append("No citations found in answer")
        
        # Find unsupported claims
        unsupported = self._find_unsupported_claims(
            answer,
            citations,
            source_chunks
        )
        
        # Calculate confidence
        confidence = self._calculate_confidence(citations, answer)
        
        is_valid = len(unsupported) == 0 and len(citations) > 0
        
        return ValidationResult(
            is_valid=is_valid,
            citations=citations,
            unsupported_claims=unsupported,
            confidence=confidence,
            issues=issues
        )
    
    def _extract_citations(
        self,
        answer: str,
        chunks: List[RetrievedChunk]
    ) -> List[Citation]:
        """
        Extract citations by matching answer text to source chunks.
        Uses fuzzy string matching for robustness.
        """
        citations = []
        
        # Split answer into sentences
        sentences = self._split_sentences(answer)
        
        for sentence in sentences:
            # Skip short sentences (likely transitions)
            if len(sentence.split()) < 5:
                continue
            
            best_match = None
            best_score = 0.0
            
            # Find best matching chunk
            for chunk in chunks:
                similarity = self._text_similarity(sentence, chunk.text)
                
                if similarity > self.threshold and similarity > best_score:
                    best_score = similarity
                    best_match = chunk
            
            if best_match:
                # Extract the specific quote that matches
                evidence = self._extract_matching_quote(
                    sentence,
                    best_match.text
                )
                
                citations.append(Citation(
                    document_id=best_match.document_id,
                    document_name=best_match.document_name,
                    chunk_id=best_match.chunk_id,
                    start_page=best_match.start_page,
                    end_page=best_match.end_page,
                    evidence_quote=evidence,
                    relevance_score=best_score
                ))
        
        # Deduplicate citations
        return self._deduplicate_citations(citations)
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        # More sophisticated approaches could use NLTK or spaCy
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings.
        Uses SequenceMatcher for fuzzy matching.
        """
        # Normalize texts
        t1 = self._normalize_text(text1)
        t2 = self._normalize_text(text2)
        
        # Quick check: does t1 contain significant words from t2?
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Jaccard similarity for word overlap
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0
        # Containment catches the common case where a valid answer sentence
        # is a concise subset of a longer source chunk.
        containment = intersection / min(len(words1), len(words2))
        
        # Sequence similarity for phrase matching
        sequence_sim = SequenceMatcher(None, t1, t2).ratio()
        
        # Combined score (weighted average) with containment boost.
        combined = 0.25 * jaccard + 0.45 * sequence_sim + 0.30 * containment
        return min(max(combined, 0.0), 1.0)
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()
        # Remove citations like [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _extract_matching_quote(
        self,
        answer_sentence: str,
        source_text: str,
        max_length: int = 200
    ) -> str:
        """
        Extract the specific portion of source that matches answer.
        """
        # Find best matching substring in source
        best_match = ""
        best_score = 0.0
        
        # Try different window sizes
        answer_words = answer_sentence.split()
        source_words = source_text.split()
        
        window_size = min(len(answer_words) + 5, len(source_words))
        
        for i in range(len(source_words) - window_size + 1):
            window = " ".join(source_words[i:i + window_size])
            score = self._text_similarity(answer_sentence, window)
            
            if score > best_score:
                best_score = score
                best_match = window
        
        # Truncate if too long
        if len(best_match) > max_length:
            best_match = best_match[:max_length].rsplit(' ', 1)[0] + "..."
        
        return best_match
    
    def _find_unsupported_claims(
        self,
        answer: str,
        citations: List[Citation],
        source_chunks: List[RetrievedChunk]
    ) -> List[str]:
        """
        Identify claims in answer that aren't supported by citations.
        """
        unsupported = []
        sentences = self._split_sentences(answer)
        
        # Get all cited evidence
        cited_text = " ".join(c.evidence_quote for c in citations)
        cited_text = self._normalize_text(cited_text)
        
        for sentence in sentences:
            # Skip short sentences
            if len(sentence.split()) < 5:
                continue
            
            # Check if sentence is supported by any citation
            normalized = self._normalize_text(sentence)
            
            # Skip sentences that look like citations themselves
            if re.match(r'^\[\d+\]', sentence):
                continue
            
            # Check similarity to cited text
            similarity = self._text_similarity(normalized, cited_text)
            
            if similarity < self.threshold * 0.7:  # Lower threshold for claim detection
                # This sentence might be unsupported
                # Check against all source chunks directly
                max_chunk_sim = max(
                    self._text_similarity(normalized, chunk.text)
                    for chunk in source_chunks
                ) if source_chunks else 0
                
                if max_chunk_sim < self.threshold * 0.5:
                    unsupported.append(sentence)
        
        return unsupported
    
    def _deduplicate_citations(self, citations: List[Citation]) -> List[Citation]:
        """Remove duplicate citations keeping highest relevance."""
        seen = {}
        
        for citation in citations:
            key = (citation.document_id, citation.chunk_id)
            
            if key not in seen or citation.relevance_score > seen[key].relevance_score:
                seen[key] = citation
        
        # Sort by relevance
        return sorted(seen.values(), key=lambda c: c.relevance_score, reverse=True)
    
    def _calculate_confidence(
        self,
        citations: List[Citation],
        answer: str
    ) -> float:
        """Calculate overall confidence score."""
        if not citations:
            return 0.0
        
        # Average relevance score
        avg_relevance = sum(c.relevance_score for c in citations) / len(citations)
        
        # Coverage: what fraction of answer sentences have citations?
        sentences = [s for s in self._split_sentences(answer) if len(s.split()) >= 5]
        coverage = min(len(citations) / max(len(sentences), 1), 1.0)
        
        return 0.7 * avg_relevance + 0.3 * coverage
    
    def format_citations_for_display(self, citations: List[Citation]) -> str:
        """Format citations for display in answer."""
        if not citations:
            return ""
        
        parts = []
        for i, citation in enumerate(citations, 1):
            page_str = (
                f"Page {citation.start_page}"
                if citation.start_page == citation.end_page
                else f"Pages {citation.start_page}-{citation.end_page}"
            )
            parts.append(f"[{i}] {citation.document_name}, {page_str}")
        
        return "\n".join(parts)

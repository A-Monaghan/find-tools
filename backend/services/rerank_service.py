"""
Cross-encoder reranking service for improved retrieval quality.

Re-ranks initial vector search results using a cross-encoder model
for better relevance scoring.
"""

import asyncio
import logging
from typing import List
from dataclasses import dataclass

import numpy as np
from sentence_transformers import CrossEncoder

from core.config import get_settings
from services.vector_store import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class RerankedResult:
    """Result after reranking."""
    chunk_id: str
    document_id: str
    document_name: str
    text: str
    start_page: int
    end_page: int
    vector_score: float  # Original vector similarity
    rerank_score: float  # Cross-encoder score
    combined_score: float  # Weighted combination


def vector_order_top_k(
    results: List[SearchResult],
    document_name_map: dict,
    top_k: int,
) -> List[RerankedResult]:
    """Take top-k chunks by dense score only — skips cross-encoder (much faster on CPU)."""
    if not results:
        return []
    ordered = sorted(results, key=lambda r: r.score, reverse=True)[:top_k]
    out: List[RerankedResult] = []
    for r in ordered:
        doc_name = document_name_map.get(str(r.document_id), "Unknown")
        if doc_name == "Unknown" and hasattr(r, "document_name"):
            doc_name = r.document_name  # type: ignore[attr-defined]
        out.append(
            RerankedResult(
                chunk_id=r.chunk_id,
                document_id=str(r.document_id),
                document_name=doc_name,
                text=r.text,
                start_page=r.start_page,
                end_page=r.end_page,
                vector_score=r.score,
                rerank_score=r.score,
                combined_score=r.score,
            )
        )
    return out


class RerankService:
    """
    Re-ranks retrieval results using cross-encoder.
    
    Cross-encoders are more accurate than bi-encoders (embeddings)
    because they can attend to both query and document simultaneously.
    However, they're slower, so we only use them on top-K results.
    """
    
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(self, model_name: str = None):
        settings = get_settings()
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model: CrossEncoder = None
        self.top_k_rerank = settings.TOP_K_RERANK
    
    def _load_model(self) -> CrossEncoder:
        """Lazy load the cross-encoder model."""
        if self._model is None:
            self._model = CrossEncoder(self.model_name)
        return self._model
    
    async def rerank(
        self,
        query: str,
        results: List[SearchResult],
        document_name_map: dict = None
    ) -> List[RerankedResult]:
        """
        Re-rank search results using cross-encoder.
        
        Args:
            query: Original query
            results: Results from vector search
            document_name_map: Map of document_id -> document_name
        
        Returns:
            Re-ranked results sorted by combined score
        """
        if not results:
            return []
        
        model = self._load_model()
        
        # Prepare query-document pairs
        pairs = [(query, r.text) for r in results]
        
        # Run in threadpool to avoid blocking
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: model.predict(pairs, show_progress_bar=False)
        )
        
        # Normalize scores to 0-1 range
        # Cross-encoder can output negative scores, so we sigmoid normalize
        rerank_scores = 1 / (1 + np.exp(-scores))
        
        # Create reranked results
        reranked = []
        for i, (result, rerank_score) in enumerate(zip(results, rerank_scores)):
            # Get document name
            doc_name = document_name_map.get(str(result.document_id), "Unknown")
            if doc_name == "Unknown" and hasattr(result, 'document_name'):
                doc_name = result.document_name
            
            # Combine scores (weighted average)
            # Vector score captures semantic similarity
            # Rerank score captures relevance
            combined = 0.4 * result.score + 0.6 * rerank_score
            
            reranked.append(RerankedResult(
                chunk_id=result.chunk_id,
                document_id=str(result.document_id),
                document_name=doc_name,
                text=result.text,
                start_page=result.start_page,
                end_page=result.end_page,
                vector_score=result.score,
                rerank_score=float(rerank_score),
                combined_score=float(combined)
            ))
        
        # Sort by combined score descending
        reranked.sort(key=lambda x: x.combined_score, reverse=True)
        
        # Return top-k
        return reranked[:self.top_k_rerank]
    
    async def rerank_with_fallback(
        self,
        query: str,
        results: List[SearchResult],
        document_name_map: dict = None
    ) -> List[RerankedResult]:
        """
        Re-rank with fallback to vector scores if reranking fails.
        """
        try:
            return await self.rerank(query, results, document_name_map)
        except Exception as e:
            # Keep retrieval available even when cross-encoder model load/inference fails.
            logger.warning("Reranking failed, falling back to dense ranking: %s", e, exc_info=True)
            
            reranked = []
            for result in results[:self.top_k_rerank]:
                doc_name = document_name_map.get(str(result.document_id), "Unknown")
                if doc_name == "Unknown" and hasattr(result, 'document_name'):
                    doc_name = result.document_name
                
                reranked.append(RerankedResult(
                    chunk_id=result.chunk_id,
                    document_id=str(result.document_id),
                    document_name=doc_name,
                    text=result.text,
                    start_page=result.start_page,
                    end_page=result.end_page,
                    vector_score=result.score,
                    rerank_score=result.score,  # Use vector score as fallback
                    combined_score=result.score
                ))
            
            return reranked
"""
Fusion Retrieval: combines dense vector search with BM25 sparse search.

Why fusion over vector-only?
- Dense embeddings excel at semantic similarity ("meaning").
- BM25 excels at exact lexical matches (names, codes, acronyms).
- Combining them via Reciprocal Rank Fusion (RRF) captures both
  signals, consistently outperforming either method alone.

This service sits between the query route and the vector store,
transparently merging results from both retrieval paths.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from collections import defaultdict

import numpy as np
from rank_bm25 import BM25Okapi

from services.vector_store import SearchResult, VectorStore
from core.config import get_settings

logger = logging.getLogger(__name__)


class FusionRetriever:
    """
    Merges BM25 (sparse) and vector (dense) retrieval using
    Reciprocal Rank Fusion.
    """

    # RRF constant — controls how much lower-ranked items are penalised
    RRF_K = 60

    def __init__(
        self,
        vector_store: VectorStore,
        alpha: float = 0.5,
    ):
        """
        Args:
            vector_store: The dense vector store to query.
            alpha: Weight for dense scores (1-alpha goes to BM25).
                   0.5 = equal weight; >0.5 favours dense.
        """
        self.vector_store = vector_store
        self.alpha = alpha
        self._bm25_index: Optional[BM25Okapi] = None
        self._corpus_results: List[SearchResult] = []

    # ------------------------------------------------------------------
    # Index BM25 corpus from vector store payloads
    # ------------------------------------------------------------------

    def build_bm25_index(self, results: List[SearchResult]):
        """Build a BM25 index over the supplied result texts.

        Called with the full set of results from the dense search so that
        BM25 operates over the same candidate pool.  This avoids needing
        a separate full-text index in the database.
        """
        self._corpus_results = results
        tokenised = [self._tokenise(r.text) for r in results]
        self._bm25_index = BM25Okapi(tokenised)

    @staticmethod
    def _tokenise(text: str) -> List[str]:
        """Simple whitespace + lowercasing tokeniser."""
        return text.lower().split()

    # ------------------------------------------------------------------
    # Fused search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        query_embedding: np.ndarray,
        top_k: int = 20,
        document_filter: Optional[UUID] = None,
    ) -> List[SearchResult]:
        """Run dense + BM25 search and fuse with RRF.

        Flow:
        1. Dense vector search (top_k * 2 to widen candidate pool).
        2. Build ephemeral BM25 index over those candidates.
        3. Score candidates with BM25.
        4. Merge via Reciprocal Rank Fusion.
        5. Return top_k fused results.
        """
        settings = get_settings()

        # 1. Dense retrieval — fetch a wider pool for BM25 to re-score
        dense_results = await self.vector_store.search(
            query_embedding,
            top_k=top_k * 2,
            document_filter=document_filter,
        )

        if not dense_results:
            return []

        # 2. Build BM25 index over dense candidates
        self.build_bm25_index(dense_results)

        # 3. BM25 scoring
        query_tokens = self._tokenise(query)
        bm25_scores = self._bm25_index.get_scores(query_tokens)

        # 4. RRF fusion
        # Build rank maps
        dense_rank: Dict[str, int] = {}
        for rank, r in enumerate(dense_results):
            dense_rank[r.chunk_id] = rank

        # Sort BM25 scores to get ranks
        bm25_order = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )
        bm25_rank: Dict[str, int] = {}
        for rank, idx in enumerate(bm25_order):
            bm25_rank[dense_results[idx].chunk_id] = rank

        # Compute fused score
        fused: Dict[str, float] = defaultdict(float)
        all_ids = set(dense_rank.keys()) | set(bm25_rank.keys())
        for cid in all_ids:
            d_rank = dense_rank.get(cid, len(dense_results))
            b_rank = bm25_rank.get(cid, len(dense_results))
            fused[cid] = (
                self.alpha * (1.0 / (self.RRF_K + d_rank))
                + (1 - self.alpha) * (1.0 / (self.RRF_K + b_rank))
            )

        # 5. Sort by fused score and map back to SearchResult
        result_map = {r.chunk_id: r for r in dense_results}
        sorted_ids = sorted(fused, key=fused.get, reverse=True)

        fused_results = []
        for cid in sorted_ids[:top_k]:
            r = result_map[cid]
            # Overwrite score with fused score for downstream consumers
            fused_results.append(SearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_index=r.chunk_index,
                text=r.text,
                start_page=r.start_page,
                end_page=r.end_page,
                score=fused[cid],
                token_count=r.token_count,
            ))

        logger.info(
            "Fusion retrieval: %d dense → %d fused (alpha=%.2f)",
            len(dense_results), len(fused_results), self.alpha,
        )
        return fused_results

    async def search_with_trace(
        self,
        query: str,
        query_embedding: np.ndarray,
        top_k: int = 20,
        document_filter: Optional[UUID] = None,
    ) -> Tuple[List[SearchResult], Dict[str, Any]]:
        """Same as search, plus per-chunk dense/BM25 ranks and fused score for UI trace."""
        dense_results = await self.vector_store.search(
            query_embedding,
            top_k=top_k * 2,
            document_filter=document_filter,
        )
        if not dense_results:
            return [], {
                "mode": "fusion",
                "fusion_alpha": self.alpha,
                "rrf_k": self.RRF_K,
                "chunks": [],
            }

        self.build_bm25_index(dense_results)
        query_tokens = self._tokenise(query)
        bm25_scores = self._bm25_index.get_scores(query_tokens)

        dense_rank: Dict[str, int] = {}
        for rank, r in enumerate(dense_results):
            dense_rank[r.chunk_id] = rank

        bm25_order = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )
        bm25_rank: Dict[str, int] = {}
        for rank, idx in enumerate(bm25_order):
            bm25_rank[dense_results[idx].chunk_id] = rank

        fused: Dict[str, float] = defaultdict(float)
        all_ids = set(dense_rank.keys()) | set(bm25_rank.keys())
        for cid in all_ids:
            d_rank = dense_rank.get(cid, len(dense_results))
            b_rank = bm25_rank.get(cid, len(dense_results))
            fused[cid] = (
                self.alpha * (1.0 / (self.RRF_K + d_rank))
                + (1 - self.alpha) * (1.0 / (self.RRF_K + b_rank))
            )

        result_map = {r.chunk_id: r for r in dense_results}
        sorted_ids = sorted(fused, key=fused.get, reverse=True)

        chunk_traces: List[Dict[str, Any]] = []
        fused_results: List[SearchResult] = []
        for cid in sorted_ids[:top_k]:
            r = result_map[cid]
            fused_results.append(
                SearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    chunk_index=r.chunk_index,
                    text=r.text,
                    start_page=r.start_page,
                    end_page=r.end_page,
                    score=fused[cid],
                    token_count=r.token_count,
                )
            )
            chunk_traces.append(
                {
                    "chunk_id": cid,
                    "dense_rank": dense_rank.get(cid, -1),
                    "bm25_rank": bm25_rank.get(cid, -1),
                    "fused_score": round(float(fused[cid]), 6),
                }
            )

        trace: Dict[str, Any] = {
            "mode": "fusion",
            "fusion_alpha": self.alpha,
            "rrf_k": self.RRF_K,
            "chunks": chunk_traces,
        }
        return fused_results, trace

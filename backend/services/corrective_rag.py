"""
Corrective RAG (CRAG) — self-check loop with web search fallback.

After initial retrieval, the LLM evaluates whether the retrieved
chunks actually answer the query. If confidence is low, it:
1. Rewrites the query for better retrieval.
2. Falls back to web search (Brave/DuckDuckGo) for external context.
3. Merges external results with local retrieval.

This prevents the common RAG failure mode of confidently answering
from irrelevant chunks.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from core.config import get_settings
from services.vector_store import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class CRAGResult:
    """Outcome of the corrective RAG evaluation."""
    action: str  # "use_local", "augment_web", "web_only"
    local_chunks: List[SearchResult]
    web_results: List[dict] = field(default_factory=list)
    rewritten_query: Optional[str] = None
    confidence: float = 0.0


RELEVANCE_EVAL_PROMPT = """You are evaluating whether retrieved document chunks are relevant to a user's question.

QUESTION: {query}

RETRIEVED CHUNKS:
{chunks}

For each chunk, respond with RELEVANT or IRRELEVANT on a separate line.
Then on the final line, write OVERALL: HIGH, MEDIUM, or LOW to indicate
overall retrieval confidence.

Example response:
1. RELEVANT
2. IRRELEVANT
3. RELEVANT
OVERALL: MEDIUM
"""

QUERY_REWRITE_PROMPT = """The following question did not retrieve good results from our document database.
Rewrite it as a better search query — more specific, using likely document terminology.

Original question: {query}

Rewritten query (just the query, nothing else):"""


class CorrectiveRAG:
    """
    Self-correcting retrieval pipeline.

    Evaluates retrieval quality and falls back to web search
    when local retrieval is insufficient.
    """

    def __init__(self, llm_router):
        self.llm = llm_router
        self.settings = get_settings()

    async def evaluate_and_correct(
        self,
        query: str,
        search_results: List[SearchResult],
        model: Optional[str] = None,
    ) -> CRAGResult:
        """Evaluate retrieval quality and decide next action.

        Returns a CRAGResult with the recommended action and
        any supplementary web results.
        """
        if not search_results:
            # Nothing retrieved — go straight to web
            web = await self._web_search(query)
            return CRAGResult(
                action="web_only",
                local_chunks=[],
                web_results=web,
                confidence=0.0,
            )

        # Evaluate relevance of retrieved chunks
        confidence, relevant_chunks = await self._evaluate_relevance(
            query, search_results, model
        )

        if confidence >= 0.7:
            # High confidence — use local results as-is
            return CRAGResult(
                action="use_local",
                local_chunks=relevant_chunks or search_results,
                confidence=confidence,
            )

        if confidence >= 0.3:
            # Medium — augment with web results
            web = await self._web_search(query)
            return CRAGResult(
                action="augment_web",
                local_chunks=relevant_chunks or search_results,
                web_results=web,
                confidence=confidence,
            )

        # Low confidence — rewrite query and try web
        rewritten = await self._rewrite_query(query, model)
        web = await self._web_search(rewritten or query)
        return CRAGResult(
            action="web_only",
            local_chunks=[],
            web_results=web,
            rewritten_query=rewritten,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Relevance evaluation via LLM
    # ------------------------------------------------------------------

    async def _evaluate_relevance(
        self,
        query: str,
        results: List[SearchResult],
        model: Optional[str] = None,
    ) -> tuple[float, List[SearchResult]]:
        """Ask the LLM to judge each chunk's relevance."""
        chunk_text = "\n\n".join(
            f"{i+1}. {r.text[:500]}" for i, r in enumerate(results[:5])
        )
        prompt = RELEVANCE_EVAL_PROMPT.format(query=query, chunks=chunk_text)

        try:
            response = await self.llm.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=200,
                model=model,
            )
            return self._parse_relevance(response.text, results)
        except Exception as e:
            logger.warning("CRAG relevance eval failed: %s", e)
            # Fallback: assume medium confidence based on vector scores
            avg_score = sum(r.score for r in results) / len(results)
            return avg_score, results

    @staticmethod
    def _parse_relevance(
        llm_output: str, results: List[SearchResult]
    ) -> tuple[float, List[SearchResult]]:
        """Parse the LLM's relevance judgements."""
        lines = llm_output.strip().split("\n")
        relevant = []

        for i, line in enumerate(lines):
            if i >= len(results):
                break
            if "RELEVANT" in line.upper() and "IRRELEVANT" not in line.upper():
                relevant.append(results[i])

        # Parse overall confidence
        confidence = 0.5
        for line in reversed(lines):
            upper = line.upper()
            if "HIGH" in upper:
                confidence = 0.9
                break
            elif "MEDIUM" in upper:
                confidence = 0.5
                break
            elif "LOW" in upper:
                confidence = 0.2
                break

        return confidence, relevant

    # ------------------------------------------------------------------
    # Query rewriting
    # ------------------------------------------------------------------

    async def _rewrite_query(
        self, query: str, model: Optional[str] = None
    ) -> Optional[str]:
        """Rewrite the query for better retrieval."""
        try:
            response = await self.llm.generate(
                prompt=QUERY_REWRITE_PROMPT.format(query=query),
                temperature=0.3,
                max_tokens=100,
                model=model,
            )
            rewritten = response.text.strip().strip('"').strip("'")
            logger.info("CRAG rewrote query: '%s' → '%s'", query, rewritten)
            return rewritten
        except Exception as e:
            logger.warning("CRAG query rewrite failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Web search fallback
    # ------------------------------------------------------------------

    async def _web_search(self, query: str, max_results: int = 3) -> List[dict]:
        """Search the web using DuckDuckGo Lite (no API key required).

        Returns a list of {title, url, snippet} dicts.
        Falls back gracefully if network is unavailable.
        """
        try:
            return await self._duckduckgo_search(query, max_results)
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return []

    @staticmethod
    async def _duckduckgo_search(query: str, max_results: int) -> List[dict]:
        """Lightweight DuckDuckGo search via the HTML lite endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "RAG-v2.1/1.0"},
            )
            resp.raise_for_status()

        # Parse results from HTML (basic extraction)
        import re
        results = []
        # Find result blocks
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL,
        )
        titles = re.findall(
            r'class="result__a"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL,
        )
        urls = re.findall(
            r'class="result__url"[^>]*href="([^"]*)"',
            resp.text,
        )

        for i in range(min(max_results, len(snippets))):
            results.append({
                "title": re.sub(r"<[^>]+>", "", titles[i]) if i < len(titles) else "",
                "url": urls[i] if i < len(urls) else "",
                "snippet": re.sub(r"<[^>]+>", "", snippets[i]).strip(),
            })

        if len(results) == 0 and resp.status_code == 200:
            logger.warning(
                "DuckDuckGo HTML structure may have changed; no results parsed. "
                "Consider using duckduckgo-search package for robust parsing."
            )
        return results

    @staticmethod
    def format_web_context(web_results: List[dict]) -> str:
        """Format web results as context for the LLM prompt."""
        if not web_results:
            return ""
        parts = ["\n\n--- Web Search Results ---\n"]
        for i, r in enumerate(web_results, 1):
            parts.append(f"[Web {i}] {r.get('title', 'Untitled')}")
            parts.append(f"URL: {r.get('url', '')}")
            parts.append(f"{r.get('snippet', '')}\n")
        return "\n".join(parts)

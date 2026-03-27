"""
HyDE — Hypothetical Document Embedding.

When a user query is short or vague, the embedding may not match
well against document chunks. HyDE asks the LLM to generate a
*hypothetical answer* first, then embeds that answer for retrieval.

The intuition: a hypothetical answer is linguistically closer to
the actual document text than a bare question is, so embedding
similarity improves.

Trade-off: one extra LLM call per query. Use selectively.
"""

import logging
from typing import Optional

import numpy as np

from core.config import get_settings

logger = logging.getLogger(__name__)

HYDE_SYSTEM_PROMPT = (
    "You are a research assistant. Given a question, write a short paragraph "
    "(3-5 sentences) that would be a plausible answer found in a document. "
    "Do NOT say 'I don't know'. Just write the answer as if it were an "
    "excerpt from a relevant document. Be factual and specific."
)


class HyDEService:
    """
    Generates hypothetical document embeddings for improved retrieval.

    Usage:
        hyde = HyDEService(llm_router, embedding_service)
        enhanced_embedding = await hyde.generate(query)
        # Use enhanced_embedding instead of raw query embedding
    """

    def __init__(self, llm_router, embedding_service):
        self.llm = llm_router
        self.embedder = embedding_service
        self.settings = get_settings()

    async def generate(
        self,
        query: str,
        model: Optional[str] = None,
    ) -> np.ndarray:
        """Generate a HyDE embedding for the given query.

        Returns:
            A single embedding vector that is the *average* of:
            - the original query embedding
            - the hypothetical answer embedding
            This blended approach retains the original intent while
            adding document-like vocabulary.
        """
        # Generate hypothetical answer
        try:
            response = await self.llm.generate(
                prompt=query,
                system_message=HYDE_SYSTEM_PROMPT,
                temperature=0.7,  # slightly creative for diverse hypotheticals
                max_tokens=300,
                model=model,
            )
            hypothetical_answer = response.text
            logger.info("HyDE generated hypothetical (%d chars)", len(hypothetical_answer))
        except Exception as e:
            logger.warning("HyDE generation failed, using raw query: %s", e)
            return await self.embedder.embed_query(query)

        # Embed both the query and the hypothetical answer
        embeddings = await self.embedder.embed([query, hypothetical_answer])

        # Average the two embeddings — keeps original intent
        # while adding document-style vocabulary
        blended = np.mean(embeddings, axis=0)

        # Normalise for cosine similarity
        norm = np.linalg.norm(blended)
        if norm > 0:
            blended = blended / norm

        return blended

    async def should_use_hyde(self, query: str) -> bool:
        """Heuristic: use HyDE for short/vague queries where raw embedding
        is unlikely to match well against document chunks."""
        min_words = getattr(self.settings, "HYDE_MIN_WORDS", 8)
        use_for_questions = getattr(self.settings, "HYDE_USE_FOR_QUESTIONS", True)
        word_count = len(query.split())
        return (
            word_count < min_words
            or (use_for_questions and query.strip().endswith("?"))
        )

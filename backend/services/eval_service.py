"""
RAG evaluation service using DeepEval metrics.

Measures retrieval and generation quality with standardised metrics:
- Faithfulness: does the answer only use info from retrieved context?
- Answer Relevancy: does the answer actually address the question?
- Contextual Precision: are the most relevant chunks ranked highest?
- Contextual Recall: did we retrieve all the info needed to answer?

These metrics replace "eyeballing" with quantitative, repeatable
evaluation that can be tracked over time or across config changes.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Single evaluation result."""
    metric: str
    score: float
    reason: str = ""


@dataclass
class RAGEvaluation:
    """Full evaluation of a single RAG query."""
    query: str
    answer: str
    context_texts: List[str]
    metrics: List[EvalResult] = field(default_factory=list)
    overall_score: float = 0.0

    @property
    def passed(self) -> bool:
        return self.overall_score >= 0.5


def _deepeval_available() -> bool:
    try:
        import deepeval  # noqa: F401
        return True
    except ImportError:
        return False


class RAGEvaluator:
    """
    Evaluates RAG pipeline quality using DeepEval.

    Usage:
        evaluator = RAGEvaluator()
        result = await evaluator.evaluate(query, answer, context_texts)
        print(result.overall_score, result.metrics)

    If DeepEval is not installed, falls back to heuristic scoring.
    """

    def __init__(self, model: str = None):
        self.settings = get_settings()
        self.model = model

    async def evaluate(
        self,
        query: str,
        answer: str,
        context_texts: List[str],
        expected_answer: Optional[str] = None,
    ) -> RAGEvaluation:
        """Run all evaluation metrics on a single RAG response."""
        evaluation = RAGEvaluation(
            query=query,
            answer=answer,
            context_texts=context_texts,
        )

        if _deepeval_available():
            evaluation.metrics = self._evaluate_with_deepeval(
                query, answer, context_texts, expected_answer
            )
        else:
            logger.info("DeepEval not installed, using heuristic evaluation")
            evaluation.metrics = self._evaluate_heuristic(
                query, answer, context_texts
            )

        if evaluation.metrics:
            evaluation.overall_score = sum(
                m.score for m in evaluation.metrics
            ) / len(evaluation.metrics)

        return evaluation

    # ------------------------------------------------------------------
    # DeepEval-based evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_with_deepeval(
        query: str,
        answer: str,
        context_texts: List[str],
        expected_answer: Optional[str] = None,
    ) -> List[EvalResult]:
        """Run DeepEval metrics. Requires `pip install deepeval`."""
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import (
            FaithfulnessMetric,
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            ContextualRecallMetric,
        )

        test_case = LLMTestCase(
            input=query,
            actual_output=answer,
            retrieval_context=context_texts,
            expected_output=expected_answer,
        )

        results: List[EvalResult] = []

        # Faithfulness — is the answer grounded in context?
        try:
            faithfulness = FaithfulnessMetric(threshold=0.7)
            faithfulness.measure(test_case)
            results.append(EvalResult(
                metric="faithfulness",
                score=faithfulness.score,
                reason=faithfulness.reason or "",
            ))
        except Exception as e:
            logger.warning("Faithfulness metric failed: %s", e)

        # Answer Relevancy — does the answer address the question?
        try:
            relevancy = AnswerRelevancyMetric(threshold=0.7)
            relevancy.measure(test_case)
            results.append(EvalResult(
                metric="answer_relevancy",
                score=relevancy.score,
                reason=relevancy.reason or "",
            ))
        except Exception as e:
            logger.warning("Answer relevancy metric failed: %s", e)

        # Contextual Precision — are relevant chunks ranked highly?
        if expected_answer:
            try:
                precision = ContextualPrecisionMetric(threshold=0.7)
                precision.measure(test_case)
                results.append(EvalResult(
                    metric="contextual_precision",
                    score=precision.score,
                    reason=precision.reason or "",
                ))
            except Exception as e:
                logger.warning("Contextual precision metric failed: %s", e)

        # Contextual Recall — did we retrieve everything needed?
        if expected_answer:
            try:
                recall = ContextualRecallMetric(threshold=0.7)
                recall.measure(test_case)
                results.append(EvalResult(
                    metric="contextual_recall",
                    score=recall.score,
                    reason=recall.reason or "",
                ))
            except Exception as e:
                logger.warning("Contextual recall metric failed: %s", e)

        return results

    # ------------------------------------------------------------------
    # Heuristic fallback (no DeepEval dependency)
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_heuristic(
        query: str, answer: str, context_texts: List[str]
    ) -> List[EvalResult]:
        """Lightweight heuristic evaluation when DeepEval is not installed."""
        results: List[EvalResult] = []

        # Faithfulness heuristic: word overlap between answer and context
        context_words = set()
        for ctx in context_texts:
            context_words.update(ctx.lower().split())
        answer_words = set(answer.lower().split())

        if answer_words:
            overlap = len(answer_words & context_words) / len(answer_words)
            results.append(EvalResult(
                metric="faithfulness_heuristic",
                score=min(overlap * 1.2, 1.0),
                reason=f"{overlap:.0%} of answer words found in context",
            ))

        # Relevancy heuristic: query term coverage in answer
        query_words = set(query.lower().split()) - {"the", "a", "an", "is", "are", "was", "were", "what", "how", "why", "when", "where", "which"}
        if query_words:
            query_coverage = len(query_words & answer_words) / len(query_words)
            results.append(EvalResult(
                metric="relevancy_heuristic",
                score=query_coverage,
                reason=f"{query_coverage:.0%} of query terms found in answer",
            ))

        # Length sanity — penalise very short or very long answers
        word_count = len(answer.split())
        if word_count < 10:
            length_score = 0.3
        elif word_count > 1000:
            length_score = 0.6
        else:
            length_score = 0.9
        results.append(EvalResult(
            metric="length_sanity",
            score=length_score,
            reason=f"Answer has {word_count} words",
        ))

        return results

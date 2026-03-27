"""
Chat and RAG query API routes.

Handles querying documents with RAG, conversation management.
"""

import time
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from models.database import (
    Document, Conversation, Message, MessageRole,
    QueryLog, DocumentStatus,
)
from models.schemas import (
    QueryRequest, QueryResponse, ConversationResponse,
    MessageResponse, CitationResponse, RetrievedChunk,
    QueryLogEntry, AvailableModel, AvailableModelsResponse,
    RetrievalTrace, RetrievalTraceChunk,
)
from services.embedding_service import get_embedding_service
from services.vector_store import create_vector_store, SearchResult
from services.rerank_service import RerankService, vector_order_top_k
from services.citation_service import CitationService, RetrievedChunk as CitationRetrievedChunk
from services.llm_router import get_llm_router, LLMResponse
from services.hyde_service import HyDEService
from services.corrective_rag import CorrectiveRAG
from services.eval_service import RAGEvaluator
from core.config import get_settings
from api.dependencies import get_db, get_session_maker

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _build_trace_chunk_map(
    search_results: List[SearchResult],
    fusion_meta: Optional[Dict[str, Any]],
    fusion_enabled: bool,
) -> Dict[str, RetrievalTraceChunk]:
    """Map chunk_id → trace row from fusion diagnostics or dense-only ranks."""
    out: Dict[str, RetrievalTraceChunk] = {}
    if fusion_enabled and fusion_meta and fusion_meta.get("chunks"):
        for row in fusion_meta["chunks"]:
            cid = row["chunk_id"]
            out[cid] = RetrievalTraceChunk(
                chunk_id=cid,
                dense_rank=int(row.get("dense_rank", -1)),
                bm25_rank=int(row.get("bm25_rank", -1)),
                fused_score=row.get("fused_score"),
            )
        return out
    for i, r in enumerate(search_results):
        out[r.chunk_id] = RetrievalTraceChunk(
            chunk_id=r.chunk_id,
            dense_rank=i,
            bm25_rank=-1,
            dense_score=float(r.score),
        )
    return out


def _assemble_retrieval_trace(
    reranked: List,  # SearchResult or RerankedResult (both expose chunk_id)
    trace_map: Dict[str, RetrievalTraceChunk],
    hyde_used: bool,
    fusion_enabled: bool,
    fusion_meta: Optional[Dict[str, Any]],
    crag_action: Optional[str],
    web_augmented: bool,
) -> RetrievalTrace:
    """Order trace rows to match reranked chunks shown to the LLM."""
    chunks: List[RetrievalTraceChunk] = []
    for r in reranked:
        if r.chunk_id in trace_map:
            chunks.append(trace_map[r.chunk_id])
        else:
            chunks.append(
                RetrievalTraceChunk(chunk_id=r.chunk_id, dense_rank=-1, bm25_rank=-1)
            )
    mode = "fusion" if fusion_enabled else "dense"
    return RetrievalTrace(
        hyde_used=hyde_used,
        fusion_enabled=fusion_enabled,
        fusion_alpha=fusion_meta.get("fusion_alpha") if fusion_meta else None,
        rrf_k=fusion_meta.get("rrf_k") if fusion_meta else None,
        mode=mode,
        crag_action=crag_action,
        web_augmented=web_augmented,
        chunks=chunks,
    )


# System prompt template
RAG_SYSTEM_PROMPT = """You are a research assistant answering questions based on provided documents.

INSTRUCTIONS:
1. Answer ONLY using the information in the provided context
2. If the answer is not in the context, respond: "The information is not found in the provided documents."
3. Cite your sources using [1], [2], etc. referring to the context numbers
4. Be concise but thorough
5. Use markdown formatting for clarity
6. You can query documents, extract entities, and cite sources. Use citations [1], [2] for evidence.

CONTEXT:
{context}

The user's question will be provided after this context. Answer it based ONLY on the information above."""


async def _build_context_injection(
    db: AsyncSession,
    conversation_id: UUID,
    exclude_message_id: UUID,
    document_id: Optional[UUID],
    max_prior_turns: int = 5,
) -> str:
    """Build dynamic context: prior turns, document-in-focus."""
    parts = []

    # Prior conversation (exclude current user message we just added)
    prior_result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.id != exclude_message_id,
        )
        .order_by(Message.timestamp)
    )
    prior_msgs = prior_result.scalars().all()[-2 * max_prior_turns :]  # last N turns
    if prior_msgs:
        conv_lines = []
        for m in prior_msgs:
            role = "User" if m.role == MessageRole.USER else "Assistant"
            conv_lines.append(f"{role}: {m.content[:200]}{'...' if len(m.content) > 200 else ''}")
        parts.append("RECENT CONVERSATION:\n" + "\n".join(conv_lines) + "\n")

    # Document in focus
    if document_id:
        doc_result = await db.execute(
            select(Document.original_name).where(Document.id == document_id)
        )
        doc_name = doc_result.scalar_one_or_none()
        if doc_name:
            parts.append(f"DOCUMENT IN FOCUS: {doc_name}\n")

    return "\n".join(parts) if parts else ""


def format_context_for_prompt(chunks: List[CitationRetrievedChunk]) -> str:
    """Format retrieved chunks for LLM prompt."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source_info = f"Source [{i}]"
        if hasattr(chunk, 'document_name'):
            source_info += f" - {chunk.document_name}"
        if hasattr(chunk, 'start_page'):
            page_str = (
                f"Page {chunk.start_page}"
                if chunk.start_page == chunk.end_page
                else f"Pages {chunk.start_page}-{chunk.end_page}"
            )
            source_info += f", {page_str}"
        
        parts.append(f"{source_info}:\n{chunk.text}")
    
    return "\n\n---\n\n".join(parts)


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Main RAG query endpoint.
    
    Pipeline:
    1. Embed query
    2. Vector search (top-K)
    3. Re-rank
    4. Generate answer with LLM
    5. Validate citations
    6. Log query
    7. Return response with citations
    """
    settings = get_settings()
    start_time = time.time()
    query_run_id = str(uuid4())
    
    # Get or create conversation
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == request.conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        workspace_id = None
        if request.document_id:
            ws_row = await db.execute(
                select(Document.workspace_id).where(Document.id == request.document_id)
            )
            workspace_id = ws_row.scalar_one_or_none()
        conversation = Conversation(
            id=uuid4(),
            document_id=request.document_id,
            workspace_id=workspace_id,
        )
        db.add(conversation)
        await db.flush()
    
    # Save user message
    user_message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=request.query
    )
    db.add(user_message)
    
    # 1. Embed query — optionally enhanced with HyDE
    embedding_service = get_embedding_service()
    llm_router = get_llm_router()

    hyde_used = False
    fusion_enabled = settings.ENABLE_FUSION_RETRIEVAL
    crag_action = None
    web_augmented = False

    if settings.ENABLE_HYDE:
        hyde = HyDEService(llm_router, embedding_service)
        if await hyde.should_use_hyde(request.query):
            query_embedding = await hyde.generate(request.query, model=request.model)
            hyde_used = True
        else:
            query_embedding = await embedding_service.embed_query(request.query)
    else:
        query_embedding = await embedding_service.embed_query(request.query)
    
    # 2. Retrieval — fusion (BM25 + dense) or dense-only (+ capture trace for UI)
    vector_store = create_vector_store()
    fusion_meta: Optional[Dict[str, Any]] = None

    if settings.ENABLE_FUSION_RETRIEVAL:
        from services.fusion_retrieval import FusionRetriever

        fusion = FusionRetriever(vector_store, alpha=settings.FUSION_ALPHA)
        search_results, fusion_meta = await fusion.search_with_trace(
            query=request.query,
            query_embedding=query_embedding,
            top_k=settings.TOP_K_VECTOR_SEARCH,
            document_filter=request.document_id,
        )
    else:
        search_results = await vector_store.search(
            query_embedding,
            top_k=settings.TOP_K_VECTOR_SEARCH,
            document_filter=request.document_id,
        )

    trace_map = _build_trace_chunk_map(
        search_results,
        fusion_meta,
        settings.ENABLE_FUSION_RETRIEVAL,
    )

    # 2b. Corrective RAG — evaluate retrieval and augment if needed
    web_context = ""
    if settings.ENABLE_CORRECTIVE_RAG and search_results:
        crag = CorrectiveRAG(llm_router)
        crag_result = await crag.evaluate_and_correct(
            request.query, search_results, model=request.model
        )
        crag_action = crag_result.action
        if crag_result.action in ("augment_web", "web_only"):
            web_context = CorrectiveRAG.format_web_context(crag_result.web_results)
            web_augmented = True
        if crag_result.action == "web_only":
            search_results = []  # discard low-confidence local results
        elif crag_result.local_chunks:
            search_results = crag_result.local_chunks
    
    if not search_results and not web_context:
        # No relevant chunks found
        answer = "No relevant information found in the documents."
        
        assistant_message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            model_used="none",
            latency_ms=int((time.time() - start_time) * 1000)
        )
        db.add(assistant_message)
        await db.commit()

        empty_trace = RetrievalTrace(
            hyde_used=hyde_used,
            fusion_enabled=fusion_enabled,
            fusion_alpha=fusion_meta.get("fusion_alpha") if fusion_meta else None,
            rrf_k=fusion_meta.get("rrf_k") if fusion_meta else None,
            mode="fusion" if fusion_enabled else "dense",
            crag_action=crag_action,
            web_augmented=web_augmented,
            chunks=[],
        )

        return QueryResponse(
            answer=answer,
            citations=[],
            retrieved_chunks=[],
            conversation_id=conversation.id,
            model_used="none",
            latency_ms=assistant_message.latency_ms,
            token_count_prompt=0,
            token_count_response=0,
            retrieval_trace=empty_trace,
        )
    
    # Get document names for search results
    doc_ids = list(set([r.document_id for r in search_results]))
    result = await db.execute(
        select(Document.id, Document.original_name)
        .where(Document.id.in_(doc_ids))
    )
    doc_name_map = {str(row.id): row.original_name for row in result.all()}
    
    # Add document names to search results
    for r in search_results:
        r.document_name = doc_name_map.get(str(r.document_id), "Unknown")
    
    # 3. Re-rank (cross-encoder) or dense-order only — latter avoids slow CPU MiniLM on ~20 pairs
    if settings.ENABLE_CROSS_ENCODER_RERANK:
        rerank_service = RerankService()
        reranked = await rerank_service.rerank_with_fallback(
            request.query,
            search_results,
            doc_name_map,
        )
    else:
        reranked = vector_order_top_k(search_results, doc_name_map, settings.TOP_K_RERANK)
    
    # Convert to citation service format
    citation_chunks = [
        CitationRetrievedChunk(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_name=r.document_name,
            text=r.text,
            start_page=r.start_page,
            end_page=r.end_page,
            score=r.combined_score
        )
        for r in reranked
    ]
    
    # 4. Generate answer
    context_str = format_context_for_prompt(citation_chunks)
    # Append web context from CRAG if available
    if web_context:
        context_str += web_context
    # Context injection: prior turns + document-in-focus
    injected = await _build_context_injection(
        db, conversation.id, user_message.id, request.document_id
    )
    if injected:
        context_str = injected + "\n" + context_str
    # Use custom prompt if provided, otherwise use default
    prompt_template = request.system_prompt if request.system_prompt else RAG_SYSTEM_PROMPT

    # Format prompt with context and append user question
    try:
        system_prompt = prompt_template.format(context=context_str)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid system_prompt template. Use only {context} as a placeholder.",
        ) from exc
    full_prompt = f"{system_prompt}\n\nQUESTION: {request.query}\n\nANSWER:"
    
    llm_response: LLMResponse = await llm_router.generate(
        prompt=full_prompt,
        system_message=None,  # Already in prompt
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        model=request.model
    )
    
    # 5. Validate citations
    citation_service = CitationService()
    validation = citation_service.validate_answer(
        llm_response.text,
        citation_chunks
    )
    
    # 5b. RAG quality evaluation (background, non-blocking)
    async def _run_eval():
        try:
            evaluator = RAGEvaluator()
            eval_result = await evaluator.evaluate(
                query=request.query,
                answer=llm_response.text,
                context_texts=[c.text for c in citation_chunks],
            )
            logger.info(
                "RAG eval: overall=%.2f metrics=%s",
                eval_result.overall_score,
                [(m.metric, f"{m.score:.2f}") for m in eval_result.metrics],
            )
        except Exception as e:
            logger.warning("RAG eval failed: %s", e, exc_info=True)

    background_tasks.add_task(_run_eval)
    
    # 6. Save assistant message
    assistant_message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=llm_response.text,
        citations=[
            {
                "document_id": str(c.document_id),
                "document_name": c.document_name,
                "chunk_id": c.chunk_id,
                "start_page": c.start_page,
                "end_page": c.end_page,
                "evidence_quote": c.evidence_quote,
                "relevance_score": c.relevance_score
            }
            for c in validation.citations
        ],
        retrieved_chunks=[
            {
                "chunk_id": c.chunk_id,
                "document_id": str(c.document_id),
                "document_name": c.document_name,
                "text": c.text[:500],  # Truncate for storage
                "start_page": c.start_page,
                "end_page": c.end_page,
                "score": c.score
            }
            for c in citation_chunks
        ],
        model_used=llm_response.model_used,
        latency_ms=llm_response.latency_ms,
        token_count_prompt=llm_response.prompt_tokens,
        token_count_response=llm_response.completion_tokens
    )
    db.add(assistant_message)
    
    # Update conversation timestamp
    conversation.updated_at = func.now()
    
    await db.commit()
    
    # 7. Log query (in background)
    top_rerank = float(reranked[0].combined_score) if reranked else None
    rag_meta = {
        "query_run_id": query_run_id,
        "stability_profile": settings.RUNTIME_STABILITY_PROFILE,
        "config_fingerprint": settings.stability_fingerprint(),
        "hyde_used": hyde_used,
        "fusion_enabled": fusion_enabled,
        "crag_action": crag_action,
        "top_rerank_score": top_rerank,
    }
    background_tasks.add_task(
        log_query_background,
        request.query,
        request.document_id,
        [r.chunk_id for r in reranked],
        full_prompt,
        llm_response.text,
        llm_response.latency_ms,
        llm_response.prompt_tokens,
        llm_response.completion_tokens,
        llm_response.model_used,
        rag_meta,
    )
    
    # Build response
    retrieved_chunks_response = [
        RetrievedChunk(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_name=r.document_name,
            text=r.text[:500],  # Truncate for response
            start_page=r.start_page,
            end_page=r.end_page,
            score=r.combined_score
        )
        for r in reranked
    ]
    
    citations_response = [
        CitationResponse(
            document_id=c.document_id,
            document_name=c.document_name,
            chunk_id=c.chunk_id,
            start_page=c.start_page,
            end_page=c.end_page,
            evidence_quote=c.evidence_quote,
            relevance_score=c.relevance_score
        )
        for c in validation.citations
    ]

    retrieval_trace = _assemble_retrieval_trace(
        reranked,
        trace_map,
        hyde_used,
        fusion_enabled,
        fusion_meta,
        crag_action,
        web_augmented,
    )

    return QueryResponse(
        answer=llm_response.text,
        citations=citations_response,
        retrieved_chunks=retrieved_chunks_response,
        conversation_id=conversation.id,
        model_used=llm_response.model_used,
        latency_ms=llm_response.latency_ms,
        token_count_prompt=llm_response.prompt_tokens,
        token_count_response=llm_response.completion_tokens,
        retrieval_trace=retrieval_trace,
    )


async def log_query_background(
    query: str,
    document_id: Optional[UUID],
    chunk_ids: List[str],
    prompt: str,
    response: str,
    latency_ms: int,
    token_count_prompt: int,
    token_count_response: int,
    model_used: str,
    rag_meta: Optional[dict] = None,
):
    """Log query to database."""
    async_session = get_session_maker()
    async with async_session() as db:
        try:
            log_entry = QueryLog(
                id=uuid4(),
                query=query,
                document_id=document_id,
                retrieved_chunk_ids=chunk_ids,
                prompt_sent=prompt,
                response_received=response,
                latency_ms=latency_ms,
                token_count_prompt=token_count_prompt,
                token_count_response=token_count_response,
                model_used=model_used,
                rag_meta=rag_meta,
            )
            db.add(log_entry)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("Query log background write failed: %s", exc, exc_info=True)


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    document_id: Optional[UUID] = Query(None, description="Filter by document"),
    db: AsyncSession = Depends(get_db)
):
    """Get conversations for a document or all conversations."""
    query = select(Conversation)
    if document_id:
        query = query.where(Conversation.document_id == document_id)
    query = query.order_by(desc(Conversation.updated_at))
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    response_list = []
    for conv in conversations:
        messages_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.timestamp)
        )
        messages = messages_result.scalars().all()
        
        response_list.append(ConversationResponse(
            id=conv.id,
            document_id=conv.document_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            messages=[
                MessageResponse(
                    id=m.id,
                    role=m.role.value,
                    content=m.content,
                    timestamp=m.timestamp,
                    citations=m.citations
                )
                for m in messages
            ]
        ))
    
    return response_list


@router.post("/conversations")
async def create_conversation(
    document_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create a new conversation."""
    if document_id:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found")
    
    conversation = Conversation(
        id=uuid4(),
        document_id=document_id
    )
    db.add(conversation)
    await db.commit()
    
    return {"id": conversation.id, "message": "Conversation created"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    await db.delete(conversation)
    await db.commit()
    
    return {"message": "Conversation deleted"}


@router.post("/evaluate")
async def evaluate_query(
    query: str,
    answer: str,
    context_texts: List[str],
    expected_answer: Optional[str] = None,
):
    """Run RAG evaluation metrics on a query/answer pair.

    Useful for benchmarking pipeline changes or testing
    specific query types against known-good answers.
    """
    evaluator = RAGEvaluator()
    result = await evaluator.evaluate(query, answer, context_texts, expected_answer)
    return {
        "overall_score": result.overall_score,
        "passed": result.passed,
        "metrics": [
            {"metric": m.metric, "score": m.score, "reason": m.reason}
            for m in result.metrics
        ],
    }


@router.get("/models", response_model=AvailableModelsResponse)
async def get_available_models():
    """Get list of available LLM models."""
    from services.llm_router import get_llm_router
    
    router = get_llm_router()
    models = router.list_available_models()
    settings = get_settings()
    
    # Convert to response format
    available_models = [
        AvailableModel(id=m["id"], name=m["name"], provider=m["provider"])
        for m in models
    ]
    
    return AvailableModelsResponse(
        models=available_models,
        default_model=settings.DEFAULT_CLOUD_MODEL,
        fast_model=settings.OPENROUTER_FAST_MODEL,
        active_provider=router.active_provider_name,
    )

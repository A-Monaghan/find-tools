"""
Query logging API routes.

Provides access to query audit logs for debugging and monitoring.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from models.database import QueryLog, Document
from models.schemas import QueryLogEntry
from api.dependencies import get_db

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/queries", response_model=List[QueryLogEntry])
async def get_query_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    document_id: Optional[UUID] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get query audit logs.
    
    Parameters:
    - limit: Maximum number of results (1-1000)
    - offset: Pagination offset
    - document_id: Filter by specific document
    - start_date: Filter from date (ISO format)
    - end_date: Filter to date (ISO format)
    """
    query = select(QueryLog)
    
    # Apply filters
    if document_id:
        query = query.where(QueryLog.document_id == document_id)
    
    if start_date:
        query = query.where(QueryLog.timestamp >= start_date)
    
    if end_date:
        query = query.where(QueryLog.timestamp <= end_date)
    
    # Order by timestamp descending (newest first)
    query = query.order_by(desc(QueryLog.timestamp))
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return [
        QueryLogEntry(
            id=log.id,
            timestamp=log.timestamp,
            query=log.query,
            document_id=log.document_id,
            retrieved_chunk_ids=log.retrieved_chunk_ids,
            prompt_sent=log.prompt_sent,
            response_received=log.response_received,
            latency_ms=log.latency_ms,
            token_count_prompt=log.token_count_prompt,
            token_count_response=log.token_count_response
        )
        for log in logs
    ]


@router.get("/queries/{log_id}", response_model=QueryLogEntry)
async def get_query_log(log_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific query log entry by ID."""
    result = await db.execute(
        select(QueryLog).where(QueryLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    
    return QueryLogEntry(
        id=log.id,
        timestamp=log.timestamp,
        query=log.query,
        document_id=log.document_id,
        retrieved_chunk_ids=log.retrieved_chunk_ids,
        prompt_sent=log.prompt_sent,
        response_received=log.response_received,
        latency_ms=log.latency_ms,
        token_count_prompt=log.token_count_prompt,
        token_count_response=log.token_count_response
    )


@router.get("/stats")
async def get_query_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get query statistics.
    
    Returns:
    - total_queries: Total number of queries
    - avg_latency_ms: Average query latency
    - total_tokens: Total tokens used (prompt + response)
    - queries_by_document: Query counts per document
    """
    # Base query
    query = select(QueryLog)
    
    if start_date:
        query = query.where(QueryLog.timestamp >= start_date)
    if end_date:
        query = query.where(QueryLog.timestamp <= end_date)
    
    # Get all logs for stats calculation
    result = await db.execute(query)
    logs = result.scalars().all()
    
    if not logs:
        return {
            "total_queries": 0,
            "avg_latency_ms": 0,
            "total_tokens": 0,
            "queries_by_document": []
        }
    
    # Calculate stats
    total_queries = len(logs)
    avg_latency = sum(log.latency_ms for log in logs) / total_queries
    total_tokens = sum(
        log.token_count_prompt + log.token_count_response 
        for log in logs
    )
    
    # Group by document
    doc_counts = {}
    for log in logs:
        doc_id = str(log.document_id) if log.document_id else "cross-document"
        doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
    
    # Get document names
    doc_ids = [UUID(did) for did in doc_counts.keys() if did != "cross-document"]
    doc_names = {}
    if doc_ids:
        result = await db.execute(
            select(Document.id, Document.original_name)
            .where(Document.id.in_(doc_ids))
        )
        doc_names = {str(row.id): row.original_name for row in result.all()}
    
    queries_by_document = [
        {
            "document_id": doc_id if doc_id != "cross-document" else None,
            "document_name": doc_names.get(doc_id, "Cross-document search"),
            "query_count": count
        }
        for doc_id, count in doc_counts.items()
    ]
    
    return {
        "total_queries": total_queries,
        "avg_latency_ms": round(avg_latency, 2),
        "total_tokens": total_tokens,
        "queries_by_document": queries_by_document
    }


@router.delete("/queries/{log_id}")
async def delete_query_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a single query log entry by ID."""
    from sqlalchemy import delete
    result = await db.execute(delete(QueryLog).where(QueryLog.id == log_id))
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"message": "Log entry deleted", "id": str(log_id)}


@router.delete("/queries")
async def clear_query_logs(
    before_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Clear query logs.
    
    Parameters:
    - before_date: Only delete logs before this date (if not specified, deletes all)
    """
    from sqlalchemy import delete
    
    query = delete(QueryLog)
    
    if before_date:
        query = query.where(QueryLog.timestamp < before_date)
    
    result = await db.execute(query)
    await db.commit()
    
    deleted_count = result.rowcount
    
    return {
        "message": f"Deleted {deleted_count} log entries",
        "deleted_count": deleted_count
    }
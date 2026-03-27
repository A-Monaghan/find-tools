"""
Staged document ingestion: parse → chunk → embed → index (+ optional graph).
Single entrypoint for upload and librarian rechunk flows.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from models.database import Chunk, Document, DocumentStatus
from services.chunk_preset_service import get_chunk_preset
from services.docling_service import get_document_processor
from services.embedding_service import get_embedding_service
from services.vector_store import create_vector_store

logger = logging.getLogger(__name__)


async def _delete_document_chunks(db: AsyncSession, document_id: UUID) -> None:
    """Remove Postgres chunks; caller deletes vectors separately."""
    await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await db.flush()


async def run_document_ingest(
    db: AsyncSession,
    document_id: UUID,
    file_path: Path,
    *,
    chunk_preset_id: Optional[str] = None,
    delete_existing_vectors: bool = False,
) -> None:
    """
    Full ingest: parse with Docling or PyMuPDF, chunk with preset, embed, upsert to Qdrant/pgvector.

    delete_existing_vectors: True for rechunk — wipes DB chunks + vector points first.
    """
    settings = get_settings()
    preset = get_chunk_preset(chunk_preset_id)

    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one()
    document.chunk_preset_id = preset.id
    document.ingest_stage = "parse"
    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    await db.commit()

    try:
        if delete_existing_vectors:
            document.ingest_stage = "cleanup"
            await db.commit()
            vs = create_vector_store()
            await vs.delete_document(document_id)
            await _delete_document_chunks(db, document_id)
            await db.commit()

        processor = get_document_processor(file_path)
        parser_name = type(processor).__name__

        document.ingest_stage = "parse"
        await db.commit()

        t0 = time.perf_counter()
        parsed, chunks = await processor.process_file(
            file_path,
            chunk_size=preset.chunk_size,
            overlap=preset.overlap,
            strategy=preset.strategy,
        )
        logger.info(
            "ingest_parse document_id=%s preset=%s parser=%s duration_ms=%d pages=%d chunks=%d",
            document_id,
            preset.id,
            parser_name,
            int((time.perf_counter() - t0) * 1000),
            parsed.total_pages,
            len(chunks),
        )

        document = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one()
        document.total_pages = parsed.total_pages
        document.ingest_stage = "embed"
        await db.commit()

        embedding_service = get_embedding_service()
        texts = [c.text for c in chunks]
        t1 = time.perf_counter()
        embeddings = await embedding_service.embed(texts)
        logger.info(
            "ingest_embed document_id=%s duration_ms=%d",
            document_id,
            int((time.perf_counter() - t1) * 1000),
        )

        document.ingest_stage = "index"
        await db.commit()

        chunk_records = []
        for chunk in chunks:
            chunk_records.append(
                Chunk(
                    id=uuid4(),
                    document_id=document_id,
                    chunk_index=chunk.index,
                    start_page=chunk.start_page,
                    end_page=chunk.end_page,
                    text_content=chunk.text,
                    token_count=chunk.token_count,
                    section_title=getattr(chunk, "section_title", None),
                    chunk_strategy=getattr(chunk, "chunk_strategy", None),
                )
            )

        db.add_all(chunk_records)
        await db.flush()

        vector_store = create_vector_store()
        t2 = time.perf_counter()
        embedding_ids = await vector_store.upsert(document_id, chunks, embeddings)
        logger.info(
            "ingest_index document_id=%s duration_ms=%d",
            document_id,
            int((time.perf_counter() - t2) * 1000),
        )

        for chunk_record, emb_id in zip(chunk_records, embedding_ids):
            chunk_record.embedding_id = emb_id

        document = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one()
        document.status = DocumentStatus.INDEXED
        document.ingest_stage = None
        await db.commit()

        if settings.ENABLE_GRAPH_INGEST:
            try:
                from services.graph_service import build_kg_for_document

                await build_kg_for_document(document_id, db)
            except Exception as kg_err:
                logger.warning("Graph ingest failed for %s: %s", document_id, kg_err)

    except Exception as e:
        logger.exception("ingest failed document_id=%s", document_id)
        document = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one()
        document.status = DocumentStatus.ERROR
        document.error_message = str(e)[:2000]
        document.ingest_stage = "error"
        await db.commit()
        raise

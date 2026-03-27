"""
Document management API routes.

Handles PDF upload, processing, listing, librarian chunk views, and rechunk.
"""

from pathlib import Path
import logging
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body, Form, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from models.database import Document, Chunk, DocumentStatus
from models.schemas import (
    DocumentUploadResponse,
    DocumentSummary,
    DocumentDetail,
    ChunkPreview,
    DocumentChunkRow,
    DocumentChunksPage,
    RechunkRequest,
    ChunkPresetInfo,
    ChunkPresetsResponse,
    GlobalSearchHit,
)
from services.vector_store import create_vector_store
from services.ingest_pipeline import run_document_ingest
from services.chunk_preset_service import get_chunk_preset, load_presets
from core.config import get_settings

from api.dependencies import get_db, get_session_maker

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

_PREVIEW_LEN = 400


def _detail(doc: Document, chunk_count: int) -> DocumentDetail:
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        original_name=doc.original_name,
        file_size=doc.file_size,
        total_pages=doc.total_pages,
        chunk_count=chunk_count,
        upload_date=doc.upload_date,
        status=doc.status.value,
        error_message=doc.error_message,
        chunk_preset_id=getattr(doc, "chunk_preset_id", None),
        ingest_stage=getattr(doc, "ingest_stage", None),
    )


@router.get("/chunk-presets", response_model=ChunkPresetsResponse)
async def list_chunk_presets():
    presets = load_presets()
    return ChunkPresetsResponse(
        presets=[
            ChunkPresetInfo(
                id=p.id,
                chunk_size=p.chunk_size,
                overlap=p.overlap,
                strategy=p.strategy,
            )
            for p in sorted(presets.values(), key=lambda x: x.id)
        ]
    )



@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_preset: Optional[str] = Form(default=None),
    workspace_id: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    contents = await file.read()
    file_size = len(contents)
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB",
        )

    preset = get_chunk_preset(chunk_preset)
    ws_uuid: Optional[UUID] = None
    if workspace_id:
        try:
            ws_uuid = UUID(workspace_id.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workspace_id")

    doc_id = uuid4()
    safe_filename = f"{doc_id}.pdf"
    file_path = settings.UPLOAD_DIR / safe_filename

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(contents)

    document = Document(
        id=doc_id,
        workspace_id=ws_uuid,
        filename=safe_filename,
        original_name=file.filename,
        file_size=file_size,
        total_pages=0,
        file_path=str(file_path),
        status=DocumentStatus.PROCESSING,
        chunk_preset_id=preset.id,
    )

    db.add(document)
    await db.commit()

    background_tasks.add_task(
        process_document_background,
        doc_id,
        file_path,
        file.filename,
        preset.id,
    )

    return DocumentUploadResponse(
        id=doc_id,
        filename=file.filename,
        status=DocumentStatus.PROCESSING,
        total_pages=0,
        upload_date=document.upload_date,
        message="Document uploaded successfully. Processing in background.",
    )


async def process_document_background(
    document_id: UUID,
    file_path: Path,
    original_name: str,
    chunk_preset_id: Optional[str] = None,
):
    async_session = get_session_maker()

    async with async_session() as db:
        try:
            await run_document_ingest(
                db,
                document_id,
                file_path,
                chunk_preset_id=chunk_preset_id,
                delete_existing_vectors=False,
            )
        except Exception as e:
            logger.exception("Background ingest failed document_id=%s error=%s", document_id, e)
            raise



@router.get("/search", response_model=List[GlobalSearchHit])
async def search_corpus(
    q: str = Query(..., min_length=1, max_length=500),
    workspace_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight full-corpus search over chunk text and document titles (ILIKE)."""
    # Avoid ILIKE metacharacters in user input
    safe_q = "".join(c for c in q if c not in "%_\\")
    pat = f"%{safe_q}%"
    base = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == DocumentStatus.INDEXED)
    )
    if workspace_id is not None:
        base = base.where(Document.workspace_id == workspace_id)
    base = base.where(
        or_(
            Chunk.text_content.ilike(pat),
            Document.original_name.ilike(pat),
        )
    ).limit(limit)

    result = await db.execute(base)
    hits: List[GlobalSearchHit] = []
    for chunk, doc in result.all():
        text = chunk.text_content or ""
        snippet = text[:280] + ("…" if len(text) > 280 else "")
        hits.append(
            GlobalSearchHit(
                chunk_id=str(chunk.id),
                document_id=doc.id,
                document_name=doc.original_name,
                start_page=chunk.start_page,
                end_page=chunk.end_page,
                snippet=snippet,
                chunk_strategy=chunk.chunk_strategy,
            )
        )
    return hits


@router.get("/", response_model=List[DocumentSummary])
async def list_documents(
    workspace_id: Optional[UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Document, func.count(Chunk.id).label("chunk_count"))
        .outerjoin(Chunk, Document.id == Chunk.document_id)
        .group_by(Document.id)
        .order_by(Document.upload_date.desc())
    )
    if workspace_id is not None:
        q = q.where(Document.workspace_id == workspace_id)

    result = await db.execute(q)

    documents = []
    for row in result.all():
        doc, chunk_count = row
        documents.append(
            DocumentSummary(
                id=doc.id,
                filename=doc.filename,
                original_name=doc.original_name,
                total_pages=doc.total_pages,
                chunk_count=chunk_count or 0,
                upload_date=doc.upload_date,
                status=doc.status.value,
                error_message=doc.error_message,
                workspace_id=getattr(doc, "workspace_id", None),
                ingest_stage=getattr(doc, "ingest_stage", None),
                chunk_preset_id=getattr(doc, "chunk_preset_id", None),
            )
        )

    return documents


class DocumentUpdate(BaseModel):
    original_name: Optional[str] = None
    workspace_id: Optional[UUID] = None


@router.patch("/{document_id}", response_model=DocumentDetail)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document, func.count(Chunk.id).label("chunk_count"))
        .outerjoin(Chunk, Document.id == Chunk.document_id)
        .where(Document.id == document_id)
        .group_by(Document.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    doc, chunk_count = row
    if body.original_name is not None:
        doc.original_name = body.original_name.strip() or doc.original_name
    if body.workspace_id is not None:
        doc.workspace_id = body.workspace_id
    await db.commit()
    await db.refresh(doc)
    return _detail(doc, chunk_count or 0)


@router.get("/{document_id}/chunks", response_model=DocumentChunksPage)
async def list_document_chunks(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    dr = await db.execute(select(Document).where(Document.id == document_id))
    doc = dr.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    count_q = await db.execute(
        select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
    )
    total = count_q.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .offset(offset)
        .limit(page_size)
    )
    rows = result.scalars().all()

    chunks = [
        DocumentChunkRow(
            chunk_id=ch.embedding_id or str(ch.id),
            chunk_index=ch.chunk_index,
            start_page=ch.start_page,
            end_page=ch.end_page,
            token_count=ch.token_count,
            chunk_strategy=ch.chunk_strategy,
            text_preview=(ch.text_content or "")[:_PREVIEW_LEN],
        )
        for ch in rows
    ]

    return DocumentChunksPage(
        document_id=document_id,
        total=total,
        page=page,
        page_size=page_size,
        chunks=chunks,
    )


@router.post("/{document_id}/rechunk")
async def rechunk_document(
    document_id: UUID,
    body: RechunkRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(document.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Original file missing on disk")

    preset = get_chunk_preset(body.chunk_preset)
    document.chunk_preset_id = preset.id
    await db.commit()

    background_tasks.add_task(
        _rechunk_background,
        document_id,
        file_path,
        preset.id,
    )
    return {
        "message": "Rechunk started",
        "document_id": str(document_id),
        "chunk_preset": preset.id,
    }


async def _rechunk_background(document_id: UUID, file_path: Path, chunk_preset_id: str):
    async_session = get_session_maker()

    async with async_session() as db:
        try:
            await run_document_ingest(
                db,
                document_id,
                file_path,
                chunk_preset_id=chunk_preset_id,
                delete_existing_vectors=True,
            )
        except Exception as e:
            logger.exception(
                "Background rechunk failed document_id=%s preset=%s error=%s",
                document_id,
                chunk_preset_id,
                e,
            )
            raise


@router.post("/{document_id}/retry-ingest")
async def retry_ingest(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = Path(document.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Original file missing on disk")

    preset_id = document.chunk_preset_id or "default"
    background_tasks.add_task(
        _rechunk_background,
        document_id,
        file_path,
        preset_id,
    )
    return {"message": "Retry ingest started", "document_id": str(document_id)}


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document, func.count(Chunk.id).label("chunk_count"))
        .outerjoin(Chunk, Document.id == Chunk.document_id)
        .where(Document.id == document_id)
        .group_by(Document.id)
    )

    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    doc, chunk_count = row
    return _detail(doc, chunk_count or 0)


@router.delete("/{document_id}")
async def delete_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        vector_store = create_vector_store()
        await vector_store.delete_document(document_id)
    except Exception as e:
        logger.warning("Vector store delete failed document_id=%s error=%s", document_id, e)

    try:
        fp = Path(document.file_path)
        if fp.exists():
            fp.unlink()
    except Exception as e:
        logger.warning("File delete failed document_id=%s path=%s error=%s", document_id, document.file_path, e)

    await db.delete(document)
    await db.commit()

    return {"message": "Document deleted successfully"}


@router.get("/{document_id}/chunks/{chunk_id}", response_model=ChunkPreview)
async def get_chunk_preview(
    document_id: UUID,
    chunk_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    vector_store = create_vector_store()
    chunk = await vector_store.get_chunk(chunk_id)

    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    return ChunkPreview(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_name=document.original_name,
        text=chunk.text,
        start_page=chunk.start_page,
        end_page=chunk.end_page,
    )

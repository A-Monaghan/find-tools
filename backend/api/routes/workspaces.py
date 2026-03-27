"""Investigation workspaces (cases) — group documents and conversations."""

from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Workspace
from models.schemas import WorkspaceSummary, WorkspaceCreate
from api.dependencies import get_db

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/", response_model=List[WorkspaceSummary])
async def list_workspaces(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workspace).order_by(Workspace.created_at.asc()))
    rows = result.scalars().all()
    return [
        WorkspaceSummary(id=w.id, name=w.name, created_at=w.created_at)
        for w in rows
    ]


@router.post("/", response_model=WorkspaceSummary)
async def create_workspace(body: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    w = Workspace(id=uuid4(), name=body.name.strip())
    db.add(w)
    await db.flush()
    return WorkspaceSummary(id=w.id, name=w.name, created_at=w.created_at)


@router.patch("/{workspace_id}", response_model=WorkspaceSummary)
async def rename_workspace(
    workspace_id: UUID,
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workspace not found")
    w.name = body.name.strip()
    await db.flush()
    return WorkspaceSummary(id=w.id, name=w.name, created_at=w.created_at)

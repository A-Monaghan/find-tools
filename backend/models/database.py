"""
SQLAlchemy database models.
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4, UUID

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Text,
    Enum, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class Workspace(Base):
    """Investigation workspace / case — groups documents and conversations."""

    __tablename__ = "workspaces"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    documents = relationship("Document", back_populates="workspace")
    conversations = relationship("Conversation", back_populates="workspace")


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    INDEXED = "indexed"
    ERROR = "error"


class Document(Base):
    """Uploaded PDF document metadata."""
    __tablename__ = "documents"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    total_pages = Column(Integer, nullable=False)
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PROCESSING)
    file_path = Column(String(500), nullable=False)
    error_message = Column(Text, nullable=True)  # Populated when status is ERROR
    # Ingest: named chunk preset (see config/chunk_presets.json) + stage logging for ops / HITL rechunk
    chunk_preset_id = Column(String(64), nullable=True, default="default")
    ingest_stage = Column(String(32), nullable=True)
    
    # Relationships
    workspace = relationship("Workspace", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="document")


class Chunk(Base):
    """Document chunks with metadata."""
    __tablename__ = "chunks"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False)
    embedding_id = Column(String(100), nullable=True)
    section_title = Column(String(255), nullable=True)
    chunk_strategy = Column(String(50), nullable=True)
    
    # Relationship
    document = relationship("Document", back_populates="chunks")


class Conversation(Base):
    """Chat conversation."""
    __tablename__ = "conversations"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    workspace_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="conversations")
    workspace = relationship("Workspace", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    """Individual chat message."""
    __tablename__ = "messages"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    citations = Column(JSON, nullable=True)  # List of citation objects
    retrieved_chunks = Column(JSON, nullable=True)  # Full retrieval context
    model_used = Column(String(100), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    token_count_prompt = Column(Integer, nullable=True)
    token_count_response = Column(Integer, nullable=True)
    
    # Relationship
    conversation = relationship("Conversation", back_populates="messages")


class QueryLog(Base):
    """Audit log for all RAG queries."""
    __tablename__ = "query_logs"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    query = Column(Text, nullable=False)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    retrieved_chunk_ids = Column(JSON, nullable=False)  # List of chunk IDs
    prompt_sent = Column(Text, nullable=False)
    response_received = Column(Text, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    token_count_prompt = Column(Integer, nullable=False)
    token_count_response = Column(Integer, nullable=False)
    model_used = Column(String(100), nullable=False)
    rag_meta = Column(JSON, nullable=True)

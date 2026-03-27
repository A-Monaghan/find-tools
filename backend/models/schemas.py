"""
Pydantic schemas for data validation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ============== PDF Processing Schemas ==============

@dataclass
class TextBlock:
    """A block of text with spatial information."""
    text: str
    bbox: tuple  # (x0, y0, x1, y1) bounding box
    page: int


@dataclass
class Page:
    """A page containing text blocks."""
    number: int
    blocks: List[TextBlock]


@dataclass
class ParsedDocument:
    """Parsed PDF document with page structure."""
    pages: List[Page]
    
    @property
    def total_pages(self) -> int:
        return len(self.pages)
    
    def get_full_text(self) -> str:
        """Get all text with page markers."""
        parts = []
        for page in self.pages:
            page_text = "\n".join(block.text for block in page.blocks)
            parts.append(f"\n\n--- Page {page.number} ---\n\n{page_text}")
        return "".join(parts)


@dataclass
class Chunk:
    """A text chunk with page range metadata."""
    text: str
    start_page: int
    end_page: int
    token_count: int
    index: int = 0
    section_title: Optional[str] = None
    chunk_strategy: Optional[str] = None
    
    @property
    def page_range(self) -> str:
        if self.start_page == self.end_page:
            return f"Page {self.start_page}"
        return f"Pages {self.start_page}-{self.end_page}"


# ============== API Request/Response Schemas ==============

class DocumentUploadResponse(BaseModel):
    """Response after document upload."""
    id: UUID
    filename: str
    status: str  # processing, indexed, error
    total_pages: int
    upload_date: datetime
    message: str


class DocumentSummary(BaseModel):
    """Summary of a document in the library."""
    id: UUID
    filename: str
    original_name: str
    total_pages: int
    chunk_count: int
    upload_date: datetime
    status: str
    error_message: Optional[str] = None
    workspace_id: Optional[UUID] = None
    ingest_stage: Optional[str] = None
    chunk_preset_id: Optional[str] = None


class DocumentDetail(BaseModel):
    """Detailed document information."""
    id: UUID
    filename: str
    original_name: str
    file_size: int
    total_pages: int
    chunk_count: int
    upload_date: datetime
    status: str
    error_message: Optional[str] = None
    chunk_preset_id: Optional[str] = None
    ingest_stage: Optional[str] = None


class DocumentChunkRow(BaseModel):
    """One stored chunk with boundaries (librarian view)."""
    chunk_id: str
    chunk_index: int
    start_page: int
    end_page: int
    token_count: int
    chunk_strategy: Optional[str] = None
    text_preview: str


class DocumentChunksPage(BaseModel):
    document_id: UUID
    total: int
    page: int
    page_size: int
    chunks: List[DocumentChunkRow]


class RechunkRequest(BaseModel):
    chunk_preset: str = Field(default="default", description="Preset id from config/chunk_presets.json")


class ChunkPresetInfo(BaseModel):
    id: str
    chunk_size: int
    overlap: int
    strategy: str


class ChunkPresetsResponse(BaseModel):
    presets: List[ChunkPresetInfo]


class QueryRequest(BaseModel):
    """Query request for RAG."""
    query: str = Field(..., min_length=1, description="User question")
    document_id: Optional[UUID] = Field(
        default=None,
        description="Specific document to search (null = search all)"
    )
    conversation_id: Optional[UUID] = Field(
        default=None,
        description="Existing conversation ID (null = new conversation)"
    )
    model: Optional[str] = Field(
        default=None,
        description="Model to use for generation (null = use default)"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Custom system prompt template (use {context} placeholder for document context)"
    )

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt_template(cls, value: Optional[str]) -> Optional[str]:
        """Allow {context} placeholder only to avoid runtime format errors."""
        if value is None:
            return value
        if "{context}" not in value:
            raise ValueError("system_prompt must include the {context} placeholder")
        # Escaped braces are fine; reject extra unescaped placeholders.
        sanitized = value.replace("{{", "").replace("}}", "").replace("{context}", "")
        if "{" in sanitized or "}" in sanitized:
            raise ValueError("system_prompt may only use the {context} placeholder")
        return value


class CitationResponse(BaseModel):
    """Citation information for an answer."""
    document_id: UUID
    document_name: str
    chunk_id: str
    start_page: int
    end_page: int
    evidence_quote: str
    relevance_score: float


class RetrievedChunk(BaseModel):
    """A retrieved chunk with metadata."""
    chunk_id: str
    document_id: UUID
    document_name: str
    text: str
    start_page: int
    end_page: int
    score: float


class RetrievalTraceChunk(BaseModel):
    """Per-chunk retrieval diagnostics (fusion or dense-only)."""
    chunk_id: str
    dense_rank: int = -1
    bm25_rank: int = -1
    fused_score: Optional[float] = None
    dense_score: Optional[float] = None


class RetrievalTrace(BaseModel):
    """HyDE / fusion / CRAG transparency for investigators."""
    hyde_used: bool = False
    fusion_enabled: bool = False
    fusion_alpha: Optional[float] = None
    rrf_k: Optional[int] = None
    mode: str = "dense"  # dense | fusion
    crag_action: Optional[str] = None
    web_augmented: bool = False
    chunks: List[RetrievalTraceChunk] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """RAG query response."""
    model_config = ConfigDict(protected_namespaces=())
    answer: str
    citations: List[CitationResponse]
    retrieved_chunks: List[RetrievedChunk]
    conversation_id: UUID
    model_used: str
    latency_ms: int
    token_count_prompt: int
    token_count_response: int
    retrieval_trace: Optional[RetrievalTrace] = None


class WorkspaceSummary(BaseModel):
    """One investigation workspace."""
    id: UUID
    name: str
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class GlobalSearchHit(BaseModel):
    """One row from corpus-wide chunk search."""
    chunk_id: str
    document_id: UUID
    document_name: str
    start_page: int
    end_page: int
    snippet: str
    chunk_strategy: Optional[str] = None


class ChunkPreview(BaseModel):
    """Preview of a specific chunk."""
    chunk_id: str
    document_id: UUID
    document_name: str
    text: str
    start_page: int
    end_page: int


class MessageResponse(BaseModel):
    """Chat message in conversation history."""
    id: UUID
    role: str  # user, assistant, system
    content: str
    timestamp: datetime
    citations: Optional[List[CitationResponse]] = None


class ConversationResponse(BaseModel):
    """Conversation history."""
    id: UUID
    document_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]


class QueryLogEntry(BaseModel):
    """Audit log entry for queries."""
    id: UUID
    timestamp: datetime
    query: str
    document_id: Optional[UUID]
    retrieved_chunk_ids: List[str]
    prompt_sent: str
    response_received: str
    latency_ms: int
    token_count_prompt: int
    token_count_response: int


class AvailableModel(BaseModel):
    """Available LLM model information."""
    id: str
    name: str
    provider: str  # "openrouter" or "vllm"


class AvailableModelsResponse(BaseModel):
    """Response listing available models."""
    models: List[AvailableModel]
    default_model: str
    fast_model: str = Field(description="OpenRouter id for fast/cheap draft pass (from OPENROUTER_FAST_MODEL)")
    active_provider: str


class CHRunRequest(BaseModel):
    """Companies House pipeline run request."""
    search_type: str = Field(..., description="company_number | officer_id | name")
    search_value: str = Field(..., description="Company numbers, officer ID, or name to search")
    api_key: Optional[str] = Field(default=None, description="Optional API key override")


class CHFilingsListRequest(BaseModel):
    """List filing metadata (no PDFs) for one company; optional calendar-year filter."""
    company_number: str = Field(..., description="UK company number")
    year_from: Optional[int] = Field(default=None, description="Inclusive start year")
    year_to: Optional[int] = Field(default=None, description="Inclusive end year")
    api_key: Optional[str] = Field(default=None, description="Optional API key override")


class CHFilingListItem(BaseModel):
    """One row from filing history with document availability."""
    transaction_id: Optional[str] = None
    date: Optional[str] = None
    filing_type: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    has_document: bool = False
    document_id: Optional[str] = None


class CHFilingsListResponse(BaseModel):
    """Filings list for UI selection / year filtering."""
    company_number: str
    filings: List[CHFilingListItem]


class CHDocumentsDownloadRequest(BaseModel):
    """Download PDFs for selected filing transaction IDs (from prior list call)."""
    company_number: str = Field(..., description="UK company number")
    transaction_ids: List[str] = Field(..., description="Filing transaction IDs to fetch")
    api_key: Optional[str] = Field(default=None, description="Optional API key override")


class CHHopGraphRequest(BaseModel):
    """Return a company-centred CH graph from Neo4j using N-hop traversal."""
    company_number: str = Field(..., description="Root UK company number")
    hops: int = Field(default=2, ge=1, le=4, description="Traversal depth in hops")
    max_nodes: int = Field(default=400, ge=50, le=2000, description="Maximum nodes returned")
    max_edges: int = Field(default=1200, ge=100, le=6000, description="Maximum edges returned")
# RAG-v2.1 System Architecture

## Flow Diagrams

### 1. Document ingestion (upload pipeline)

When a user uploads a PDF, data flows in sequence:

```mermaid
flowchart LR
    subgraph Ingest["Document ingestion"]
        A[PDF upload] --> B[PDF Service<br/>extract text]
        B --> C[Chunking Service<br/>512 tokens, 50 overlap]
        C --> D[Embedding Service]
        D --> E[Vector Store<br/>pgvector]
        E --> F[(PostgreSQL)]
    end
```

### 2. Query / RAG flow (chat)

When a user sends a chat query, the pipeline runs in order:

```mermaid
flowchart LR
    subgraph RAG["RAG query pipeline"]
        Q[User query] --> QE[Embed query]
        QE --> VS[Vector search<br/>similarity]
        VS --> RR[Rerank chunks]
        RR --> LLM[LLM Router<br/>vLLM or OpenRouter]
        LLM --> CIT[Citation Service<br/>validate + credibility]
        CIT --> R[Response to UI]
    end
```

### 3. Component topology

How services and data fit together:

```mermaid
flowchart TB
    subgraph Client["Frontend (React + TypeScript)"]
        UI[ChatInterface / DocumentLibrary / CitationPanel]
    end

    subgraph Gateway["Nginx"]
        NG[80/443]
    end

    subgraph Backend["FastAPI"]
        API[API Routes]
        PDF[PDF]
        CHUNK[Chunking]
        EMBED[Embedding]
        VSTORE[Vector Store]
        RERANK[Rerank]
        LLM[LLM Router]
        CIT[Citation]
    end

    subgraph Data["Data"]
        PG[(PostgreSQL+pgvector)]
        REDIS[(Redis)]
    end

    subgraph External["External"]
        VLLM[vLLM]
        OPENROUTER[OpenRouter]
        LOCAL_EMBED[Local embeddings]
    end

    UI --> NG --> API
    API --> PDF --> CHUNK --> EMBED --> VSTORE
    API --> EMBED --> VSTORE --> RERANK --> LLM --> CIT --> API
    API --> PG
    API --> REDIS
    EMBED --> LOCAL_EMBED
    LLM --> VLLM
    LLM --> OPENROUTER
```

## Component Descriptions

### Frontend
| Component | Description |
|-----------|-------------|
| **ChatInterface** | Main chat UI for querying documents with message display and citation links |
| **DocumentLibrary** | Document upload, list, and management interface |
| **CitationPanel** | Displays sources and evidence for LLM-generated answers |

### Backend Services
| Service | Description |
|---------|-------------|
| **PDF Service** | Parses uploaded PDFs, extracts text with page number tracking |
| **Embedding Service** | Generates vector embeddings using local models (sentence-transformers) or OpenAI |
| **Vector Store** | Qdrant/pgvector abstraction for similarity search and storage |
| **Rerank Service** | Re-ranks retrieved chunks for improved relevance |
| **LLM Router** | Routes requests to vLLM (local) or OpenRouter (cloud) with automatic fallback |
| **Citation Service** | Validates and extracts citations from LLM responses |
| **Chunking Service** | Splits documents into overlapping chunks (512 tokens, 50 overlap) |
| **OSINT Processor** | Processes open-source intelligence data |
| **Credibility Scorer** | Scores source credibility for citations |

### Data Layer
| Component | Description |
|-----------|-------------|
| **PostgreSQL + pgvector** | Primary database for metadata, conversations, and vector storage |
| **Redis** | Caching layer for performance optimisation |

### API Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/register` | POST | User registration |
| `/auth/login` | POST | User login, returns JWT token |
| `/documents/upload` | POST | Upload PDF documents |
| `/documents/` | GET | List all documents |
| `/chat/query` | POST | Main RAG query endpoint |
| `/logs/queries` | GET | Query audit logs |

## Operation Modes

| Mode | Configuration | Providers |
|------|---------------|-----------|
| **private** | Fully offline | vLLM + local embeddings |
| **hybrid** | Prefer local, fallback to cloud | vLLM → OpenRouter |
| **cloud** | Cloud-only | OpenRouter only |

## Data Flow Summary

1. **Document Ingestion**: PDF upload → Text extraction → Chunking → Embedding → Vector store
2. **Query Processing**: User query → Embedding → Vector search → Re-ranking → LLM generation → Citation validation → Response

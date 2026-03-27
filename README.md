# RAG-v2.1

A private, browser-based Retrieval-Augmented Generation (RAG) application for querying large documents with grounded, citation-based answers.

## Features

- **Multi-Format Ingestion**: PDF, DOCX, PPTX, XLSX, HTML, images via Docling (falls back to PyMuPDF)
- **Semantic Chunking**: Embedding-similarity-based chunk boundaries (+ section, paragraph, sliding strategies)
- **Fusion Retrieval**: BM25 + dense vector search combined via Reciprocal Rank Fusion
- **HyDE**: Hypothetical Document Embedding for short/vague queries
- **Corrective RAG**: Self-checks retrieval quality; falls back to web search when confidence is low
- **Hybrid LLM Support**: Local (vLLM) or cloud (OpenRouter) inference
- **Citation Tracking**: Every answer includes source document and page references
- **RAG Evaluation**: Faithfulness, answer relevancy, contextual precision/recall (DeepEval)
- **Privacy-First**: Run completely offline with local models
- **Query Logging**: Full audit trail of all queries and responses
- **Investigation workspaces**: Optional “case” labels filter the document library; uploads target a chosen workspace (`/workspaces`, `workspace_id` on documents)
- **Retrieval trace** (UI): Each answer can show HyDE, fusion vs dense, CRAG, and per-chunk dense/BM25 ranks (`retrieval_trace` on `/chat/query`)
- **Corpus search**: Quick ILIKE search across indexed chunk text and titles (`GET /documents/search?q=…`)

## Architecture

```
┌─────────────┐      ┌──────────────────────────────────────────────────────────┐
│   Frontend  │──────▶│                     Backend (FastAPI)                    │
│  (React)    │      │                                                          │
└─────────────┘      │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐ │
                     │  │ Docling / │  │ Semantic  │  │  Fusion   │  │  HyDE  │ │
                     │  │ PyMuPDF  │──▶│ Chunker  │  │ Retrieval │  │        │ │
                     │  └──────────┘  └──────────┘  │ BM25+Dense│  └────────┘ │
                     │                               └───────────┘             │
                     │  ┌──────────┐  ┌──────────┐  ┌───────────┐             │
                     │  │   CRAG   │  │ Reranker │  │ DeepEval  │             │
                     │  │ Web fall │  │ Cross-Enc│  │ Metrics   │             │
                     │  └──────────┘  └──────────┘  └───────────┘             │
                     └──────────────────────────────────────────────────────────┘
                            │                          │
                            ▼                          ▼
                     ┌──────────────┐          ┌─────────────────┐
                     │  PostgreSQL  │          │  Vector Store   │
                     │  (Metadata)  │          │   (Qdrant)      │
                     └──────────────┘          └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) OpenRouter API key for cloud mode
- (Optional) vLLM for local inference

### 1. Clone and Configure

```bash
cd RAG-v2.1
cp .env.example .env
# Edit .env with your API keys and preferences
```

### 2. Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL with pgvector on port 5432
- Qdrant on port 6333
- Redis on port 6379
- Backend API on port 8000
- Frontend on port 3000

### 2b. Local API with repo `venv` (optional)

Use the checked-in pattern: `RAG-v2.1/venv` (gitignored) plus `scripts/run_backend_venv.sh` when you want the FastAPI process on the host while databases still run in Docker (or elsewhere).

1. **Python 3.12** — create the venv with `python3.12`; Python 3.13 does not install the pinned `qdrant-client==1.7.0`.
2. From `RAG-v2.1`:
   ```bash
   python3.12 -m venv venv
   ./venv/bin/pip install -r backend/requirements.txt
   ```
3. Ensure `.env` points at your Postgres, Qdrant, and Redis (e.g. start infra only: `docker compose up -d postgres qdrant redis`).
4. Run the API:
   ```bash
   chmod +x scripts/run_backend_venv.sh   # once
   ./scripts/run_backend_venv.sh
   ```

### 3. (Optional) Entity Extractor

For URL/text entity extraction, start the OOCP backend:

```bash
cd "OOCP/TExt Body Extractor" && ./start_backend.sh
```

Runs on port 5001. The frontend proxies `/ee` to it in dev.

### 4. (Optional) Neo4j – Ingest into Graph

To push extracted entities/relationships into Neo4j:

1. Run Neo4j (Docker: `docker run -d -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/yourpassword neo4j:5-community`)
2. Add to `OOCP/TExt Body Extractor/.env`:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=yourpassword
   ```
3. Restart OOCP. The Entity Extractor UI will show "Neo4j: Connected" and enable Push to Neo4j.

### 5. Access the Application

Open http://localhost:3000 in your browser (or http://localhost:5175 when running frontend dev server).

## Operation Modes

### Private Mode (Local Only)

Run completely offline with local models:

```bash
# 1. Start vLLM (in separate terminal)
python -m vllm.entrypoints.openai.api_server \
    --model mistralai/Mistral-7B-Instruct-v0.3 \
    --tensor-parallel-size 1

# 2. Configure
OPERATION_MODE=private
VLLM_URL=http://localhost:8000/v1

# 3. Start RAG
docker-compose up -d
```

### Hybrid Mode (Recommended)

Uses local resources when available, falls back to cloud:

```bash
OPERATION_MODE=hybrid
OPENROUTER_API_KEY=sk-or-...
VLLM_URL=http://localhost:8000/v1
```

Priority:
1. vLLM (if running)
2. OpenRouter (if API key configured)

### Cloud Mode

Uses only cloud services:

```bash
OPERATION_MODE=cloud
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
```

## Advanced RAG Configuration

All features are controlled via environment variables (`.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_DOCLING` | `true` | Reserved for future Docling; pipeline currently uses PyMuPDF |
| `CHUNKING_STRATEGY` | `auto` | `auto`, `sections`, `paragraphs`, `sliding`, `semantic` |
| `ENABLE_FUSION_RETRIEVAL` | `true` | Combine BM25 + dense search via RRF |
| `FUSION_ALPHA` | `0.5` | Dense vs BM25 weight (>0.5 favours dense) |
| `ENABLE_HYDE` | `true` | HyDE for short/vague queries |
| `ENABLE_CORRECTIVE_RAG` | `true` | Self-check retrieval + web fallback |

### Query Pipeline

```
User Query
    │
    ├─ [HyDE] Generate hypothetical answer → blend embedding
    │
    ├─ [Fusion] BM25 + Dense vector search → RRF merge
    │
    ├─ [CRAG] Evaluate relevance → web fallback if LOW
    │
    ├─ [Rerank] Cross-encoder re-scoring → top-K
    │
    ├─ [LLM] Generate answer with context
    │
    ├─ [Citations] Validate + extract evidence
    │
    └─ [DeepEval] Faithfulness + relevancy metrics (background)
```

## Development

### Backend Only

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Frontend Only

```bash
cd frontend
npm install
npm run dev
```

From the `RAG-v2.1` root (after `npm install` in `frontend/`): `npm run dev` and `npm run build` delegate to `frontend/` so you do not need to `cd frontend` each time.

## Verification

Run the verification script to test API, upload, and chat:

```bash
cd RAG-v2.1
python verify_system.py
```

Quick **API-only smoke** (no upload, chat, or frontend check):

```bash
python verify_system.py --smoke
```

Optional: `--base-url http://localhost:8000` and `--frontend-url http://localhost:3000` to override defaults.

For detailed troubleshooting, see [TESTING.md](TESTING.md).

## API Endpoints

- `POST /documents/upload` - Upload PDF
- `GET /documents/` - List documents
- `POST /chat/query` - Query documents
- `GET /logs/queries` - Query audit logs

See full API documentation at http://localhost:8000/docs

## License

MIT

# RAG-v2.1 Deployment Guide

## Local (Docker Compose)

```bash
cd RAG-v2.1
cp .env.example .env   # if .env missing
# Edit .env: add OPENROUTER_API_KEY for cloud LLM (hybrid/cloud mode)
docker-compose up -d
```

**Optional – Neo4j:** For graph ingestion, add to `services/text-body-extractor/.env`:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=yourpassword
```
Restart the extractor. Entity Extractor shows "Neo4j: Connected" when reachable.

**Optional – Entity Extractor:** For URL/text entity extraction, run the bundled service:
```bash
cd services/text-body-extractor && cp -n .env.example .env   # once; add keys
./start_backend.sh
```
Or with Docker Compose (publishes **5001** on the host): `docker compose --profile entity-extractor up -d text-body-extractor`

Frontend dev proxies `/ee` → `http://localhost:5001`.

**Access:** http://localhost:3000 (frontend) | http://localhost:8000/docs (API)

### Alternative: UIkit frontend

Vanilla HTML/JS frontend using [UIkit](https://getuikit.com/). Same API; lighter, no React build.

```bash
# Option A: Use UIkit from CDN (default)
docker-compose -f docker-compose.yml -f docker-compose.uikit.yml up -d

# Option B: Bundle local UIkit (clone + build)
cd frontend-uikit && ./setup-uikit.sh && cd ..
docker-compose -f docker-compose.yml -f docker-compose.uikit.yml up -d --build
```

**Verify:** `python verify_system.py --base-url http://localhost:8000 --frontend-url http://localhost:3000`

---

## Fly.io Deployment

### Prerequisites

- `flyctl` installed and logged in
- Same Fly org for all apps (required for `*.internal` networking)

### 1. Create Postgres

```bash
fly postgres create --name rag-postgres --region lhr
# Note the connection string; or attach later:
fly postgres attach rag-postgres -a rag-backend
```

### 2. Deploy Infrastructure (fly-infra)

```bash
cd fly-infra
fly volumes create qdrant_data --region lhr
fly volumes create redis_data --region lhr

cd qdrant && fly launch --no-deploy && fly deploy
cd ../redis && fly launch --no-deploy && fly deploy
```

### 3. Deploy Backend

```bash
cd RAG-v2.1/backend
fly volumes create rag_documents --region lhr
fly launch --no-deploy

# Secrets (required for hybrid/cloud mode)
fly secrets set \
  OPENROUTER_API_KEY=sk-or-... \
  OPENAI_API_KEY=sk-... \
  DATABASE_URL="postgresql+asyncpg://..." \
  QDRANT_URL="http://qdrant.internal:6333" \
  REDIS_URL="redis://redis.internal:6379" \
  SECRET_KEY="$(openssl rand -hex 32)"

fly deploy
```

**If Postgres attached:** `DATABASE_URL` is set automatically. Add the rest.

### 4. Deploy Frontend

**React (default):**
```bash
cd RAG-v2.1/frontend
fly launch --no-deploy
# Ensure fly.toml has: VITE_API_BASE_URL = "https://rag-backend.fly.dev"
fly deploy
```

**UIkit alternative:**
```bash
cd RAG-v2.1/frontend-uikit
fly launch --no-deploy
# Same CORS; no build step
fly deploy
```

### 5. Wire CORS

Backend `fly.toml` already has `CORS_ORIGINS` for `https://rag-frontend.fly.dev`. If using a custom domain, add it:

```bash
fly secrets set CORS_ORIGINS="https://rag-frontend.fly.dev,https://your-domain.com"
```

---

## Operation Modes

| Mode | LLM | Embeddings |
|------|-----|------------|
| **private** | vLLM (local) | sentence-transformers |
| **hybrid** | vLLM → OpenRouter fallback | local → OpenAI fallback |
| **cloud** | OpenRouter | OpenAI |

Set via `OPERATION_MODE` in `.env` or Fly secrets.

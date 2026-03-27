# AGENTS.md

## Cursor Cloud specific instructions

### Architecture overview

FIND Tools (RAG-v2.1) is an OSINT investigation platform with a FastAPI backend (Python 3.12) and a React + Vite frontend (TypeScript). Infrastructure services run via Docker: PostgreSQL (pgvector), Qdrant (vector store), and Redis (cache/rate-limiting). Neo4j is optional.

### Starting infrastructure

Run the three required infrastructure services directly with `docker run` (not `docker compose up`), because the compose file includes memory limits that fail in cgroup-v2 threaded-mode environments (the default Cloud Agent VM). See the commands below:

```bash
docker network create rag-network 2>/dev/null || true
docker run -d --name rag-postgres --network rag-network -e POSTGRES_DB=ragdb -e POSTGRES_USER=raguser -e POSTGRES_PASSWORD=changeme -p 5432:5432 --restart unless-stopped ankane/pgvector:latest
docker run -d --name rag-qdrant --network rag-network -e QDRANT__SERVICE__HTTP_PORT=6333 -e QDRANT__SERVICE__GRPC_PORT=6334 -p 6333:6333 -p 6334:6334 --restart unless-stopped qdrant/qdrant:v1.7.4
docker run -d --name rag-redis --network rag-network -p 6379:6379 --restart unless-stopped redis:7-alpine redis-server --appendonly yes
```

### Starting the backend

From the repo root, with the venv at `./venv`:

```bash
cd /workspace
PYTHONPATH=backend ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The backend loads `.env` from the repo root via pydantic-settings. Health check: `curl http://localhost:8000/health`.

### Starting the frontend

```bash
cd /workspace/frontend
npx vite --host 0.0.0.0 --port 5175
```

Access at `http://localhost:5175`. The Vite proxy forwards `/api/*` to `http://localhost:8000`.

### Running tests

- **Backend:** `cd /workspace && PYTHONPATH=backend ./venv/bin/python -m pytest backend/tests/ -v`
- **Frontend:** `cd /workspace/frontend && npx vitest run`

### Running lint / type-check / build

- **Frontend type-check:** `cd /workspace/frontend && npx tsc --noEmit`
- **Frontend build:** `cd /workspace/frontend && npm run build`

### Key gotchas

1. **bcrypt compatibility:** The pinned `passlib[bcrypt]` requires `bcrypt<5`. If bcrypt 5.x installs, auth registration/login will crash with a `ValueError`. Fix: `pip install 'bcrypt==4.0.1'`.
2. **Python 3.13 incompatibility:** `qdrant-client==1.7.0` does not install on Python 3.13. Use Python 3.12.
3. **cgroup v2 in Cloud VMs:** `docker compose up` fails for services with `deploy.resources.limits.memory` because the Cloud VM cgroup is in threaded mode. Use `docker run` directly (without `--memory` flags) instead.
4. **Embeddings without API keys:** If `OPENAI_API_KEY` is not set (or commented out in `.env`), the backend falls back to local `sentence-transformers` embeddings. The first embed call downloads the model and can take 30–60 seconds.
5. **LLM chat requires API keys:** The `/chat/query` endpoint needs at least one LLM provider (`OPENROUTER_API_KEY` or a running vLLM instance). Without it, document upload/index/search all work, but chat answers will 500. Set `OPENROUTER_API_KEY` or `OPENAI_API_KEY` in `.env` for full functionality.
6. **`.env` placeholder keys:** The `.env.example` ships with placeholder keys (`sk-or-v1-...`, `sk-...`). These must be replaced or commented out; the backend treats them as real keys and tries (and fails) to call the external APIs.

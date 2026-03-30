# Deploying RAG-v2.1 to Northflank

## Architecture overview

The app has **two container images** plus **three managed add-ons**:

```
┌──────────────────────────────────────────────────────────┐
│  Northflank Project                                      │
│                                                          │
│  ┌────────────┐  ┌────────────┐                          │
│  │  Frontend   │  │  Backend   │                          │
│  │  (nginx)    │──│  (FastAPI) │                          │
│  │  port 80    │  │  port 8000 │                          │
│  └────────────┘  └─────┬──────┘                          │
│                        │                                 │
│        ┌───────────────┼───────────────┐                 │
│        │               │               │                 │
│  ┌─────┴─────┐  ┌──────┴────┐  ┌──────┴────┐            │
│  │ PostgreSQL │  │  Qdrant   │  │   Redis   │            │
│  │ (pgvector) │  │ (vectors) │  │  (cache)  │            │
│  └───────────┘  └───────────┘  └───────────┘            │
│                                                          │
│  Optional: Neo4j Aura (external, set env vars)           │
└──────────────────────────────────────────────────────────┘
```

| Component | Image / source | Port | Notes |
|-----------|---------------|------|-------|
| **Backend** | `backend/Dockerfile` — Python 3.11, Uvicorn | 8000 | Stateless; document uploads need a persistent volume |
| **Frontend** | `frontend/Dockerfile` — Node build → nginx | 80 | Static SPA; nginx reverse-proxies `/api/` to backend |
| **Postgres** | Northflank add-on or `ankane/pgvector` | 5432 | pgvector extension required for vector store fallback |
| **Qdrant** | Northflank add-on or `qdrant/qdrant:v1.7.4` | 6333 | Primary vector store |
| **Redis** | Northflank add-on or `redis:7-alpine` | 6379 | Query/response cache |

---

## Step 1 — Create the Northflank project

1. Log in to Northflank → **New Project**.
2. Name it something like `rag-v2` and pick a region close to your users.

---

## Step 2 — Provision data stores

### Option A: Northflank managed add-ons (simplest)

| Add-on | Type | Min plan | Notes |
|--------|------|----------|-------|
| **PostgreSQL** | Postgres 16+ | 1 GB RAM | Enable the `pgvector` extension after creation (or use the Northflank Postgres add-on that supports it). |
| **Redis** | Redis 7 | 256 MB | Append-only for durability. |
| **Qdrant** | Custom container | 1 GB RAM | Run as a Northflank **service** (see Option B). |

Northflank doesn't have a native Qdrant add-on. Deploy it as a container service:

1. **New Service** → **External image** → `qdrant/qdrant:v1.7.4`.
2. Internal port **6333** (HTTP) and **6334** (gRPC).
3. Add a **persistent volume** at `/qdrant/storage` (4–10 GB to start).
4. Set resource limits to at least 1 GB RAM.

### Option B: Bring your own (external)

Point `DATABASE_URL`, `QDRANT_URL`, and `REDIS_URL` at any reachable hosted instances.

---

## Step 3 — Create the backend service

### 3a — Using the GitHub Actions CI pipeline (recommended)

The repo already has `.github/workflows/northflank-deploy.yml`. It builds both images, pushes to GHCR, then deploys via the Northflank API.

**GitHub repo → Settings → Secrets and variables → Actions:**

| Secret | Value |
|--------|-------|
| `NORTHFLANK_API_KEY` | API token from Northflank dashboard (needs "Update deployment" scope) |
| `NORTHFLANK_PROJECT_ID` | Project ID from Northflank |
| `NORTHFLANK_SERVICE_BACKEND` | Service ID for the backend service |
| `NORTHFLANK_SERVICE_FRONTEND` | Service ID for the frontend service |
| `NORTHFLANK_REGISTRY_CREDENTIALS_ID` | Registry credentials ID in Northflank so it can pull from GHCR |

| Variable | Value |
|----------|-------|
| `BACKEND_PUBLIC_URL` | Public URL of your backend service, e.g. `https://api-xxxxx.northflank.app` (no trailing slash) |

Push to `main`, `master`, or `develop` triggers the pipeline.

### 3b — Northflank-native build (alternative)

1. **New Service** → **Combined (build + deploy)**.
2. Connect your GitHub repo.
3. **Build context:** `backend` (not repo root — root has a `package.json` that confuses buildpacks).
4. **Dockerfile path:** `backend/Dockerfile`.
5. Internal port: **8000**.
6. Add a **health check**: `GET /health` on port 8000.

### Backend environment variables

Set these on the backend service (runtime env):

```env
# === Required ===
DATABASE_URL=postgresql+asyncpg://raguser:<password>@<postgres-host>:5432/ragdb
QDRANT_URL=http://<qdrant-service>:6333
REDIS_URL=redis://<redis-host>:6379
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-...
SECRET_KEY=<random-string>

# === CORS — include the frontend's public URL ===
CORS_ORIGINS=https://<your-frontend>.northflank.app

# === Operation mode ===
OPERATION_MODE=cloud          # "cloud" unless you have a GPU on Northflank
VECTOR_STORE_TYPE=qdrant

# === Optional ===
NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
LOG_LEVEL=INFO
```

### Persistent volume for uploads

Attach a volume at `/app/storage/documents` (1–5 GB to start). Without this, uploaded documents are lost on redeploy.

---

## Step 4 — Create the frontend service

### Build

1. **New Service** → **Combined (build + deploy)** (or deploy from GHCR if using CI).
2. **Build context:** `frontend`.
3. **Dockerfile path:** `frontend/Dockerfile`.
4. **Build argument:**
   ```
   VITE_API_BASE_URL=https://<your-backend>.northflank.app
   ```
   This bakes the API URL into the Vite bundle at build time. If you change the backend URL you must rebuild the frontend.
5. Internal port: **80**.

### Frontend environment variables (runtime)

The nginx container also reverse-proxies `/api/` calls. Set this if the SPA should proxy through nginx rather than call the backend directly from the browser:

```env
NGINX_PROXY_API_UPSTREAM=http://<backend-internal-host>:8000
```

Using the Northflank internal network name (e.g. `http://backend:8000`) avoids a public round-trip. Leave the DNS resolver env blank — the entrypoint script auto-detects it from `/etc/resolv.conf`.

### Public networking

1. On the frontend service, add a **public port** on **80** with TLS.
2. Northflank assigns a `*.northflank.app` subdomain, or add a custom domain + CNAME.

---

## Step 5 — Networking

Northflank services in the same project can reach each other by internal hostname.

| From → To | Address | Notes |
|-----------|---------|-------|
| Frontend nginx → Backend | `http://<backend-svc-name>:8000` | Internal; set as `NGINX_PROXY_API_UPSTREAM` |
| Backend → Postgres | `postgresql+asyncpg://...@<pg-host>:5432/ragdb` | Use Northflank add-on connection string |
| Backend → Qdrant | `http://<qdrant-svc-name>:6333` | Internal service-to-service |
| Backend → Redis | `redis://<redis-host>:6379` | Internal |
| Browser → Frontend | `https://<frontend>.northflank.app` | Public TLS endpoint |
| Browser → Backend (CORS) | `https://<backend>.northflank.app` | Only needed if the SPA calls the API directly (VITE_API_BASE_URL) |

**CORS**: the backend's `CORS_ORIGINS` must include the frontend's public URL.

---

## Step 6 — First deploy checklist

1. **Postgres migrations** — the backend runs Alembic on startup (or run manually):
   ```bash
   # One-off Northflank job, or exec into the backend container:
   alembic upgrade head
   ```
2. **Verify health** — hit `https://<backend>.northflank.app/health`.
3. **Load the frontend** — `https://<frontend>.northflank.app` should show the UI.
4. **Upload a test document** and run a query to confirm the full pipeline (embedding → Qdrant → LLM → response).

---

## Resource sizing guidelines

| Service | CPU | RAM | Disk |
|---------|-----|-----|------|
| Backend | 0.5–1 vCPU | 2–4 GB | Volume: 2 GB (uploads) |
| Frontend | 0.1 vCPU | 128 MB | — |
| Postgres | 0.5 vCPU | 1 GB | 5 GB |
| Qdrant | 0.5 vCPU | 1–2 GB | 5 GB |
| Redis | 0.1 vCPU | 256 MB | — |

The backend is the heaviest — it loads spaCy, sentence-transformers for reranking, and Docling for document parsing. 2 GB RAM is the minimum; 4 GB is comfortable.

---

## Scaling

- **Frontend**: stateless, scale horizontally to as many replicas as needed.
- **Backend**: stateless (uploads go to the volume), safe to scale horizontally. The volume must be shared or replaced with object storage (S3/R2) for multi-replica.
- **Qdrant**: single-node is fine for moderate collections; for HA, use Qdrant Cloud instead.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| Frontend loads but API calls fail (CORS) | `CORS_ORIGINS` on backend doesn't include the frontend URL |
| Frontend shows blank page | `VITE_API_BASE_URL` wasn't set at build time — rebuild with the arg |
| Backend exits with OOM | Bump RAM to 4 GB; disable cross-encoder rerank (`ENABLE_CROSS_ENCODER_RERANK=false`) |
| Qdrant connection refused | Check `QDRANT_URL` uses the internal hostname, not `localhost` |
| Postgres "pgvector not found" | Run `CREATE EXTENSION IF NOT EXISTS vector;` in the database |
| nginx 502 on `/api/` | `NGINX_PROXY_API_UPSTREAM` points to wrong host; check backend is healthy |

---

## CI pipeline reference

The workflow at `.github/workflows/northflank-deploy.yml` handles the full flow:

1. Builds `backend/Dockerfile` → pushes to `ghcr.io/<org>/<repo>/rag-backend:<sha>`.
2. Builds `frontend/Dockerfile` with `VITE_API_BASE_URL` → pushes to `ghcr.io/<org>/<repo>/rag-frontend:<sha>`.
3. Deploys both to Northflank via the `northflank/deploy-to-northflank` action.

Set the GitHub secrets/variables listed in Step 3a and pushes to `main`/`master`/`develop` auto-deploy.

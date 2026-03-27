# RAG-v2.1 – Run Checklist & Test Plan

## Todo: Get System Running

- [x] Fix spaCy model download in Dockerfile (use pip wheel URL)
- [ ] Build and start stack
- [ ] Verify health and core API
- [ ] Smoke-test upload + chat

---

## 1. Build and Run

```bash
cd RAG-v2.1
docker-compose up -d --build
```

- **Frontend:** http://localhost:3000  
- **Backend API:** http://localhost:8000  
- **API docs:** http://localhost:8000/docs  

Nginx is commented out by default; frontend and backend are exposed directly. To use nginx on port 80, uncomment the `nginx` service in `docker-compose.yml`.

---

## 2. How We Test

### 2.1 Docker build

- **Pass:** `docker-compose build backend` completes with no errors.
- **Fail:** Any step fails (e.g. pip, spaCy model, system deps).

### 2.2 Containers up

```bash
docker-compose ps
```

- **Pass:** `postgres`, `qdrant`, `redis`, `backend`, `frontend` (and optionally `nginx`) are `Up`.

### 2.3 Health

```bash
curl -s http://localhost:8000/health | jq
```

- **Pass:** `"status": "healthy"`, `"mode"` and `"providers"` present.

### 2.4 API docs

- Open http://localhost:8000/docs  
- **Pass:** Swagger UI loads; no 5xx.

### 2.5 Upload + chat (smoke)

1. **Upload:** In UI or:

   ```bash
   curl -X POST http://localhost:8000/documents/upload \
     -F "file=@/path/to/small.pdf"
   ```

2. **Chat:** In UI send a short question about the document, or:

   ```bash
   curl -X POST http://localhost:8000/chat/query \
     -H "Content-Type: application/json" \
     -d '{"query": "Summarise the document", "document_ids": []}'
   ```

- **Pass:** Upload returns 200; chat returns an answer (and optional citations).

### 2.6 Auth (optional)

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
```

- **Pass:** Register and login return JSON with token/user data.

---

## 3. If Build Fails

- **Backend build:** Check backend Dockerfile and `requirements.txt`; ensure no typo in spaCy wheel URL.
- **Network:** Ensure Docker can reach GitHub (for the spaCy wheel).
- **Logs:** `docker-compose logs backend` (or the failing service).

---

## 4. Browser not connecting (page won’t load)

1. **Containers running**
   ```bash
   docker-compose ps
   ```
   `rag-frontend` and `rag-backend` must be **Up**. If frontend is Exit or Restarting, run `docker-compose logs frontend`.

2. **Try both URLs**
   - http://localhost:3000  
   - http://127.0.0.1:3000  
   Some setups only work with one of these.

3. **Check port from host**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000
   ```
   You want `200`. If you get `000` or “connection refused”, nothing is listening on 3000.

4. **Restart frontend**
   ```bash
   docker-compose up -d frontend
   ```
   Then wait a few seconds and open http://127.0.0.1:3000 again.

5. **Access from another machine (e.g. phone/tablet)**  
   Use your Mac’s IP instead of localhost, e.g. http://192.168.1.x:3000. Ensure no firewall is blocking ports 3000 or 8000.

---

## 5. "Network error" when uploading documents

The upload goes to **same origin** (`/api/documents/upload`), so the frontend nginx must proxy to the backend.

- **Rebuild frontend** so it uses the current page origin: `docker-compose up -d --build frontend`.
- **Open the app the same way you reach it**: e.g. if you use `http://localhost:3000`, use that (not `http://127.0.0.1:3000` in another tab). The upload URL is derived from the page origin.
- **Check backend is up**: `docker-compose ps` — `rag-backend` should be Up. `docker-compose logs backend` for errors.
- The UI now shows the exact URL it tried (e.g. `http://localhost:3000/api/documents/upload`). If that URL is correct and the backend is running, the failure is between frontend nginx and backend (e.g. backend not on `backend:8000`).

---

## 6. `curl http://localhost:8000/health` doesn’t work

The backend isn’t responding. Run these in order:

1. **Is the backend container running?**
   ```bash
   docker-compose ps
   ```
   If `rag-backend` is **Exited** or **Restarting**, it’s crashing before it can serve.

2. **Why is it failing?**
   ```bash
   docker-compose logs backend --tail 80
   ```
   Look for the last **Traceback** and **ImportError** or **ModuleNotFoundError**. Common causes:
   - `cached_download` / `huggingface_hub` → ensure `requirements.txt` has `huggingface_hub>=0.17,<0.20` and rebuild.
   - Missing or wrong env (e.g. `DATABASE_URL`, `DB_PASSWORD`) → check `.env` and docker-compose `environment`.

3. **Rebuild and start backend**
   ```bash
   docker-compose build --no-cache backend
   docker-compose up -d backend
   ```
   Wait 30–60 seconds (backend loads ML models on startup), then:
   ```bash
   curl -s http://127.0.0.1:8000/health
   ```
   Use `127.0.0.1` if `localhost` doesn’t work.

4. **Run backend in the foreground (see crash immediately)**
   ```bash
   docker-compose run --rm --service-ports backend
   ```
   You’ll see uvicorn logs and any Python traceback when it crashes.

5. **Port 8000 in use?**
   ```bash
   lsof -i :8000
   ```
   If another process is using 8000, stop it or change the host port in docker-compose (e.g. `"8001:8000"` and then `curl http://localhost:8001/health`).

---

## 7. If API / Health / Docs Not Working

1. **Containers:** `docker-compose ps` — `rag-backend` should be **Up** (and healthy if healthcheck runs).
2. **Backend logs:** `docker-compose logs backend` — look for import errors, DB or Qdrant connection errors, tracebacks.
3. **Rebuild backend:** `docker-compose up -d --build backend` — fix any build errors.
4. **Run backend locally (no Docker):** From `backend/`: set `DATABASE_URL`, `QDRANT_URL` (e.g. to your local Postgres/Qdrant), then `pip install -r requirements.txt` and `uvicorn main:app --reload`. Then try http://localhost:8000/health and http://localhost:8000/docs.

---

## 8. Quick Reference

| Service   | URL (no nginx)   | Purpose        |
|----------|-------------------|----------------|
| Frontend | http://localhost:3000 | UI             |
| Backend  | http://localhost:8000 | API            |
| API docs | http://localhost:8000/docs | Swagger        |
| Qdrant   | http://localhost:6333   | Vector store  |
| Postgres | localhost:5432          | Metadata DB   |
| Redis    | localhost:6379          | Cache / limit |

With nginx on port 80: use `http://localhost/api/` for API and `/` for frontend (if configured).

---

## 9. Stability Gates (Required)

Before release, run:

```bash
python verify_system.py --smoke
cd backend && pytest -q
```

For full validation in a live environment:

```bash
python verify_system.py --base-url http://localhost:8000
```

Release is blocked if any gate fails. See:

- `docs/OPERATIONS_RUNBOOK.md`
- `docs/REPRODUCIBILITY_BASELINES.md`
- `docs/STABILITY_RELEASE_GATES.md`

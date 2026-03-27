# RAG-v2.1 UIkit Frontend

Vanilla HTML/JS frontend using [UIkit](https://getuikit.com/). Same backend API as the React frontend; no build step.

## Quick start (CDN)

UIkit loads from CDN by default. Serve locally:

```bash
# With Docker (recommended)
cd ..
docker-compose -f docker-compose.yml -f docker-compose.uikit.yml up -d

# Or static server (backend must be running on :8010, CORS allowed)
npx serve . -p 3001
# Open http://localhost:3001 — set data-api-base="http://localhost:8010" on <html> if needed
```

## Local UIkit (git clone)

To bundle UIkit from source instead of CDN:

```bash
./setup-uikit.sh
```

This clones `https://github.com/uikit/uikit`, builds it, and copies `dist/` to `vendor/uikit/`. Rebuild the Docker image to include it.

## API

Uses the same endpoints as the React frontend: `/documents/`, `/chat/query`, `/chat/models`, etc. See `ARCHITECTURE.md`.

# Reproducibility Baselines

Stability depends on replaying the same configuration, corpus, and model path.

## Baseline profiles

Set in `.env`:

- `RUNTIME_STABILITY_PROFILE=stability_safe`
  - Conservative, lower-variance path.
  - Disables HyDE, fusion, corrective RAG, cross-encoder rerank.
  - `TOP_K_VECTOR_SEARCH=12`.

- `RUNTIME_STABILITY_PROFILE=stability_full`
  - Full stable path with all core RAG features enabled.
  - Uses `TOP_K_VECTOR_SEARCH=20`.

## Required run manifest

Record this for every benchmark or incident replay:

- date/time (UTC)
- git commit SHA
- environment (`local`, `docker`, `staging`)
- `RUNTIME_STABILITY_PROFILE`
- `config_fingerprint` (from startup/query logs)
- `DEFAULT_CLOUD_MODEL`, `OPENROUTER_FAST_MODEL`
- corpus snapshot identifier (document ids + upload timestamps)
- test query set version
- result summary (pass/fail, latency p50/p95, citation coverage)

## Replay workflow

1. Set profile in `.env`.
2. Restart backend.
3. Confirm startup log includes expected fingerprint.
4. Run:
   - `python verify_system.py --smoke`
   - `cd backend && pytest -q`
5. Compare metrics against previous manifest.

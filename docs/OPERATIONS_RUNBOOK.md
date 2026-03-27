# Operations Runbook (Stability)

Use this runbook when RAG responses are flaky, slow, or uncited.

## 1) Fast triage

1. Confirm backend health:
   - `curl -s http://localhost:8000/health | jq`
2. Confirm runtime profile/fingerprint in startup logs:
   - Look for `profile=` and `config_fingerprint=`.
3. Confirm recent query logs exist:
   - `GET /logs/queries?limit=20`
4. Confirm document state:
   - `GET /documents/` and verify target docs are `indexed`.

## 2) Symptom to checks

- Empty/weak answers:
  - Check `retrieved_chunks` length in `/chat/query` response.
  - Check query log `rag_meta.top_rerank_score` and `rag_meta.crag_action`.
  - Mitigation: switch to `RUNTIME_STABILITY_PROFILE=stability_full`.

- Slow responses:
  - Check whether cross-encoder rerank is enabled.
  - Mitigation: set `RUNTIME_STABILITY_PROFILE=stability_safe` for incident period.

- Intermittent ingest failures:
  - Inspect backend logs for `Background ingest failed`.
  - Re-run via `POST /documents/{document_id}/retry-ingest`.

- Missing citations:
  - Confirm reranked chunks exist and are returned.
  - Treat response as degraded if citations are zero.

## 3) Safe rollback toggles

Order of rollback (least invasive first):

1. `RUNTIME_STABILITY_PROFILE=stability_safe`
2. `ENABLE_CROSS_ENCODER_RERANK=false`
3. `ENABLE_CORRECTIVE_RAG=false`
4. `ENABLE_HYDE=false`
5. `ENABLE_FUSION_RETRIEVAL=false`

Restart backend after changes.

## 4) Incident capture checklist

For each incident, capture:

- UTC timestamp
- query text (or redacted form)
- `query_run_id`
- `RUNTIME_STABILITY_PROFILE`
- `config_fingerprint`
- model used
- document id/workspace id
- top rerank score
- citations count
- mitigation applied and outcome

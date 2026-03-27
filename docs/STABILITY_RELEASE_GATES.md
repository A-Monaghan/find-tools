# Stability Release Gates

A change is not release-ready until all gates pass.

## Gate 1: API smoke

- Command: `python verify_system.py --smoke`
- Must pass all checks.

## Gate 2: Backend test suite

- Command: `cd backend && pytest -q`
- Must pass with no new failures.

## Gate 3: Retrieval integrity

- Full verify run (environment with documents loaded):
  - `python verify_system.py --base-url http://localhost:8000`
- Chat check must return:
  - non-empty `answer`
  - non-empty `retrieved_chunks`
  - at least one citation

## Gate 4: Profile reproducibility

- Run once with `stability_safe` and once with `stability_full`.
- Each run must emit a `config_fingerprint`.
- Store both manifests in release notes.

## Gate 5: Ops readiness

- Runbook links present in release/PR description:
  - `docs/OPERATIONS_RUNBOOK.md`
  - `docs/REPRODUCIBILITY_BASELINES.md`
  - `docs/STABILITY_RELEASE_GATES.md`

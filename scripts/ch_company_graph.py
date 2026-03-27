#!/usr/bin/env python3
"""
CLI: print Companies House hop graph JSON from Neo4j (same logic as POST /ch/graph/hops).

Run from repo root with backend venv activated, or set PYTHONPATH=backend.

  cd RAG-v2.1 && PYTHONPATH=backend ./venv/bin/python scripts/ch_company_graph.py 12345678 --hops 2

Requires Neo4j loaded from CH pipeline CSVs: labels Company, Person; rels OFFICER_OF, PSC_OF.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root = parent of scripts/
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))

from services.ch_pipeline.ch_graph import get_company_hop_graph  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="CH company hop graph (Neo4j)")
    p.add_argument("company_number", help="UK company number")
    p.add_argument("--hops", type=int, default=2, help="1-4 (default 2)")
    p.add_argument("--max-nodes", type=int, default=400)
    p.add_argument("--max-edges", type=int, default=1200)
    args = p.parse_args()

    out = get_company_hop_graph(
        company_number=args.company_number,
        hops=args.hops,
        max_nodes=args.max_nodes,
        max_edges=args.max_edges,
    )
    if out.get("error"):
        print(json.dumps(out, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

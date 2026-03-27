"""
Companies House graph traversal helpers for Neo4j.

Builds an N-hop company-centred subgraph across Company/Person nodes.
"""

from __future__ import annotations

from typing import Any, Dict

from core.config import get_settings


def _get_driver():
    """Create Neo4j driver from app settings."""
    from neo4j import GraphDatabase

    s = get_settings()
    return GraphDatabase.driver(
        s.NEO4J_URI,
        auth=(s.NEO4J_USERNAME, s.NEO4J_PASSWORD),
    )


def get_company_hop_graph(
    company_number: str,
    hops: int = 2,
    max_nodes: int = 400,
    max_edges: int = 1200,
) -> Dict[str, Any]:
    """
    Return a CH subgraph rooted at one company number.

    Why this shape:
    - UI needs `nodes` + `edges` directly.
    - We keep only Company/Person nodes and core CH relationship types for speed.
    """
    cn = (company_number or "").strip().upper()
    if not cn:
        return {"error": "company_number is required"}

    # Defensive clamp (API schema already validates, but keep service safe in isolation).
    hop_depth = min(max(int(hops), 1), 4)
    node_cap = min(max(int(max_nodes), 50), 2000)
    edge_cap = min(max(int(max_edges), 100), 6000)

    driver = _get_driver()
    try:
        with driver.session() as session:
            # Root existence check gives clear user feedback instead of empty graph.
            root_row = session.run(
                """
                MATCH (c:Company)
                WHERE toUpper(coalesce(c.company_number, '')) = $cn
                RETURN coalesce(c.company_number, '') AS company_number, coalesce(c.name, c.company_number, 'Unknown') AS name
                LIMIT 1
                """,
                cn=cn,
            ).single()
            if not root_row:
                return {"error": f"Company not found: {cn}"}

            # Hop depth is inlined as a safe int so all Neo4j versions accept the range
            # (some drivers choke on parameters inside *1..$h).
            path_pattern = f"*1..{hop_depth}"
            records = session.run(
                f"""
                MATCH (root:Company)
                WHERE toUpper(coalesce(root.company_number, '')) = $cn
                MATCH p = (root)-[:OFFICER_OF|PSC_OF{path_pattern}]-(n)
                WHERE n:Company OR n:Person
                UNWIND relationships(p) AS rel
                WITH root, startNode(rel) AS a, endNode(rel) AS b, type(rel) AS rel_type
                WHERE (a:Company OR a:Person) AND (b:Company OR b:Person)
                  AND rel_type IN ['OFFICER_OF', 'PSC_OF']
                RETURN
                  coalesce(root.company_number, '') AS root_company_number,
                  coalesce(root.name, root.company_number, 'Unknown') AS root_name,
                  CASE
                    WHEN a:Person THEN coalesce(toString(a.person_id), toString(id(a)))
                    ELSE coalesce(toString(a.company_number), toString(id(a)))
                  END AS source_id,
                  labels(a)[0] AS source_label,
                  coalesce(a.name, a.name_full, a.company_number, a.person_id, 'Unknown') AS source_name,
                  coalesce(a.company_number, '') AS source_company_number,
                  coalesce(a.person_id, '') AS source_person_id,
                  CASE
                    WHEN b:Person THEN coalesce(toString(b.person_id), toString(id(b)))
                    ELSE coalesce(toString(b.company_number), toString(id(b)))
                  END AS target_id,
                  labels(b)[0] AS target_label,
                  coalesce(b.name, b.name_full, b.company_number, b.person_id, 'Unknown') AS target_name,
                  coalesce(b.company_number, '') AS target_company_number,
                  coalesce(b.person_id, '') AS target_person_id,
                  rel_type AS rel_type
                LIMIT $edge_cap
                """,
                cn=cn,
                edge_cap=edge_cap,
            )

            nodes: Dict[str, Dict[str, Any]] = {}
            edges: list[Dict[str, Any]] = []
            root_meta: Dict[str, Any] | None = None

            for r in records:
                root_meta = {
                    "id": r["root_company_number"] or cn,
                    "label": "Company",
                    "name": r["root_name"],
                    "company_number": r["root_company_number"] or cn,
                }

                sid = str(r["source_id"])
                tid = str(r["target_id"])
                s_label = str(r["source_label"] or "Node")
                t_label = str(r["target_label"] or "Node")

                nodes[sid] = {
                    "id": sid,
                    "label": s_label,
                    "name": r["source_name"],
                    "company_number": r["source_company_number"] or None,
                    "person_id": r["source_person_id"] or None,
                }
                nodes[tid] = {
                    "id": tid,
                    "label": t_label,
                    "name": r["target_name"],
                    "company_number": r["target_company_number"] or None,
                    "person_id": r["target_person_id"] or None,
                }

                edges.append(
                    {
                        "source": sid,
                        "target": tid,
                        "type": r["rel_type"],
                    }
                )

            if not root_meta:
                root_meta = {
                    "id": root_row["company_number"] or cn,
                    "label": "Company",
                    "name": root_row["name"],
                    "company_number": root_row["company_number"] or cn,
                }
            # Always show root company in the map (even when there are zero edges).
            if root_meta["id"] not in nodes:
                nodes[root_meta["id"]] = root_meta

            node_list = sorted(nodes.values(), key=lambda n: (n.get("label", ""), n.get("name", ""), n.get("id", "")))
            if len(node_list) > node_cap:
                # Keep root visible even when trimming (investigators always see the anchor company).
                root_id = str(root_meta["id"])
                root_node = nodes.get(root_id)
                others = [n for n in node_list if str(n.get("id")) != root_id]
                keep = (node_cap - 1) if root_node else node_cap
                node_list = ([root_node] if root_node else []) + others[:keep]

            node_ids = {n["id"] for n in node_list}
            edge_list = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

            truncated_nodes = len(nodes) > len(node_list)
            truncated_edges = len(edges) > len(edge_list)

            return {
                "root": root_meta,
                "hops": hop_depth,
                "nodes": node_list,
                "edges": edge_list,
                "truncated": {
                    "nodes": truncated_nodes,
                    "edges": truncated_edges,
                },
            }
    finally:
        driver.close()

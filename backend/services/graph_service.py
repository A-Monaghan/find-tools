"""
Neo4j graph service: push entities/relationships, fetch document graph,
neighbours, search. Used by graph API routes and optional doc ingest.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from models.database import Document, Chunk

logger = logging.getLogger(__name__)

# Map extraction labels to Neo4j labels (PascalCase); avoid "Document" for entity type
LABEL_MAP = {
    "PERSON": "Person",
    "ORGANIZATION": "Organization",
    "LOCATION": "Location",
    "EVENT": "Event",
    "DOCUMENT": "ReferenceDoc",
    "CONCEPT": "Concept",
}


def _get_driver():
    """Lazy Neo4j driver from settings."""
    from neo4j import GraphDatabase
    s = get_settings()
    return GraphDatabase.driver(
        s.NEO4J_URI,
        auth=(s.NEO4J_USERNAME, s.NEO4J_PASSWORD),
    )


def push_entities_relationships(
    entities: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    document_id: str,
) -> Dict[str, int]:
    """
    Push entities and relationships to Neo4j. Nodes are keyed by (id, document_id)
    so the same entity in different docs creates separate nodes.
    Returns {"nodes_created": N, "relationships_created": M}.
    """
    driver = _get_driver()
    nodes_created = 0
    rels_created = 0
    try:
        with driver.session() as session:
            for e in entities:
                nid = e.get("id") or ""
                name = e.get("name") or ""
                label = LABEL_MAP.get((e.get("label") or "CONCEPT").upper(), "Concept")
                if not nid:
                    continue
                result = session.run(
                    """
                    MERGE (n:%s {id: $id, document_id: $document_id})
                    ON CREATE SET n.name = $name, n.document_id = $document_id
                    ON MATCH SET n.name = $name
                    RETURN n
                    """ % label,
                    id=nid,
                    document_id=document_id,
                    name=name,
                )
                nodes_created += result.consume().counters.nodes_created
            for r in relationships:
                src = r.get("source")
                tgt = r.get("target")
                typ = (r.get("type") or "RELATED_TO").replace(" ", "_")
                if not src or not tgt:
                    continue
                result = session.run(
                    """
                    MATCH (a {id: $src, document_id: $doc_id})
                    MATCH (b {id: $tgt, document_id: $doc_id})
                    MERGE (a)-[r:%s]->(b)
                    RETURN r
                    """ % typ,
                    src=src,
                    tgt=tgt,
                    doc_id=document_id,
                )
                rels_created += result.consume().counters.relationships_created
        return {"nodes_created": nodes_created, "relationships_created": rels_created}
    finally:
        driver.close()


def get_document_graph(document_id: str) -> Dict[str, Any]:
    """Return nodes and relationships for a document. Keys: nodes, relationships."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            nodes_result = session.run(
                "MATCH (n) WHERE n.document_id = $doc_id RETURN n.id AS id, n.name AS name, labels(n)[0] AS label",
                doc_id=document_id,
            )
            nodes = [dict(record) for record in nodes_result]
            rels_result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.document_id = $doc_id AND b.document_id = $doc_id
                RETURN a.id AS source, b.id AS target, type(r) AS type
                """,
                doc_id=document_id,
            )
            relationships = [dict(record) for record in rels_result]
        return {"nodes": nodes, "relationships": relationships}
    finally:
        driver.close()


def get_neighbours(entity_id: str, document_id: Optional[str] = None) -> Dict[str, Any]:
    """One-hop neighbours of an entity. If document_id given, restrict to that doc."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            if document_id:
                r = session.run(
                    """
                    MATCH (n {id: $entity_id, document_id: $doc_id})
                    OPTIONAL MATCH (n)-[r]-(m)
                    WHERE m.document_id = $doc_id
                    RETURN n, collect({rel: r, other: m}) AS neighbours
                    """,
                    entity_id=entity_id,
                    doc_id=document_id,
                )
            else:
                r = session.run(
                    """
                    MATCH (n {id: $entity_id})
                    OPTIONAL MATCH (n)-[r]-(m)
                    RETURN n, collect({rel: r, other: m}) AS neighbours
                    """,
                    entity_id=entity_id,
                )
            record = r.single()
            if not record or not record["n"]:
                return {"node": None, "neighbours": []}
            n = record["n"]
            neighbours = []
            for item in record["neighbours"] or []:
                if item["rel"] and item["other"]:
                    rel = item["rel"]
                    other = item["other"]
                    neighbours.append({
                        "relationship_type": rel.type,
                        "direction": "out" if rel.start_node.element_id == n.element_id else "in",
                        "node_id": other.get("id"),
                        "node_name": other.get("name"),
                        "label": (other.labels or ["Concept"])[0],
                    })
            return {
                "node": {"id": n.get("id"), "name": n.get("name"), "label": (n.labels or ["Concept"])[0]},
                "neighbours": neighbours,
            }
    finally:
        driver.close()


def search_nodes(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Full-text style search on node name (case-insensitive contains)."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE n.name IS NOT NULL AND toLower(n.name) CONTAINS toLower($q)
                RETURN n.id AS id, n.name AS name, labels(n)[0] AS label, n.document_id AS document_id
                LIMIT $limit
                """,
                q=q or "",
                limit=limit,
            )
            return [dict(record) for record in result]
    finally:
        driver.close()


def get_schema_for_cypher() -> str:
    """Return a short schema summary for Text2Cypher prompts."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            labels = session.run(
                "CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName "
                "RETURN nodeLabels[0] AS label, collect(propertyName) AS props"
            ).data()
            rels = session.run(
                "CALL db.schema.relTypeProperties() YIELD relType, propertyName "
                "RETURN relType AS type"
            ).data()
        lines = ["Node labels: " + ", ".join(x.get("label", "") for x in labels if x.get("label"))]
        lines.append("Relationship types: " + ", ".join(x.get("type", "") for x in rels if x.get("type")))
        return "\n".join(lines) if any(labels + rels) else "No schema yet (empty graph)."
    except Exception as e:
        logger.warning("Schema introspection failed: %s", e)
        return "Node labels: Person, Organization, Location, Event, ReferenceDoc, Concept. Relationship types: EMPLOYED_BY, OWNED_BY, INVOLVED_IN, LOCATED_IN, MENTIONED_IN, RELATED_TO, PART_OF, FUNDED_BY."
    finally:
        driver.close()


def run_cypher(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run a read-only Cypher query and return records as list of dicts."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    finally:
        driver.close()


async def build_kg_for_document(document_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """
    Load document chunks from DB, extract entities/relationships via LLM,
    push to Neo4j. Used by POST /graph/build and by optional auto-ingest after indexing.
    """
    from services.entity_extraction_service import extract_entities_and_relationships

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": "Document not found"}
    chunks_result = await db.execute(
        select(Chunk.text_content).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    )
    texts = [row[0] for row in chunks_result.all() if row[0]]
    full_text = "\n\n".join(texts).strip()
    if not full_text:
        return {"error": "No text content for this document"}
    settings = get_settings()
    entities, relationships = await extract_entities_and_relationships(
        full_text,
        model=settings.GRAPH_EXTRACTION_MODEL,
    )
    doc_id_str = str(document_id)
    counts = push_entities_relationships(entities, relationships, doc_id_str)
    return {
        "status": "ok",
        "document_id": str(document_id),
        "entities_extracted": len(entities),
        "relationships_extracted": len(relationships),
        **counts,
    }

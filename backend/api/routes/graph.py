"""
Graph API routes: Neo4j status/stats, KG build from documents,
document graph, neighbours, search, and Graph Q&A (Text2Cypher).
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from api.dependencies import get_db
from services.graph_service import (
    build_kg_for_document,
    get_document_graph as svc_get_document_graph,
    get_neighbours as svc_get_neighbours,
    search_nodes as svc_search_nodes,
    get_schema_for_cypher,
    run_cypher,
)
from services.llm_router import get_llm_router

router = APIRouter(prefix="/graph", tags=["graph"])
logger = logging.getLogger(__name__)


def _driver():
    """Lazy Neo4j driver from settings."""
    from neo4j import GraphDatabase
    s = get_settings()
    return GraphDatabase.driver(
        s.NEO4J_URI,
        auth=(s.NEO4J_USERNAME, s.NEO4J_PASSWORD),
    )


@router.get("/status")
async def graph_status():
    """Check Neo4j connectivity."""
    try:
        driver = _driver()
        driver.verify_connectivity()
        driver.close()
        return {"connected": True}
    except Exception as e:
        logger.debug("Neo4j status check failed: %s", e)
        return {"connected": False, "error": str(e)}


@router.get("/stats")
async def graph_stats():
    """Node and relationship counts from Neo4j."""
    try:
        driver = _driver()
        with driver.session() as session:
            total_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            node_labels = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c ORDER BY c DESC"
            ).data()
            rel_types = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS c ORDER BY c DESC"
            ).data()
        driver.close()
        return {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "node_labels": [{"label": r["label"], "count": r["c"]} for r in node_labels],
            "relationship_types": [{"type": r["type"], "count": r["c"]} for r in rel_types],
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {e}")


@router.post("/build/{document_id}")
async def graph_build(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Build knowledge graph from a document: load chunks text, extract entities/relationships
    via LLM, push to Neo4j. Idempotent per document (re-run overwrites/merges).
    """
    result = await build_kg_for_document(document_id, db)
    if "error" in result:
        if result["error"] == "Document not found":
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/document/{document_id}")
async def graph_document(document_id: UUID):
    """Return nodes and relationships for a document (by UUID)."""
    try:
        return svc_get_document_graph(str(document_id))
    except Exception as e:
        logger.exception("get_document_graph failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighbours/{entity_id}")
async def graph_neighbours(entity_id: str, document_id: str | None = None):
    """One-hop neighbours of an entity; optional document_id to scope to that doc."""
    try:
        return svc_get_neighbours(entity_id, document_id)
    except Exception as e:
        logger.exception("get_neighbours failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def graph_search(q: str = "", limit: int = 20):
    """Search nodes by name (case-insensitive contains)."""
    try:
        return svc_search_nodes(q, limit=limit)
    except Exception as e:
        logger.exception("search_nodes failed")
        raise HTTPException(status_code=500, detail=str(e))


CYPHER_SYSTEM = (
    "You are a Cypher expert. Reply with ONLY a single Cypher query, no markdown, no explanation. "
    "Use only READ operations (MATCH, RETURN). No CREATE/SET/DELETE."
)
CYPHER_USER_TEMPLATE = """Schema:
{schema}

Question: {question}

Return only the Cypher query."""

ANSWER_USER_TEMPLATE = """Question: {question}

Query result (JSON-like):
{result}

Provide a short, direct answer based on the result."""


class GraphQueryBody(BaseModel):
    """Request body for Graph Q&A."""
    question: str


@router.post("/query")
async def graph_query(body: GraphQueryBody = Body(...)):
    """
    Graph Q&A: use LLM to generate Cypher from the question, run it, then
    use LLM to turn the result into a natural-language answer. Body: {"question": "..."}.
    """
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")
    schema = get_schema_for_cypher()
    router = get_llm_router()
    settings = get_settings()
    # Generate Cypher
    cypher_prompt = CYPHER_USER_TEMPLATE.format(schema=schema, question=q)
    try:
        cypher_response = await router.generate(
            prompt=cypher_prompt,
            system_message=CYPHER_SYSTEM,
            temperature=0,
            max_tokens=500,
            model=settings.GRAPH_EXTRACTION_MODEL,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM Cypher generation failed: {e}")
    cypher_text = (cypher_response.text or "").strip()
    # Strip markdown code block if present
    if "```" in cypher_text:
        m = re.search(r"```(?:cypher)?\s*([\s\S]*?)```", cypher_text)
        if m:
            cypher_text = m.group(1).strip()
    if not cypher_text or "MATCH" not in cypher_text.upper():
        raise HTTPException(status_code=400, detail="No valid Cypher query generated")
    try:
        rows = run_cypher(cypher_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher execution failed: {e}")
    # Limit result size for answer context
    result_str = str(rows[:30])
    answer_prompt = ANSWER_USER_TEMPLATE.format(question=q, result=result_str)
    try:
        answer_response = await router.generate(
            prompt=answer_prompt,
            system_message="Answer briefly based on the given query result.",
            temperature=0,
            max_tokens=500,
            model=settings.GRAPH_EXTRACTION_MODEL,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM answer generation failed: {e}")
    return {
        "question": q,
        "cypher": cypher_text,
        "result": rows,
        "answer": (answer_response.text or "").strip(),
    }

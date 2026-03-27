"""
Entity extraction for knowledge graph construction.

Uses the existing LLM router to extract entities and relationships from text.
Output format: entities [{id?, name, label}], relationships [{source, target, type}].
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from core.config import get_settings
from services.llm_router import get_llm_router

logger = logging.getLogger(__name__)

# Schema constraints for the LLM
ENTITY_LABELS = "PERSON, ORGANIZATION, LOCATION, EVENT, DOCUMENT, CONCEPT"
REL_TYPES = "EMPLOYED_BY, OWNED_BY, INVOLVED_IN, LOCATED_IN, MENTIONED_IN, RELATED_TO, PART_OF, FUNDED_BY"

SYSTEM_PROMPT = (
    "You are a JSON-only extraction assistant. Output exactly one valid JSON object, "
    "no markdown, no code fences, no explanation. Only raw JSON."
)

USER_TEMPLATE = f"""Extract entities and relationships from the text below. Reply with ONLY a JSON object in this shape:
{{"entities": [{{"name": "string", "label": "string"}}], "relationships": [{{"source": "string", "target": "string", "type": "string"}}]}}

Rules:
- Entity labels (use exactly): {ENTITY_LABELS}.
- Relationship types (use exactly): {REL_TYPES}.
- source and target must be exact entity names that appear in the entities list.
- Create relationships only when both source and target are in the text.
- Prefer specificity; no generic placeholders.

Text to analyze:
__TEXT__"""

# Max chars per LLM call to avoid context overflow
CHUNK_CHARS = 6000
OVERLAP_CHARS = 200


def _normalize_id(name: str) -> str:
    """Stable id from entity name for Neo4j MERGE."""
    s = re.sub(r"[^\w\s-]", "", name or "").strip().lower()
    s = re.sub(r"[-\s]+", "_", s)
    return s[:200] or "unknown"


def _parse_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from LLM response; strip markdown if needed."""
    text = (text or "").strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Find first { ... }
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _merge_entities(
    entities_list: List[List[Dict]],
    relationships_list: List[List[Dict]],
) -> Tuple[List[Dict], List[Dict]]:
    """Dedupe entities by (name, label); dedupe relationships by (source, target, type)."""
    seen_entities: set = set()
    merged_entities: List[Dict] = []
    for lst in entities_list:
        for e in lst:
            name = (e.get("name") or "").strip()
            label = (e.get("label") or "CONCEPT").strip().upper()
            if not name:
                continue
            key = (name, label)
            if key in seen_entities:
                continue
            seen_entities.add(key)
            merged_entities.append({
                "name": name,
                "label": label,
                "id": _normalize_id(name),
            })
    seen_rels: set = set()
    merged_rels: List[Dict] = []
    for lst in relationships_list:
        for r in lst:
            src = (r.get("source") or "").strip()
            tgt = (r.get("target") or "").strip()
            typ = (r.get("type") or "RELATED_TO").strip().upper()
            if not src or not tgt:
                continue
            key = (src, tgt, typ)
            if key in seen_rels:
                continue
            seen_rels.add(key)
            merged_rels.append({"source": _normalize_id(src), "target": _normalize_id(tgt), "type": typ})
    return merged_entities, merged_rels


async def extract_entities_and_relationships(
    text: str,
    model: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract entities and relationships from text using the LLM router.
    Chunks long text and merges results. Returns (entities, relationships).
    """
    settings = get_settings()
    model = model or settings.GRAPH_EXTRACTION_MODEL
    router = get_llm_router()

    text = (text or "").strip()
    if not text:
        return [], []

    # Chunk long text
    chunks = []
    if len(text) <= CHUNK_CHARS:
        chunks.append(text)
    else:
        start = 0
        while start < len(text):
            end = start + CHUNK_CHARS
            chunk = text[start:end]
            # Try to break at paragraph
            if end < len(text):
                last_para = chunk.rfind("\n\n")
                if last_para > CHUNK_CHARS // 2:
                    chunk = chunk[: last_para + 1]
                    end = start + len(chunk)
            chunks.append(chunk)
            start = end - OVERLAP_CHARS if end < len(text) else len(text)

    all_entities = []
    all_relationships = []
    for i, chunk in enumerate(chunks):
        prompt = USER_TEMPLATE.replace("__TEXT__", chunk[:50000])
        try:
            response = await router.generate(
                prompt=prompt,
                system_message=SYSTEM_PROMPT,
                temperature=0,
                max_tokens=2000,
                model=model,
            )
            data = _parse_json_from_response(response.text)
            if data:
                entities = data.get("entities") or []
                relationships = data.get("relationships") or []
                if isinstance(entities, list) and isinstance(relationships, list):
                    all_entities.append(entities)
                    all_relationships.append(relationships)
        except Exception as e:
            logger.warning("Entity extraction chunk %s failed: %s", i + 1, e)

    return _merge_entities(all_entities, all_relationships)

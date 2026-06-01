# LangChain Agentic Architecture — FIND Tools

**Status:** Planning  
**Audience:** Engineers extending FIND Tools with autonomous agent capabilities  
**Language:** UK English

---

## Executive Summary

FIND Tools already has a mature RAG pipeline, external API integrations (Companies House, OpenSanctions, Aleph, Sayari), entity extraction, and knowledge graph capabilities. What it lacks is **orchestration** — the ability to chain these tools autonomously in a plan→act→observe→revise loop.

LangChain (specifically **LangGraph**) provides the agent runtime to connect existing services into multi-step investigative workflows without rewriting the core RAG or ingestion logic.

---

## Why LangGraph over vanilla LangChain agents

| Concern | LangChain AgentExecutor | LangGraph |
|---------|------------------------|-----------|
| State management | Flat message list | Typed state graph with persistence |
| Branching / parallel | Limited | First-class conditional edges, fan-out |
| Human-in-the-loop | Bolt-on | Native interrupt/resume |
| Checkpointing | None | Built-in (Postgres, Redis, SQLite) |
| Streaming | Partial | Full token + tool-call streaming |
| Debugging | Callbacks | LangSmith trace + visual graph |
| Controllability | Model decides everything | You define the graph; model fills slots |

For investigation workflows — where auditability, human approval, and complex branching matter — **LangGraph** is the correct choice. Pure ReAct agents are too unpredictable for compliance-sensitive work.

---

## Architecture: Where LangChain fits

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React)                                           │
│  New: AgentWorkflowPanel — kick off, monitor, approve steps │
└───────────────────────┬─────────────────────────────────────┘
                        │ WebSocket / SSE
┌───────────────────────▼─────────────────────────────────────┐
│  FastAPI — existing routes + new /agent/* routes             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  LangGraph Agent Runtime (new)                      │    │
│  │                                                     │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐   │    │
│  │  │ Planner   │→ │ Executor  │→ │ Synthesiser   │   │    │
│  │  │ (LLM)     │  │ (tools)   │  │ (LLM)        │   │    │
│  │  └───────────┘  └─────┬─────┘  └───────────────┘   │    │
│  │                        │                             │    │
│  │            ┌───────────┼───────────┐                 │    │
│  │            ▼           ▼           ▼                 │    │
│  │  ┌─────────────┐ ┌─────────┐ ┌──────────────┐      │    │
│  │  │ RAG Query   │ │ CH API  │ │ Screening    │      │    │
│  │  │ (existing)  │ │(existing│ │ (existing)   │      │    │
│  │  └─────────────┘ └─────────┘ └──────────────┘      │    │
│  │  ┌─────────────┐ ┌─────────┐ ┌──────────────┐      │    │
│  │  │ Graph Query │ │ Web     │ │ Entity       │      │    │
│  │  │ (existing)  │ │ Search  │ │ Extractor    │      │    │
│  │  └─────────────┘ └─────────┘ └──────────────┘      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  Existing services (unchanged)                              │
└─────────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   PostgreSQL        Qdrant          Neo4j
   (state +          (vectors)       (graph)
    checkpoints)
```

**Key principle:** LangGraph orchestrates; existing services do the work. No rewriting of the RAG pipeline, CH pipeline, or screening logic.

---

## Tool Wrappers: Bridging existing services to LangGraph

Each existing service becomes a **LangChain Tool** (thin async wrapper):

```python
# backend/agents/tools/rag_tool.py
from langchain_core.tools import tool

@tool
async def query_documents(
    query: str,
    workspace_id: str | None = None,
    document_ids: list[str] | None = None,
) -> str:
    """Search the document corpus using RAG. Returns cited passages.
    Use when you need factual answers grounded in uploaded documents."""
    # Calls existing chat.py logic internally
    ...

@tool
async def search_companies_house(
    query: str,
    search_type: str = "company",  # company | officer | name
) -> str:
    """Search UK Companies House registry. Returns company details,
    officers, PSC (persons of significant control), and filing history."""
    # Calls existing ch_pipeline service
    ...

@tool
async def screen_entity(
    name: str,
    dob: str | None = None,
    sources: list[str] = ["opensanctions", "aleph"],
) -> str:
    """Screen a person or entity against sanctions, PEP, and
    adverse media databases. Returns fuzzy matches with scores."""
    # Calls existing screening service
    ...

@tool
async def query_knowledge_graph(
    question: str,
    document_id: str | None = None,
) -> str:
    """Query the Neo4j knowledge graph using natural language.
    Returns entities, relationships, and paths."""
    # Calls existing graph service (NL→Cypher)
    ...

@tool
async def extract_entities(url: str | None = None, text: str | None = None) -> str:
    """Extract named entities and relationships from a URL or text.
    Returns structured entity data (people, companies, locations)."""
    # Calls existing entity extractor sidecar
    ...

@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web for recent information not in the corpus.
    Use as a last resort when documents and databases lack coverage."""
    # Extends existing CRAG web fallback
    ...
```

---

## Use Case 1: Financial Investigation Agent

**Trigger:** Analyst provides a company name or person + suspicion.  
**Goal:** Produce a structured intelligence report with corporate links, beneficial ownership, sanctions hits, and supporting evidence from documents.

### Graph definition

```
┌──────────┐     ┌──────────────┐     ┌───────────┐
│ Receive  │────▶│ Plan         │────▶│ Execute   │──┐
│ Brief    │     │ Investigation│     │ Step      │  │
└──────────┘     └──────────────┘     └───────────┘  │
                        ▲                    │        │
                        │                    ▼        │
                 ┌──────┴──────┐     ┌───────────┐   │
                 │ Revise Plan │◀────│ Evaluate  │   │
                 │ (if gaps)   │     │ Progress  │   │
                 └─────────────┘     └───────────┘   │
                                           │         │
                              ┌─────────────┘         │
                              ▼                       │
                     ┌─────────────────┐              │
                     │ Human Approval  │◀─────────────┘
                     │ (if high-risk)  │   (sensitive step)
                     └────────┬────────┘
                              │ approved
                              ▼
                     ┌─────────────────┐
                     │ Synthesise      │
                     │ Report          │
                     └─────────────────┘
```

### Typical tool sequence

1. `search_companies_house(name)` → get company numbers, officers
2. `screen_entity(officer_name, dob)` → sanctions/PEP check each officer
3. `query_documents(query about company)` → evidence from uploaded docs
4. `query_knowledge_graph(relationship query)` → network hops
5. `web_search(adverse media query)` → public domain coverage
6. → Synthesise into structured report with provenance

### State schema

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class FinancialInvestigationState(TypedDict):
    messages: Annotated[list, add_messages]
    brief: str                    # initial request
    plan: list[str]              # investigation steps
    current_step: int
    findings: list[dict]         # tool results per step
    entities_screened: list[dict] # sanctions results
    requires_approval: bool      # human gate flag
    report: str | None           # final output
```

---

## Use Case 2: Investigation Research Agent

**Trigger:** Analyst uploads documents and asks a complex research question spanning multiple sources.  
**Goal:** Multi-hop reasoning across documents, graph, and external sources with full citation chain.

### How it differs from current RAG

Current RAG is **single-turn**: embed → retrieve → answer. The research agent adds:

- **Iterative deepening** — if first retrieval is insufficient, reformulate and search again
- **Cross-document synthesis** — combine findings from multiple documents in one workspace
- **Source triangulation** — verify claims across RAG, graph, and web
- **Gap identification** — explicitly state what could not be confirmed

### Graph structure

```
Start → Decompose Question → [parallel sub-questions]
         ↓ for each sub-question
    RAG Query → Evaluate Sufficiency
         ↓ insufficient
    Graph Query → Web Search → Merge
         ↓ sufficient
    Collect Answer
         ↓ all sub-questions done
    Synthesise → Identify Gaps → Final Report
```

This leverages LangGraph's **fan-out/fan-in** pattern: decompose into N sub-questions, execute them in parallel, collect results, then synthesise.

---

## Use Case 3: Funding Proposal Research Agent

**Trigger:** Researcher provides a funding body name or programme, plus their research area.  
**Goal:** Structured brief on eligibility, deadlines, past awards, strategic fit, with recommended approach.

### Tool additions needed

```python
@tool
async def search_funding_databases(
    funder: str | None = None,
    research_area: str | None = None,
    country: str = "UK",
) -> str:
    """Search funding databases (UKRI Gateway, EU CORDIS, etc.)
    for open calls, eligibility criteria, and past awards."""
    ...

@tool
async def analyse_past_awards(
    funder: str,
    topic: str,
    years: int = 3,
) -> str:
    """Retrieve and summarise past successful awards from a funder
    in a given topic area. Identifies patterns in funded projects."""
    ...
```

### Workflow

1. Identify relevant funding calls (tool + web search)
2. Extract eligibility criteria from call documents (RAG on uploaded PDFs)
3. Analyse past successful awards for patterns
4. Cross-reference with researcher's profile/documents
5. Synthesise into a brief: eligibility Y/N, strategic alignment, deadline, recommended angle

---

## Use Case 4: Sanctions Screening Agent

**Trigger:** Analyst provides a list of names (e.g., from a transaction batch) or a single complex entity network.  
**Goal:** Comprehensive screening with fuzzy matching, network expansion, and risk scoring.

### Why an agent beats the current endpoint

The current `/screening/search` is **single-name, single-call**. An agent adds:

- **Batch processing** with intelligent prioritisation (screen high-risk first)
- **Network expansion** — if a hit is found, automatically screen associated persons
- **Alias generation** — LLM generates transliteration variants, maiden names, known aliases
- **Cross-referencing** — check Companies House for directorships of matched persons
- **Risk aggregation** — produce a scored summary across all sources

### Graph structure

```
Receive Names → Generate Aliases (LLM)
    ↓
Screen Each (parallel, rate-limited)
    ↓
Filter Hits (above threshold)
    ↓
Expand Network (CH officers, graph hops)
    ↓
Screen Expanded Names
    ↓
Aggregate → Risk Score → Report
    ↓ (if high-risk)
Human Review Gate
```

### State schema

```python
class SanctionsScreeningState(TypedDict):
    messages: Annotated[list, add_messages]
    input_names: list[dict]        # name, dob, context
    aliases_generated: list[dict]  # LLM-expanded variants
    screening_results: list[dict]  # per-name hits
    expanded_entities: list[dict]  # network connections
    risk_scores: dict[str, float]  # aggregated risk per entity
    requires_review: list[str]     # names needing human review
    report: str | None
```

---

## Use Case 5: Case Building Agent

**Trigger:** Analyst has completed initial investigation; wants to assemble evidence into a structured case file.  
**Goal:** Organised case package with evidence chain, timeline, entity map, and narrative summary.

### This is an orchestration workflow

The case builder doesn't do new research — it synthesises existing workspace data:

1. **Gather** all messages, findings, screening results, graph entities from a workspace
2. **Timeline** — extract dates from documents and order events chronologically
3. **Entity map** — pull all persons/companies from graph + screening into a relationship diagram
4. **Evidence chain** — for each factual claim, trace back to source document + page
5. **Narrative** — LLM writes a structured narrative connecting evidence to the brief
6. **Gaps report** — identify what hasn't been confirmed

### Output artefacts

- Structured JSON case file (importable into case management systems)
- PDF report with citations
- Neo4j subgraph export (for visual relationship mapping)
- Timeline CSV
- Risk assessment matrix

---

## Implementation Plan

### Phase 1: Foundation (smallest shippable agent)

**Goal:** One working agent (Financial Investigation) proving the architecture.

| Component | Work |
|-----------|------|
| `backend/agents/__init__.py` | Package init |
| `backend/agents/tools/` | Tool wrappers around existing services |
| `backend/agents/graphs/financial_investigation.py` | LangGraph state graph |
| `backend/agents/state.py` | Shared state types |
| `backend/agents/checkpointer.py` | Postgres checkpointer config |
| `backend/api/routes/agents.py` | `/agent/run`, `/agent/status/{id}`, `/agent/approve/{id}` |
| `requirements.txt` additions | `langchain-core`, `langgraph`, `langchain-openai` |

**Not in Phase 1:** New frontend panel, new external APIs, batch operations.

### Phase 2: Multi-agent expansion

- Research agent (decompose + parallel)
- Sanctions batch screening agent
- Case builder agent
- Frontend: AgentWorkflowPanel with step visualisation
- LangSmith integration for observability

### Phase 3: Production hardening

- Human-in-the-loop approval UI
- Rate limiting and budget caps per agent run
- Agent evaluation suite (golden cases per `OSINT_AGENTIC_PROMPTS.md` §8)
- Streaming intermediate results to frontend
- Multi-tenant isolation (agent runs scoped to workspace)

---

## Dependencies

```
# Add to requirements.txt
langchain-core>=0.3
langgraph>=0.4
langchain-openai>=0.3          # for ChatOpenAI (works with OpenRouter too)
langgraph-checkpoint-postgres   # persist state to existing Postgres
```

**No heavyweight dependencies needed.** LangGraph is lightweight — it's a state machine library, not a monolith. The `langchain-community` mega-package is *not* required; we only need `langchain-core` for base types and tool decorators.

---

## Integration with existing config

```python
# backend/core/config.py additions
class Settings(BaseSettings):
    # ... existing fields ...

    # === AGENT RUNTIME ===
    ENABLE_AGENTS: bool = Field(default=False, description="Enable agentic workflows")
    AGENT_MAX_ITERATIONS: int = Field(default=15, description="Max plan-execute loops")
    AGENT_MAX_TOOL_CALLS: int = Field(default=30, description="Budget cap per run")
    AGENT_REQUIRE_APPROVAL: bool = Field(
        default=True,
        description="Require human approval for sensitive actions",
    )
    LANGSMITH_API_KEY: Optional[str] = Field(default=None, description="LangSmith tracing")
    LANGSMITH_PROJECT: str = Field(default="find-tools-agents", description="LangSmith project")
```

The LLM routing uses the existing `llm_router.py` — LangGraph calls it via a `ChatOpenAI` instance pointed at OpenRouter (already configured) or vLLM.

---

## How existing services remain unchanged

| Existing service | Agent interaction | Changes needed |
|-----------------|-------------------|----------------|
| `llm_router.py` | Agent uses same LLM via `ChatOpenAI(base_url=openrouter)` | None |
| `vector_store.py` | RAG tool calls existing search | None |
| `fusion_retrieval.py` | RAG tool uses it internally | None |
| `ch_pipeline/` | CH tool wraps existing pipeline | Thin async wrapper |
| `screening.py` route | Screening tool calls same logic | Extract to service function |
| `graph_service.py` | Graph tool calls `nl_to_cypher` | None |
| `entity_extraction_service.py` | Entity tool wraps it | None |
| `ingest_pipeline.py` | Unchanged — agents query, don't ingest | None |
| `citation_service.py` | Used inside RAG tool | None |

**Total backend changes for Phase 1:** ~5 new files (agent package), 1 new route file, minor refactors to extract shared logic from route handlers into reusable functions.

---

## Observability and auditability

Every agent run produces:

1. **Checkpoint trail** — full state at each graph node (Postgres, recoverable)
2. **Tool call log** — which tool, what args, what result (maps to existing `QueryLog`)
3. **LangSmith trace** (optional) — full LLM call tree for debugging
4. **Final report** stored as a workspace artefact

This aligns with the existing philosophy of "investigator transparency" (retrieval traces, query logs).

---

## Risk assessment

| Risk | Mitigation |
|------|------------|
| Agent loops indefinitely | Hard iteration cap (`AGENT_MAX_ITERATIONS`), tool call budget |
| LLM hallucinates in investigation | Citation validation (existing); tool results are ground truth |
| Rate-limit external APIs | Per-tool rate limiters; agent pauses on 429 |
| Sensitive actions without oversight | Human-in-the-loop gate for screening, CH downloads |
| Cost runaway (many LLM calls) | Token budget tracking; cheaper model for planning, expensive for synthesis |
| Scope creep in agent plans | Constrained tool set; system prompt defines boundaries |

---

## Relationship to `OSINT_AGENTIC_PROMPTS.md`

The existing prompt library (`docs/OSINT_AGENTIC_PROMPTS.md`) defines a **manual** agentic workflow: copy-paste prompts, fill contracts, design tools. LangGraph **automates** this:

| OSINT prompt section | LangGraph equivalent |
|---------------------|---------------------|
| §1 Research contract | Agent's initial brief (input state) |
| §3 Tool inventory | LangChain tool definitions |
| §4 Agent system prompt | Graph node prompts (planner, executor) |
| §5 Tool schemas | `@tool` decorator with docstrings |
| §6 Planner–executor split | Separate graph nodes with typed state |
| §8 Evaluation | Golden-case test suite against agent outputs |

---

## Next steps

1. **Validate approach** — review this document; confirm use-case priority order
2. **Prototype** — implement Phase 1 (financial investigation agent) behind feature flag
3. **Test** — run against 2–3 real investigation scenarios from `docs/` briefs
4. **Iterate** — refine tool schemas based on what the agent actually needs
5. **Expand** — add remaining agents (Phase 2) once architecture is proven

---

*Document version: 1.0 — planning draft for LangChain/LangGraph integration into FIND Tools.*

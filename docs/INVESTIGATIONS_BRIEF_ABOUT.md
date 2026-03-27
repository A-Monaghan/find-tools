# About — investigations brief

**Audience:** Investigators, intelligence leads, and programme stakeholders  
**Purpose:** **In-product orientation** — what RAG-v2.1 modules do and how **document-grounded chat** fits together.

---

## 1. Why this tab exists

Complex workspaces need a **single place** to explain scope: which capabilities are **inside** the deployment versus **external** integrations, and where to change **settings** (e.g. Chat prompts, Entity Extractor keys, Companies House key). **About** is that **read-only narrative** — it does not execute pipelines.

---

## 2. Pipeline

No data pipeline. Content is **static help text** rendered in the browser.

---

## 3. “Datasets”

None. The tab **describes** modules; it does not query stores.

---

## 4. What the client must provide

| Item | Notes |
|------|--------|
| **No credentials** | Not applicable. |
| **Content updates** | If you fork the product, replace copy here to match **your** governance and support contacts. |

---

## 5. Expected outcomes

- New users understand **Chat** (citations, models), **Entity Extractor** (URL/text → graph), and **Companies House** (UK registry pulls).
- Short **ordered list** explains retrieval-augmented generation at a **conceptual** level (upload → chunk → embed → retrieve → answer with citations).

---

## 6. User interface (actual behaviour)

- Scrollable page: **module cards**, **how RAG works** list, **LLM provider** overview (local vLLM vs cloud OpenRouter).

---

## 7. Operational notes

- Treat About as **documentation of record only if you maintain it**; procurement and security approvals still rely on **formal architecture** documents, not this screen alone.

---

*Document version: aligned with RAG-v2.1 About tab.*

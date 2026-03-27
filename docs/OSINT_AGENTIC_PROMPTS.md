# OSINT agentic prompts

**Audience:** Engineers and analysts building **agentic** (tool-using, looped) workflows for **open-source intelligence**—or using an LLM to scaffold such tools.  
**Purpose:** Copy-paste **prompt templates** with `{placeholders}`. Fill a **research contract** first, then design tools, agent behaviour, implementation, and evaluation.  
**Language:** UK English.

---

## Disclaimer and ethics

- Use these prompts only for **lawful** purposes and in line with your organisation’s policies, applicable **terms of service**, **robots.txt**, and **data protection** rules.
- This document does **not** help evade technical controls, authentication, or rate limits.
- Treat external lookups as **uncontrolled** where relevant: **case separation** matters—do not paste **classified** or **legally restricted** material into arbitrary third-party tools. Apply your **internet use** and **vendor due diligence** policies to every data source.
- You are responsible for **proportionality**, **minimisation** of personal data, and **auditability** of what you build.

---

## How to use this file

Paste a template into your assistant (e.g. Cursor, ChatGPT), replace every `{placeholder}`, then run templates **in order** where possible: **research contract** → **tool inventory** → **tool schemas** → **agent system prompt** → **implementation** → **evaluation** → **hardening**. For greenfield work, complete the contract before writing code so the agent loop has a clear **stop condition** and **metric**.

---

## Recommended flow

```mermaid
flowchart LR
  RC[ResearchContract]
  TI[ToolInventory]
  TS[ToolSchemaPrompt]
  AS[AgentSystemPrompt]
  IM[Implement]
  EV[EvaluateAgainstMetric]

  RC --> TI --> TS --> AS --> IM --> EV
```

---

## 1. Research contract (Karpathy-style autoresearch shell)

**When to use:** Before any tool design or coding. Fixes **scope**, **constraints**, **output shape**, and **what “done” means**.

```text
You are helping define an OSINT research run that will be executed by an agent with tools (plan → act → observe → revise).

Fill and return these sections in UK English. Do not invent facts; mark unknowns explicitly.

## Input (seeds)
{input_description}
- Fixed inputs (must not be changed by the agent): ...
- Derived inputs the agent may compute: ...

## Scope
{scope_description}
- In scope (questions, jurisdictions, source types): ...
- Out of scope (explicit non-goals): ...

## Constraints
{constraints_description}
- Legal / policy: ...
- Technical (rate limits, timeouts, max tool calls, max iterations): ...
- OPSEC / handling: ...

## Metric (output quality and improvement)
{metric_description}
- Primary success metric (measurable): ...
- Secondary metrics: ...
- Stop rule: the run stops when ... OR after ... iterations / budget.

## Output (artefacts)
{output_description}
- Required fields / schema / sections: ...
- Provenance: each factual claim must cite ...

## Autoresearch loop (agent behaviour)
The agent must:
1. Write a short plan (bullet list) against Scope.
2. Call tools only to satisfy the plan; record raw observations.
3. Compare results to the Metric; if not met, revise the plan (max {N} outer iterations).
4. Emit the Output in the specified shape; list gaps and uncertainties.

Respond with the completed contract only.
```

---

## 2. Product and investigation framing

**When to use:** When the contract needs a clearer **investigation type** (entity, network, document, geospatial) before tightening scope.

```text
Summarise this OSINT product or investigation in one page (UK English).

Context:
- Investigation type: {entity | network | document | geo | mixed}
- Primary user: {analyst | engineer | both}
- Time horizon: {one-off | recurring}

Answer:
1. One-sentence mission.
2. Inputs (bullets).
3. Outputs (artefact types: CSV, graph, PDF digest, etc.).
4. Non-goals (what we will not do).
5. OPSEC notes (what must stay local, what must be redacted in logs).

Placeholders to replace: {mission_hint}, {user_type}, {horizon}.
```

---

## 3. Tool inventory

**When to use:** After the contract; before drafting JSON/tool schemas.

```text
Propose a minimal **tool inventory** for this OSINT agent. One primary capability per tool; no “god tools.”

Research contract summary:
{paste_or_summarise_contract}

For each candidate tool, provide:
- name (snake_case)
- purpose (one line)
- external dependency (API, HTTP GET, local DB, etc.)
- rate limit / cost assumptions
- failure modes (timeout, 403, empty result)
- human-only alternative (if any)

Mark tools that must **not** be automated (e.g. paywalled, legally sensitive). End with a list of tools to implement in **phase 1** (smallest shippable set).
```

---

## 4. Agent system prompt (architecture)

**When to use:** When wiring an LLM that calls tools in a loop (API or framework).

```text
Draft a **system prompt** for an OSINT research agent that uses tools.

Contract (condensed):
{paste_or_summarise_contract}

Requirements:
- Role: careful OSINT assistant; no speculation presented as fact.
- Always cite sources from tool output; if missing, say “uncited.”
- Refuse requests that violate Constraints (quote the constraint).
- Tool use: minimal calls; prefer idempotent queries; backoff on errors.
- Loop: plan briefly → tools → summarise observations → check Metric → stop or revise (max {N} iterations, max {M} tool calls per iteration).
- Output: match the Output section of the contract; include a “Limitations” subsection.

Return only the system prompt text, ready to paste.
```

---

## 5. Tool schema design (functions / JSON)

**When to use:** When exposing tools to the model (OpenAI functions, MCP, etc.).

```text
Design JSON **function specifications** for these tools: {tool_name_list}

For each function, output:
- "name", "description" (what/when not to use)
- "parameters" JSON Schema (types, required fields, enums)
- Expected return shape (structured fields, not free prose)
- Idempotency note (same args → same logical result?)
- Error contract (e.g. { "error": "rate_limited", "retry_after_sec": n })

Map each function to exactly one HTTP/API action or one local query where possible.
```

---

## 6. Planner–executor split (optional)

**When to use:** When the model over-calls tools or drifts; separate planning from execution.

**Planner prompt:**

```text
You are a **planner** only. You do not call tools.

Given the research contract:
{paste_contract}

Produce:
1. Assumptions (max 5).
2. Ordered checklist of sub-goals (each testable).
3. Which tools (by name) are likely needed per sub-goal.
4. Risks (ambiguity, single points of failure).

Max {P} lines. No tool calls.
```

**Executor prompt:**

```text
You are an **executor**. You may only call tools from the allowed list and must follow the plan.

Contract + metric:
{paste_contract}

Plan:
{paste_plan}

Rules:
- Execute the next unchecked sub-goal; call only necessary tools.
- After each tool, append a one-line observation (fact + citation id from result).
- If metric is met, produce final Output per contract; else return “continue” with revised next step.

Max tool calls this turn: {M}.
```

---

## 7. Implementation stub (minimal service or CLI)

**When to use:** When generating application code around the agent.

```text
Generate a minimal implementation skeleton for: {language_framework}
(e.g. Python CLI, FastAPI app)

Requirements:
- Read config from environment variables ({list_keys}); no secrets in logs.
- Structured logging (JSON or key=value); redact tokens and API keys.
- One module per tool adapter; shared HTTP client with timeouts and retries (bounded).
- Entrypoint: {cli_or_route_description}
- Tests: one smoke test that mocks HTTP.

Do not add unused dependencies. Match existing project style if a repo path is provided: {optional_repo_path}
```

---

## 8. Evaluation and regression

**When to use:** After first implementation; before widening scope.

```text
Define evaluation for this OSINT agent against the contract.

Contract:
{paste_contract}

Provide:
1. **Golden cases** (3–10): input → expected properties of output (not necessarily exact text), including negative cases.
2. **Automatic checks** (scripts or assertions): schema validation, required citations present, no empty mandatory fields.
3. **Hallucination checks**: flag any URL, registry ID, or date not present in tool outputs (diff against observation trace).
4. **Regression policy**: what must pass before merge / release.

Metric alignment: explicitly map each check to the Metric section.
```

For this repository, pair the evaluation output with:

- `docs/REPRODUCIBILITY_BASELINES.md` (run manifest fields)
- `docs/STABILITY_RELEASE_GATES.md` (release pass criteria)

---

## 9. Hardening and abuse review

**When to use:** Before production or wider deployment.

```text
Review this OSINT agent design and code for security and safety issues.

Artifacts:
{paste_or_point_to_summaries_of_system_prompt_tool_schemas_and_code}

Checklist (answer each with risk level + mitigation):
1. **Prompt injection**: untrusted HTML/PDF text fed back into the model; quoting rules.
2. **SSRF / open redirects**: user-supplied URLs passed to server-side fetchers.
3. **Secrets**: API keys in env only; logs redacted.
4. **PII**: unnecessary personal data in logs or outputs.
5. **Rate limiting**: client-side backoff; user-visible errors.

Output a short table: issue, severity, fix.
```

---

## Appendix: OSINT phases and which prompt to run

| Phase | Aim | Run first |
|--------|-----|------------|
| Plan | Agree question, contract, metric | §1 Research contract |
| Collect | Choose sources and tools | §3 Tool inventory → §5 Tool schemas |
| Process | Normalise, dedupe, store | §7 Implementation (adapters) |
| Analyse | Reason over observations | §4 System prompt / §6 Planner–executor |
| Report | Emit Output + limitations | §1 (Output section) + §8 Evaluation |

---

*Document version: 1.0 — prompt library for agentic OSINT tooling.*

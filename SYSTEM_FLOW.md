## RAG-v2.1 – System Flow

This document shows the main data and control flow for the RAG-v2.1 system.

### High-level architecture

```mermaid
%%{init: {'theme':'base', 'themeVariables': {'fontSize':'12px'}, 'flowchart': {'useMaxWidth':true}}}%%
flowchart LR
    subgraph UI
        User["User"]
        FE["Frontend"]
    end
    subgraph Backend
        API["FastAPI"]
        DOCS["Documents"]
        CHAT["Chat/RAG"]
        EMB["Embed"]
        RER["Rerank"]
        LLM["LLM"]
    end
    subgraph Data
        DB["PostgreSQL"]
        VEC["Vector Store"]
    end
    User --> FE
    FE --> API
    API --> DOCS
    API --> CHAT
    DOCS --> DB
    DOCS --> VEC
    CHAT --> EMB
    EMB --> CHAT
    CHAT --> VEC
    VEC --> CHAT
    CHAT --> RER
    RER --> CHAT
    CHAT --> LLM
    LLM --> CHAT
    CHAT --> DB
    CHAT --> FE
```

### RAG query pipeline (simplified)

The `/chat/query` flow: embed → search → rerank → prompt LLM → validate citations → save & return.

```mermaid
%%{init: {'theme':'base', 'themeVariables': {'fontSize':'12px'}, 'sequence': {'useMaxWidth':true}}}%%
sequenceDiagram
    participant FE as Frontend
    participant CHAT as Chat API
    participant VEC as Vector
    participant LLM as LLM
    participant DB as DB
    FE->>CHAT: query
    CHAT->>CHAT: embed query
    CHAT->>VEC: search
    VEC-->>CHAT: chunks
    CHAT->>CHAT: rerank
    CHAT->>LLM: generate
    LLM-->>CHAT: answer
    CHAT->>CHAT: validate citations
    CHAT->>DB: save message
    CHAT-->>FE: answer + citations
```

### Why it is structured this way

- **Separation of concerns**: each service (`embedding_service`, `vector_store`, `rerank_service`, `llm_router`, `citation_service`) owns one stage of the pipeline, which keeps the RAG logic in `chat.py` readable and easy to change.
- **Pluggable providers**: the `llm_router` and `vector_store` abstractions allow you to swap between local and cloud LLMs or different vector backends without rewriting the business logic.
- **Auditing and reproducibility**: messages, retrieved chunks, and validated citations are stored in PostgreSQL so you can trace exactly how each answer was produced and debug issues later.
- **Performance and resilience**: background logging and short health‑check timeouts keep the main query path responsive while still exposing enough telemetry for monitoring.


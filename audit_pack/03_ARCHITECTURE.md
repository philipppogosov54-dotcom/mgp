# Architecture

## High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (HTML)                          │
│                     frontend/index.html                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ POST /api/v1/chat
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Server                              │
│                      app/main.py                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   API Layer                              │  │
│  │         app/api/v1/endpoints/chat.py                     │  │
│  │  - Input Guardrails (AI-SAFE)                            │  │
│  │  - Rate Limiting (slowapi)                               │  │
│  │  - Session Management (thread_id)                        │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│  ┌────────────────────────▼─────────────────────────────────┐  │
│  │                 LangGraph Agent                          │  │
│  │              app/agent/graph.py                          │  │
│  │                                                          │  │
│  │  START → input_analyzer → [conditional] → handler → END │  │
│  │                                                          │  │
│  │  Handlers (nodes.py):                                    │  │
│  │  - input_analyzer    (entity extraction, slot filling)   │  │
│  │  - tour_searcher     (Tourvisor API call)                │  │
│  │  - faq_handler       (FAQ responses)                     │  │
│  │  - booking_handler   (phone collection, escalation)      │  │
│  │  - quality_check_handler (stars/food questions)          │  │
│  │  - responder         (response formatting)               │  │
│  └───────────┬──────────────────────┬───────────────────────┘  │
│              │                      │                           │
│  ┌───────────▼──────────┐  ┌───────▼────────────────────────┐  │
│  │   Session Manager    │  │      Services Layer            │  │
│  │  app/core/session.py │  │  app/services/tourvisor.py     │  │
│  │  - MemorySaver       │  │  - search_tours()              │  │
│  │  - AsyncPostgresSaver│  │  - get_hot_tours()             │  │
│  │  - Window Buffer (20)│  │  - get_hotel_content()         │  │
│  └───────────┬──────────┘  │  app/services/analytics.py     │  │
│              │             │  - save_turn()                  │  │
│              │             │  - get_global_stats()           │  │
│              │             └────────────────┬────────────────┘  │
│              │                              │                   │
└──────────────┼──────────────────────────────┼───────────────────┘
               │                              │
    ┌──────────▼──────────┐       ┌──────────▼──────────┐
    │     PostgreSQL      │       │   Tourvisor API     │
    │  (optional)         │       │  tourvisor.ru/xml   │
    │  - checkpoints      │       │  - search.php       │
    │  - dialog_turns     │       │  - result.php       │
    │  - sessions         │       │  - hottours.php     │
    └─────────────────────┘       │  - list.php         │
                                  └─────────────────────┘
```

## Modules

### 1. Agent (app/agent/)

| File | Responsibility |
|------|----------------|
| `graph.py` | StateGraph definition, `process_message()` |
| `nodes.py` | All node handlers (5849 lines) |
| `state.py` | AgentState TypedDict, cascade logic |
| `prompts.py` | FAQ_RESPONSES, templates |
| `llm.py` | YandexGPT wrapper |

### 2. Core (app/core/)

| File | Responsibility |
|------|----------------|
| `config.py` | Pydantic Settings from env |
| `session.py` | SessionManager, Checkpointer |
| `guardrails.py` | Input/Output sanitization |
| `database.py` | PostgreSQL connection |
| `tourvisor_constants.py` | Auto-synced dictionaries |

### 3. Services (app/services/)

| File | Responsibility |
|------|----------------|
| `tourvisor.py` | Tourvisor API client (2580 lines) |
| `analytics.py` | Dialog/session analytics |
| `crm.py` | CRM stub (not implemented) |

### 4. Models (app/models/)

| File | Responsibility |
|------|----------------|
| `domain.py` | TourOffer, SearchRequest, FoodType |
| `schemas.py` | ChatRequest, ChatResponse |

## State Storage

| Component | Storage | File |
|-----------|---------|------|
| Dialog State | MemorySaver / AsyncPostgresSaver | `app/core/session.py` |
| Search Params | AgentState["search_params"] | in-memory per request |
| Tour Offers | AgentState["tour_offers"] | in-memory per request |
| Analytics | PostgreSQL dialog_turns table | `app/services/analytics.py` |

## Routing Logic

Located in `app/agent/nodes.py:5669` — `should_search()`:

```python
def should_search(state: AgentState) -> str:
    # Returns one of:
    # "search", "quality_check", "faq", "booking", 
    # "general_chat", "invalid_country", "ask_child_ages",
    # "clarify_city", "more_tours", "continue_search", "ask"
```

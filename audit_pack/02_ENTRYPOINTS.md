# Entry Points

## 1. Main Application

| File | Entry | Description |
|------|-------|-------------|
| `app/main.py` | `app = FastAPI(...)` | FastAPI application object |
| `app/main.py:370` | `uvicorn.run("app.main:app", ...)` | Uvicorn startup |

### Startup Flow
```
app/main.py:lifespan()
  → init_database()           # PostgreSQL init
  → session_manager.initialize_async()  # Async checkpointer
  → reinitialize_graph()      # LangGraph with new checkpointer
  → scheduler.start()         # APScheduler for sync jobs
  → initial_sync()            # Tourvisor dictionary sync
```

## 2. API Routes

### Chat (Primary)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| POST | `/api/v1/chat` | `chat()` | `app/api/v1/endpoints/chat.py:146` |
| DELETE | `/api/v1/chat/{id}` | `delete_session()` | `chat.py:240` |
| GET | `/api/v1/chat/{id}/history` | `get_history()` | `chat.py:273` |
| GET | `/api/v1/chat/sessions/stats` | `get_sessions_stats()` | `chat.py:326` |

### Analytics

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| GET | `/api/v1/analytics/global` | `get_global_analytics()` | `chat.py:357` |
| GET | `/api/v1/analytics/session/{id}` | `get_session_analytics()` | `chat.py:393` |
| GET | `/api/v1/analytics/dialogs/{id}` | `get_dialog_history_analytics()` | `chat.py:429` |
| GET | `/api/v1/analytics/sessions/recent` | `get_recent_sessions()` | `chat.py:465` |
| GET | `/api/v1/analytics/database` | `get_database_stats()` | `chat.py:502` |

### Health & Root

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| GET | `/` | `root()` | `app/main.py:318` |
| GET | `/health` | `health_check()` | `app/main.py:331` |

### Admin

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| GET | `/api/v1/admin/stats` | — | `app/api/v1/endpoints/admin.py` |

## 3. Static Files

| Path | Serves |
|------|--------|
| `/frontend/*` | `frontend/` directory (HTML UI) |

## 4. Background Jobs

| Job | Trigger | Handler | File:Line |
|-----|---------|---------|-----------|
| `tourvisor_sync` | Every 24h | `sync_tourvisor_job()` | `app/main.py:53` |
| `session_cleanup` | Every Nh | `cleanup_sessions_job()` | `app/main.py:69` |

## 5. Message Processing Flow

```
POST /api/v1/chat
  → chat() [chat.py:146]
    → apply_input_guardrails()    # AI-SAFE
    → get_or_create_thread_id()   # Session ID
    → process_message()           # app/agent/graph.py:181
      → get_agent_graph()         # LangGraph StateGraph
      → graph.ainvoke(state, config)
        → input_analyzer         # nodes.py:2754
        → [conditional edge]     # should_search()
          → tour_searcher        # nodes.py:3901
          → faq_handler          # nodes.py:3663
          → booking_handler      # nodes.py:5407
          → quality_check_handler # nodes.py:3833
          → responder            # nodes.py:4852
        → END
    → apply_output_guardrails()   # AI-SAFE
    → ChatResponse
```

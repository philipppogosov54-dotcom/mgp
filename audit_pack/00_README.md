# ИИ-Ассистент МГП — Audit Pack

**Дата генерации:** 2026-02-01  
**Git Hash:** 59ba945  
**Версия:** 1.0.0

## Как запустить

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env из примера
cp env.example .env
# Заполнить TOURVISOR_AUTH_LOGIN, TOURVISOR_AUTH_PASS, YANDEX_API_KEY, YANDEX_FOLDER_ID

# 3. Запустить сервер
uvicorn app.main:app --reload --port 8000

# 4. Открыть документацию
open http://localhost:8000/docs
```

## Стек

| Компонент | Технология |
|-----------|------------|
| Backend | FastAPI + Python 3.9+ |
| Диалоговый движок | LangGraph (StateGraph) |
| LLM | YandexGPT (опционально) |
| Туры API | Tourvisor XML/JSON API |
| Persistence | PostgreSQL / MemorySaver |
| Session | thread_id + Checkpointer |

## Основные папки

| Путь | Назначение |
|------|------------|
| `app/main.py` | Точка входа FastAPI |
| `app/agent/` | Логика ассистента (nodes, graph, state) |
| `app/services/tourvisor.py` | Интеграция Tourvisor API |
| `app/core/config.py` | Конфигурация (env vars) |
| `app/api/v1/endpoints/chat.py` | REST API для чата |
| `frontend/` | Простой HTML фронтенд |

## Интеграции

1. **Tourvisor API** — поиск туров, справочники (страны, города, отели)
2. **YandexGPT** — LLM для извлечения сущностей (опционально)
3. **PostgreSQL** — session persistence и аналитика (опционально)

## Что НЕ включено

- `.env` с секретами (используйте `env.example`)
- `node_modules`, `__pycache__`, `.venv`
- Большие test_results/*.json артефакты

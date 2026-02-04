"""
Эндпоинт чата с ИИ-ассистентом МГП.

Session Persistence:
- Использует thread_id (conversation_id) для идентификации сессии
- PostgresSaver/MemorySaver checkpointer сохраняет состояние между запросами
- Пользователь может продолжить диалог с любого устройства

Аналитика:
- История диалогов сохраняется в PostgreSQL
- Статистика сессий и конверсии

POST /chat — основной эндпоинт для диалога с пользователем.
"""
from __future__ import annotations

import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header, Query, Request

from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.agent.graph import process_message
from app.core.session import session_manager
from app.core.guardrails import apply_input_guardrails, apply_output_guardrails
from app.core.config import settings

# Rate Limiting
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

# Настройка логгера
logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Создаём limiter для этого роутера
if SLOWAPI_AVAILABLE and settings.RATE_LIMIT_ENABLED:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None


def validate_conversation_id(conversation_id: str) -> bool:
    """
    Валидация формата conversation_id.
    
    Допустимые форматы:
    - UUID v4 (стандартный)
    - user_<id> (для сессий по user_id)
    - legacy_<hex> (для legacy сессий)
    
    Returns:
        True если формат валиден
    """
    if not conversation_id:
        return False
    
    # Проверяем специальные префиксы
    if conversation_id.startswith("user_") or conversation_id.startswith("legacy_"):
        return True
    
    # Проверяем UUID формат
    try:
        uuid.UUID(conversation_id, version=4)
        return True
    except ValueError:
        return False


def get_or_create_thread_id(conversation_id: Optional[str], user_id: Optional[str] = None) -> str:
    """
    Получает или создаёт thread_id для сессии.
    
    Приоритет:
    1. conversation_id (если передан и валиден)
    2. user_id (если передан)
    3. Генерируем новый UUID
    
    Args:
        conversation_id: ID диалога (для продолжения)
        user_id: ID пользователя (из заголовка или параметра)
        
    Returns:
        thread_id для LangGraph
        
    Raises:
        HTTPException: если conversation_id имеет невалидный формат
    """
    if conversation_id:
        if not validate_conversation_id(conversation_id):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid conversation_id format. Expected UUID or user_<id> format."
            )
        return conversation_id
    
    if user_id:
        # Используем user_id как thread_id для persistence между сессиями
        return f"user_{user_id}"
    
    # Новая сессия
    return str(uuid.uuid4())


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {"description": "Успешный ответ"},
        400: {"model": ErrorResponse, "description": "Ошибка в запросе"},
        429: {"description": "Слишком много запросов"},
        500: {"model": ErrorResponse, "description": "Внутренняя ошибка сервера"}
    },
    summary="Отправить сообщение ассистенту",
    description="""
    Основной эндпоинт для общения с ИИ-ассистентом МГП.
    
    **Session Persistence:**
    - Передайте conversation_id для продолжения диалога
    - Или используйте заголовок X-User-ID для постоянной сессии
    - Бот помнит контекст между сообщениями
    
    **Возможности:**
    - Поиск туров по параметрам (страна, даты, количество туристов)
    - Горящие туры
    - FAQ по визам, оплате, отменам
    
    **Rate Limiting:**
    - {rate_limit} запросов в минуту
    
    **Пример запроса:**
    ```json
    {{
        "message": "Хочу в Турцию на 7 ночей вдвоём с 15 февраля",
        "conversation_id": null
    }}
    ```
    """.format(rate_limit=settings.RATE_LIMIT_CHAT_PER_MINUTE)
)
async def chat(
    http_request: Request,
    request: ChatRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
) -> ChatResponse:
    """
    Обработка сообщения пользователя с Session Persistence.
    
    Thread-based Persistence:
    1. Определяет thread_id (conversation_id или user_id)
    2. Запускает LangGraph агент с checkpointer
    3. Состояние автоматически сохраняется между запросами
    4. Возвращает ответ с карточками туров (если найдены)
    """
    # ==================== RATE LIMITING ====================
    if limiter and SLOWAPI_AVAILABLE:
        try:
            # Проверяем rate limit вручную
            rate_limit = f"{settings.RATE_LIMIT_CHAT_PER_MINUTE}/minute"
            await limiter._check_request_limit(http_request, rate_limit, "chat")
        except Exception as e:
            if "rate limit exceeded" in str(e).lower() or "ratelimitexceeded" in str(type(e).__name__).lower():
                raise HTTPException(
                    status_code=429,
                    detail=f"Слишком много запросов. Попробуйте через минуту. Лимит: {settings.RATE_LIMIT_CHAT_PER_MINUTE} запросов/мин"
                )
    
    try:
        # ==================== INPUT GUARDRAILS (AI-SAFE) ====================
        sanitized_message, guardrail_error = await apply_input_guardrails(request.message)
        
        if guardrail_error:
            logger.warning(f"🚫 Input blocked by guardrails: {guardrail_error}")
            return ChatResponse(
                reply=f"⚠️ {guardrail_error}. Пожалуйста, переформулируйте ваш запрос.",
                tour_cards=None,
                conversation_id=request.conversation_id or str(uuid.uuid4())
            )
        
        # Определяем thread_id для persistence
        thread_id = get_or_create_thread_id(request.conversation_id, x_user_id)
        
        logger.info(f"📩 Входящее сообщение: thread_id={thread_id}")
        
        # Проверяем метаданные сессии (для логирования)
        session_meta = session_manager.get_session_metadata(thread_id)
        if session_meta:
            logger.info(f"📂 Продолжение сессии: thread_id={thread_id}, сообщений: {session_meta.get('message_count', 0)}")
        else:
            logger.info(f"🆕 Новая сессия: thread_id={thread_id}")
        
        # Обрабатываем сообщение через агент
        # process_message сам восстановит состояние из checkpointer если нужно
        reply, new_state = await process_message(
            user_message=sanitized_message, 
            thread_id=thread_id,
            state=None  # Всегда None — process_message сам решит
        )
        
        # Получаем карточки туров (если есть)
        tour_cards = new_state.get("tour_offers", [])
        
        # Сериализуем карточки с computed полями
        serialized_cards = None
        if tour_cards:
            serialized_cards = [card.model_dump() for card in tour_cards]
        
        # ==================== OUTPUT GUARDRAILS (AI-SAFE) ====================
        safe_reply = apply_output_guardrails(reply)
        
        logger.info(f"✅ Ответ отправлен: thread_id={thread_id}")
        
        return ChatResponse(
            reply=safe_reply,
            tour_cards=serialized_cards if serialized_cards else None,
            conversation_id=thread_id  # Возвращаем thread_id для клиента
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        # ==================== OUTPUT GUARDRAILS: Error Handling ====================
        user_friendly_error = apply_output_guardrails("", error=e)
        return ChatResponse(
            reply=user_friendly_error,
            tour_cards=None,
            conversation_id=request.conversation_id or str(uuid.uuid4())
        )


@router.delete(
    "/chat/{conversation_id}",
    summary="Удалить сессию",
    description="Удаляет сессию диалога по ID (thread_id)"
)
async def delete_session(conversation_id: str) -> dict:
    """
    Удаление сессии диалога.
    
    При использовании PostgreSQL также помечает сессию как completed.
    """
    # Проверяем, есть ли метаданные сессии
    session_meta = session_manager.get_session_metadata(conversation_id)
    
    if session_meta:
        # Помечаем сессию как completed в аналитике
        if settings.DATABASE_URL and settings.ENABLE_ANALYTICS:
            try:
                from app.services.analytics import analytics_service
                analytics_service.mark_session_completed(conversation_id)
            except Exception as e:
                logger.warning(f"Failed to mark session as completed: {e}")
        
        logger.info(f"🗑️ Удаление сессии: thread_id={conversation_id}")
        return {
            "status": "deleted", 
            "conversation_id": conversation_id,
            "note": "Session marked as completed"
        }
    
    raise HTTPException(status_code=404, detail="Сессия не найдена")


@router.get(
    "/chat/{conversation_id}/history",
    summary="История диалога",
    description="Получить историю сообщений диалога и текущие параметры поиска"
)
async def get_history(conversation_id: str) -> dict:
    """
    Получение истории диалога.
    
    Возвращает:
    - Историю сообщений (если PostgreSQL подключен)
    - Текущие параметры поиска (страна, даты, состав)
    - Метаданные сессии
    """
    # Сначала проверяем метаданные в памяти
    session_meta = session_manager.get_session_metadata(conversation_id)
    
    # Затем проверяем БД
    db_dialogs = None
    db_stats = None
    
    if settings.DATABASE_URL and settings.ENABLE_ANALYTICS:
        try:
            from app.services.analytics import analytics_service
            db_dialogs = analytics_service.get_dialog_history(conversation_id)
            db_stats = analytics_service.get_session_stats(conversation_id)
        except Exception as e:
            logger.warning(f"Failed to get DB history: {e}")
    
    if not session_meta and not db_dialogs:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    result = {
        "conversation_id": conversation_id,
    }
    
    if session_meta:
        result["session_metadata"] = {
            "created_at": session_meta.get("created_at").isoformat() if session_meta.get("created_at") else None,
            "last_access": session_meta.get("last_access").isoformat() if session_meta.get("last_access") else None,
            "message_count": session_meta.get("message_count", 0)
        }
    
    if db_stats:
        result["analytics"] = db_stats
    
    if db_dialogs:
        result["dialogs"] = db_dialogs
        result["total_turns"] = len(db_dialogs)
    
    return result


@router.get(
    "/chat/sessions/stats",
    summary="Статистика сессий",
    description="Получить статистику активных сессий"
)
async def get_sessions_stats() -> dict:
    """
    Статистика сессий.
    
    Возвращает:
    - Количество активных сессий
    - Настройки (Window Buffer, TTL)
    """
    from app.core.session import MAX_MESSAGES_HISTORY, SESSION_TTL_SECONDS
    
    checkpointer_type = "PostgresSaver" if settings.DATABASE_URL else "MemorySaver (in-memory)"
    
    return {
        "active_sessions": session_manager.get_active_sessions_count(),
        "config": {
            "max_messages_history": MAX_MESSAGES_HISTORY,
            "session_ttl_seconds": SESSION_TTL_SECONDS
        },
        "checkpointer_type": checkpointer_type,
        "database_connected": bool(settings.DATABASE_URL),
        "analytics_enabled": settings.ENABLE_ANALYTICS
    }


# ==================== ANALYTICS ENDPOINTS ====================

@router.get(
    "/analytics/global",
    summary="Глобальная статистика",
    description="Получить глобальную статистику по всем сессиям и диалогам"
)
async def get_global_analytics() -> dict:
    """
    Глобальная статистика.
    
    Возвращает:
    - Общее количество сессий
    - Статистику поиска
    - Конверсию в бронирование
    - Статистику API вызовов
    """
    if not settings.DATABASE_URL:
        raise HTTPException(
            status_code=503, 
            detail="Analytics not available: DATABASE_URL not configured"
        )
    
    if not settings.ENABLE_ANALYTICS:
        raise HTTPException(
            status_code=503, 
            detail="Analytics disabled: ENABLE_ANALYTICS=false"
        )
    
    try:
        from app.services.analytics import analytics_service
        stats = analytics_service.get_global_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get global analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/session/{conversation_id}",
    summary="Аналитика сессии",
    description="Получить детальную аналитику по конкретной сессии"
)
async def get_session_analytics(conversation_id: str) -> dict:
    """
    Аналитика конкретной сессии.
    
    Возвращает:
    - Количество сообщений
    - Статистику поиска
    - Собранные параметры
    - Статус сессии
    """
    if not settings.DATABASE_URL or not settings.ENABLE_ANALYTICS:
        raise HTTPException(
            status_code=503, 
            detail="Analytics not available"
        )
    
    try:
        from app.services.analytics import analytics_service
        stats = analytics_service.get_session_stats(conversation_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/dialogs/{conversation_id}",
    summary="История диалогов",
    description="Получить полную историю диалога из БД"
)
async def get_dialog_history_analytics(conversation_id: str) -> dict:
    """
    Полная история диалога.
    
    Возвращает все ходы диалога в хронологическом порядке.
    """
    if not settings.DATABASE_URL or not settings.ENABLE_ANALYTICS:
        raise HTTPException(
            status_code=503, 
            detail="Analytics not available"
        )
    
    try:
        from app.services.analytics import analytics_service
        dialogs = analytics_service.get_dialog_history(conversation_id)
        
        if not dialogs:
            raise HTTPException(status_code=404, detail="No dialogs found")
        
        return {
            "conversation_id": conversation_id,
            "total_turns": len(dialogs),
            "dialogs": dialogs
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dialog history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/sessions/recent",
    summary="Недавние сессии",
    description="Получить список последних сессий"
)
async def get_recent_sessions(
    limit: int = Query(default=20, ge=1, le=100, description="Количество сессий"),
    status: Optional[str] = Query(default=None, description="Фильтр по статусу (active/completed/abandoned)")
) -> dict:
    """
    Список последних сессий.
    
    Возвращает:
    - Список сессий с базовой информацией
    - Отсортированы по последней активности
    """
    if not settings.DATABASE_URL or not settings.ENABLE_ANALYTICS:
        raise HTTPException(
            status_code=503, 
            detail="Analytics not available"
        )
    
    try:
        from app.services.analytics import analytics_service
        sessions = analytics_service.get_recent_sessions(limit=limit, status=status)
        
        return {
            "total": len(sessions),
            "limit": limit,
            "status_filter": status,
            "sessions": sessions
        }
    except Exception as e:
        logger.error(f"Failed to get recent sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/database",
    summary="Статистика БД",
    description="Получить статистику базы данных"
)
async def get_database_stats() -> dict:
    """
    Статистика базы данных.
    
    Возвращает:
    - Количество записей в таблицах
    - Размер БД
    """
    if not settings.DATABASE_URL:
        raise HTTPException(
            status_code=503, 
            detail="Database not configured"
        )
    
    try:
        from app.core.database import get_database_stats
        stats = get_database_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

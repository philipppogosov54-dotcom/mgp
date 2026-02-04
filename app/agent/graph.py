"""
LangGraph граф диалога для ИИ-ассистента МГП.

Session Persistence:
    - MemorySaver для thread-based persistence
    - Каждый пользователь имеет уникальный thread_id
    - Состояние сохраняется между HTTP-запросами

Архитектура воронки:
    START -> input_analyzer -> [условие] -> 
                                   |
                                   +-- (base) ask -----------> responder -----> END
                                   +-- (details) quality_check --------------> END
                                   +-- (search) tour_searcher -> responder --> END
                                   +-- booking_handler ----------------------> END
                                   +-- faq_handler --------------------------> END
                                   +-- general_chat_handler -----------------> END
                                   
Воронка сбора данных:
    1. БАЗА: страна, даты, состав
    2. ДЕТАЛИ: звёзды, питание, бюджет (для массовых направлений)
    3. ПОИСК: все параметры собраны
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState, create_initial_state, Message
from app.agent.nodes import (
    input_analyzer,
    tour_searcher,
    responder,
    faq_handler,
    booking_handler,
    general_chat_handler,
    quality_check_handler,
    invalid_country_handler,
    child_ages_handler,  # Критическая проверка: дети без возраста
    clarify_city_handler,  # ЭТАП 1: Уточнение города двойного назначения
    more_tours_handler,  # GAP Analysis: пагинация
    continue_search_handler,  # GAP Analysis: углублённый поиск
    should_search,
    clean_response_text  # GREETING CLEANER
)
from app.core.session import session_manager, apply_window_buffer, MAX_MESSAGES_HISTORY
from app.core.debug_logger import debug_logger
from app.core.config import settings
from app.services.tourvisor import set_trace_context
from app.services.analytics import analytics_service

# Настройка логгера
logger = logging.getLogger(__name__)


def create_agent_graph() -> StateGraph:
    """
    Создание графа диалога для ИИ-ассистента МГП.
    
    Воронка сбора данных:
    1. input_analyzer — анализ ввода и извлечение сущностей
    2. Условный переход (воронка):
       - БАЗА не собрана -> responder (спрашиваем страну/даты/состав)
       - ДЕТАЛИ нужны -> quality_check_handler (спрашиваем звёзды/питание)
       - ВСЕ параметры -> tour_searcher (ищем туры)
       - FAQ вопрос -> faq_handler
       - Бронирование -> booking_handler
       - Общий вопрос -> general_chat_handler
    3. tour_searcher -> responder
    4. Все остальные -> END
    
    Returns:
        Скомпилированный граф LangGraph
    """
    # Создаём граф с типизированным состоянием
    workflow = StateGraph(AgentState)
    
    # Добавляем узлы
    workflow.add_node("input_analyzer", input_analyzer)
    workflow.add_node("tour_searcher", tour_searcher)
    workflow.add_node("faq_handler", faq_handler)
    workflow.add_node("booking_handler", booking_handler)
    workflow.add_node("general_chat_handler", general_chat_handler)
    workflow.add_node("quality_check_handler", quality_check_handler)
    workflow.add_node("invalid_country_handler", invalid_country_handler)
    workflow.add_node("child_ages_handler", child_ages_handler)  # КРИТИЧНО: дети без возраста
    workflow.add_node("clarify_city_handler", clarify_city_handler)  # ЭТАП 1: Уточнение города
    workflow.add_node("more_tours_handler", more_tours_handler)  # GAP Analysis: пагинация
    workflow.add_node("continue_search_handler", continue_search_handler)  # GAP Analysis: углублённый поиск
    workflow.add_node("responder", responder)
    
    # Устанавливаем точку входа
    workflow.set_entry_point("input_analyzer")
    
    # Условное ребро после анализа ввода (воронка)
    workflow.add_conditional_edges(
        "input_analyzer",
        should_search,
        {
            "search": "tour_searcher",                     # Все параметры есть — ищем туры
            "quality_check": "quality_check_handler",      # Спросить о качестве
            "faq": "faq_handler",                          # FAQ вопрос — отвечаем из базы знаний
            "booking": "booking_handler",                  # Бронирование — обрабатываем заявку (включая группы >6)
            "general_chat": "general_chat_handler",        # Общий вопрос — отвечаем + мягко собираем
            "invalid_country": "invalid_country_handler",  # Невалидная страна
            "ask_child_ages": "child_ages_handler",        # КРИТИЧНО: дети без возраста
            "clarify_city": "clarify_city_handler",        # ЭТАП 1: Уточнение города двойного назначения
            "more_tours": "more_tours_handler",            # GAP Analysis: пагинация
            "continue_search": "continue_search_handler",  # GAP Analysis: углублённый поиск
            "ask": "responder"                             # Нужны базовые уточнения — спрашиваем
        }
    )
    
    # После поиска всегда идём в responder
    workflow.add_edge("tour_searcher", "responder")
    
    # После FAQ — завершаем
    workflow.add_edge("faq_handler", END)
    
    # После бронирования — завершаем
    workflow.add_edge("booking_handler", END)
    
    # После general chat — завершаем
    workflow.add_edge("general_chat_handler", END)
    
    # После quality check — завершаем (ждём ответа пользователя)
    workflow.add_edge("quality_check_handler", END)
    
    # После invalid_country — завершаем (предлагаем альтернативы)
    workflow.add_edge("invalid_country_handler", END)
    
    # После child_ages_handler — завершаем (ждём возраст детей)
    workflow.add_edge("child_ages_handler", END)
    
    # После clarify_city_handler — завершаем (ждём уточнение города)
    workflow.add_edge("clarify_city_handler", END)
    
    # После more_tours_handler — завершаем (пагинация)
    workflow.add_edge("more_tours_handler", END)
    
    # После continue_search_handler — завершаем (углублённый поиск)
    workflow.add_edge("continue_search_handler", END)
    
    # После ответа — завершаем
    workflow.add_edge("responder", END)
    
    # Компилируем граф с checkpointer для persistence
    # MemorySaver/AsyncPostgresSaver сохраняет состояние между вызовами по thread_id
    return workflow.compile(checkpointer=session_manager.get_checkpointer())


# Глобальный экземпляр графа с persistence
# При использовании AsyncPostgresSaver граф будет пересоздан после async init
_agent_graph = None


def get_agent_graph():
    """Получить или создать граф агента."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
        logger.info("🔗 LangGraph агент инициализирован")
    return _agent_graph


def reinitialize_graph():
    """Пересоздать граф (вызывается после async инициализации PostgresSaver)."""
    global _agent_graph
    _agent_graph = create_agent_graph()
    logger.info("🔗 LangGraph агент переинициализирован с новым checkpointer")


# Создаём граф при импорте (для обратной совместимости)
agent_graph = get_agent_graph()


async def process_message(
    user_message: str,
    thread_id: str,
    state: Optional[AgentState] = None
) -> tuple[str, AgentState]:
    """
    Обработка сообщения пользователя через граф агента с persistence.
    
    Подход: Явное восстановление состояния из checkpointer.
    
    Args:
        user_message: Сообщение от пользователя
        thread_id: Уникальный идентификатор сессии/пользователя
        state: Начальное состояние (только для первого сообщения)
        
    Returns:
        Кортеж (ответ ассистента, обновлённое состояние)
    """
    # Получаем конфигурацию с thread_id
    config = session_manager.get_config(thread_id)
    
    logger.info(f"📨 Обработка сообщения для thread_id={thread_id}")
    
    # ==================== ВОССТАНОВЛЕНИЕ СОСТОЯНИЯ ====================
    # Если state не передан, восстанавливаем из checkpointer
    
    if state is None:
        # Пробуем восстановить состояние из checkpointer
        try:
            checkpointer = session_manager.get_checkpointer()
            # Используем асинхронный метод для AsyncPostgresSaver
            if hasattr(checkpointer, 'aget_tuple'):
                checkpoint_tuple = await checkpointer.aget_tuple(config)
            else:
                checkpoint_tuple = checkpointer.get_tuple(config)
            
            if checkpoint_tuple and checkpoint_tuple.checkpoint:
                # Восстанавливаем состояние из channel_values
                channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                
                if channel_values and "messages" in channel_values:
                    logger.info(f"🔄 Восстановлено состояние для thread_id={thread_id}")
                    state = create_initial_state()
                    
                    # Копируем все сохранённые значения
                    for key, value in channel_values.items():
                        if key in state and value is not None:
                            state[key] = value
                else:
                    logger.info(f"📭 Пустой checkpoint для thread_id={thread_id}")
                    state = create_initial_state()
            else:
                logger.info(f"📭 Checkpoint не найден для thread_id={thread_id}")
                state = create_initial_state()
        except Exception as e:
            logger.warning(f"⚠️ Ошибка восстановления: {e}")
            state = create_initial_state()
    else:
        logger.info(f"🆕 Новая сессия: thread_id={thread_id}")
    
    # Гарантируем что messages это список
    if state.get("messages") is None:
        state["messages"] = []
    
    # Добавляем сообщение пользователя
    state["messages"].append(Message(role="user", content=user_message))
    
    # ==================== WINDOW BUFFER ====================
    state["messages"] = apply_window_buffer(
        state["messages"], 
        max_messages=MAX_MESSAGES_HISTORY
    )
    
    # Сбрасываем response перед запуском графа
    state["response"] = ""
    state["error"] = None
    
    # ==================== TRACE CONTEXT ====================
    # Устанавливаем контекст для трассировки API вызовов
    messages = state.get("messages", [])
    turn_id = len([m for m in messages if m.get("role") == "user"])
    set_trace_context(thread_id, turn_id)
    
    # ==================== ЗАМЕР ВРЕМЕНИ ====================
    start_time = time.time()
    
    # Запускаем граф (используем актуальный экземпляр)
    graph = get_agent_graph()
    result = await graph.ainvoke(state, config=config)
    
    # Вычисляем время ответа
    response_time_ms = (time.time() - start_time) * 1000
    
    # Получаем ответ
    assistant_response = result.get("response", "")
    
    # ==================== GREETING CLEANER ====================
    # Определяем: это первое сообщение в сессии?
    is_first_message = len(result.get("messages", [])) <= 1
    
    # Очищаем ответ от приветствий (если не первое сообщение)
    assistant_response = clean_response_text(assistant_response, is_first_message=is_first_message)
    result["response"] = assistant_response  # Обновляем и в result
    
    # Добавляем ответ ассистента в историю
    if assistant_response:
        if "messages" not in result:
            result["messages"] = []
        result["messages"].append(Message(role="assistant", content=assistant_response))
    
    # Обновляем метаданные сессии
    session_manager.increment_message_count(thread_id)
    
    logger.info(f"✅ Ответ сформирован для thread_id={thread_id}")
    
    # ==================== DEBUG LOGGING ====================
    # Логируем turn если DEBUG_LOGS=1
    if debug_logger.enabled:
        try:
            # Вычисляем turn_id (количество пар сообщений)
            messages = result.get("messages", [])
            turn_id = len([m for m in messages if m.get("role") == "user"])
            
            # Извлекаем данные для логирования
            search_params = result.get("search_params", {})
            cascade_stage = result.get("cascade_stage", 1)
            search_mode = result.get("search_mode", "package")
            missing_info = result.get("missing_info", [])
            intent = result.get("intent")
            last_question = result.get("last_question")
            
            debug_logger.log_turn(
                conversation_id=thread_id,
                turn_id=turn_id,
                user_text=user_message,
                assistant_text=assistant_response,
                search_mode=search_mode,
                cascade_stage=cascade_stage,
                search_params=search_params,
                missing_params=missing_info,
                detected_intent=intent,
                last_question_type=last_question,
                extra={
                    "is_first_message": is_first_message,
                    "tour_offers_count": len(result.get("tour_offers", []))
                }
            )
        except Exception as e:
            logger.warning(f"[DEBUG_LOGGER] Ошибка логирования turn: {e}")
    
    # ==================== ANALYTICS (PostgreSQL) ====================
    # Сохраняем диалог в БД для аналитики (асинхронно, не блокируем ответ)
    if settings.ENABLE_ANALYTICS and settings.DATABASE_URL:
        try:
            # Извлекаем данные для сохранения
            search_params = result.get("search_params", {})
            tour_offers_list = result.get("tour_offers", [])
            missing_info = result.get("missing_info", [])
            intent = result.get("intent")
            search_mode = result.get("search_mode", "package")
            cascade_stage = result.get("cascade_stage", 1)
            
            # Сериализуем tour_offers
            tour_offers_json = None
            if tour_offers_list:
                tour_offers_json = [offer.model_dump() for offer in tour_offers_list]
            
            # Сохраняем асинхронно (не блокируем ответ пользователю)
            asyncio.create_task(
                analytics_service.save_turn(
                    conversation_id=thread_id,
                    turn_id=turn_id,
                    user_text=user_message,
                    assistant_text=assistant_response,
                    search_params=search_params,
                    tour_offers=tour_offers_json,
                    missing_params=missing_info,
                    intent=intent,
                    search_mode=search_mode,
                    cascade_stage=cascade_stage,
                    response_time_ms=response_time_ms
                )
            )
        except Exception as e:
            logger.warning(f"[ANALYTICS] Ошибка сохранения в БД: {e}")
    
    return assistant_response, result


async def process_message_legacy(
    user_message: str,
    state: Optional[AgentState] = None
) -> tuple[str, AgentState]:
    """
    Legacy-метод для обратной совместимости (без persistence).
    
    DEPRECATED: Используйте process_message с thread_id.
    """
    # Генерируем временный thread_id
    import uuid
    temp_thread_id = f"legacy_{uuid.uuid4().hex[:8]}"
    return await process_message(user_message, temp_thread_id, state)


async def chat(user_message: str, session_state: Optional[dict] = None) -> dict:
    """
    Упрощённый интерфейс для чата.
    
    Args:
        user_message: Сообщение пользователя
        session_state: Состояние сессии (для продолжения диалога)
        
    Returns:
        Словарь с ответом и состоянием
    """
    # Восстанавливаем состояние из сессии
    state = None
    if session_state:
        state = AgentState(
            messages=session_state.get("messages", []),
            search_params=session_state.get("search_params", {}),
            missing_info=session_state.get("missing_info", []),
            tour_offers=[],
            response="",
            intent=session_state.get("intent"),
            error=None,
            customer_name=session_state.get("customer_name"),
            customer_phone=session_state.get("customer_phone"),
            awaiting_phone=session_state.get("awaiting_phone", False),
            selected_tour_id=session_state.get("selected_tour_id"),
            cascade_stage=session_state.get("cascade_stage", 1),
            quality_check_asked=session_state.get("quality_check_asked", False),
            is_first_message=False,
            greeted=session_state.get("greeted", False),
            # Новые поля
            is_group_request=session_state.get("is_group_request", False),
            group_size=session_state.get("group_size", 0),
            group_warning=session_state.get("group_warning", False),  # P3 FIX
            invalid_country=session_state.get("invalid_country"),
            # Гибкий поиск и согласие
            flex_search=session_state.get("flex_search", False),
            flex_days=session_state.get("flex_days", 2),  # По умолчанию ±2 дня
            awaiting_agreement=session_state.get("awaiting_agreement", False),
            pending_action=session_state.get("pending_action"),
            search_attempts=session_state.get("search_attempts", 0),
            offered_alt_departure=session_state.get("offered_alt_departure", False),
            missing_child_ages=session_state.get("missing_child_ages", 0),
            # P5 FIX: проверка питания для отеля
            alt_food_checked=session_state.get("alt_food_checked", False),
            available_food_types=session_state.get("available_food_types"),
            available_food_for_hotel=session_state.get("available_food_for_hotel")
        )
    
    # Обрабатываем сообщение
    response, new_state = await process_message(user_message, state)
    
    # Формируем результат
    return {
        "response": response,
        "tour_offers": [offer.model_dump() for offer in new_state.get("tour_offers", [])],
        "session_state": {
            "messages": new_state["messages"],
            "search_params": new_state["search_params"],
            "missing_info": new_state["missing_info"],
            "intent": new_state.get("intent"),
            "customer_name": new_state.get("customer_name"),
            "customer_phone": new_state.get("customer_phone"),
            "awaiting_phone": new_state.get("awaiting_phone", False),
            "selected_tour_id": new_state.get("selected_tour_id"),
            "cascade_stage": new_state.get("cascade_stage", 1),
            "quality_check_asked": new_state.get("quality_check_asked", False),
            "greeted": new_state.get("greeted", False),
            # Новые поля
            "is_group_request": new_state.get("is_group_request", False),
            "group_size": new_state.get("group_size", 0),
            "group_warning": new_state.get("group_warning", False),  # P3 FIX
            "invalid_country": new_state.get("invalid_country"),
            # Гибкий поиск и согласие
            "flex_search": new_state.get("flex_search", False),
            "flex_days": new_state.get("flex_days", 2),
            "awaiting_agreement": new_state.get("awaiting_agreement", False),
            "pending_action": new_state.get("pending_action"),
            "search_attempts": new_state.get("search_attempts", 0),
            "offered_alt_departure": new_state.get("offered_alt_departure", False),
            "missing_child_ages": new_state.get("missing_child_ages", 0),
            # P5 FIX: проверка питания для отеля
            "alt_food_checked": new_state.get("alt_food_checked", False),
            "available_food_types": new_state.get("available_food_types"),
            "available_food_for_hotel": new_state.get("available_food_for_hotel"),
            # FIX 2.3: Причина отсутствия туров для альтернатив
            "search_reason": new_state.get("search_reason"),
            "search_suggestion": new_state.get("search_suggestion")
        }
    }

"""
Runner для State Machine агента МГП.

Интегрирует:
- SlotExtractor — извлечение параметров
- StateMachine — граф состояний
- SessionManager — persistence

Основной entry point для обработки сообщений.

DEBUG FIX: State Persistence между вызовами API.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.agent.state_machine import (
    AgentStateMachine,
    TourSlots,
    DialogPhase,
    create_initial_state_machine,
    state_machine_graph,
    Message,
)
from app.agent.slot_extractor import slot_extractor
from app.core.session import session_manager, apply_window_buffer, MAX_MESSAGES_HISTORY

# Настройка логгера
logger = logging.getLogger(__name__)

# ==================== IN-MEMORY STATE STORAGE ====================
# Храним состояния сессий в памяти (дополнительно к checkpointer)
# Это решает проблему потери контекста между HTTP-запросами

_session_states: dict[str, AgentStateMachine] = {}


async def process_user_message(
    user_message: str,
    thread_id: str,
    state: Optional[AgentStateMachine] = None
) -> tuple[str, AgentStateMachine]:
    """
    Обработка сообщения пользователя через State Machine.
    
    КРИТИЧНО: State Persistence между HTTP-запросами!
    
    Flow:
    1. Восстанавливаем состояние из хранилища (если есть)
    2. Добавляем сообщение пользователя
    3. Извлекаем слоты
    4. Запускаем граф
    5. СОХРАНЯЕМ состояние
    6. Возвращаем ответ
    
    Args:
        user_message: Сообщение от пользователя
        thread_id: Уникальный ID сессии
        state: Текущее состояние (опционально, для override)
        
    Returns:
        Кортеж (ответ, новое состояние)
    """
    global _session_states
    
    try:
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG: process_user_message()")
        print(f"   thread_id: {thread_id}")
        print(f"   message: {user_message}")
        print(f"   state provided: {state is not None}")
        print(f"   known sessions: {list(_session_states.keys())}")
        
        # ==================== ШАГ 1: ВОССТАНОВЛЕНИЕ СОСТОЯНИЯ ====================
        # КРИТИЧНО: Сначала проверяем in-memory storage!
        if state is None:
            if thread_id in _session_states:
                state = _session_states[thread_id]
                print(f"   ✅ RESTORED from memory: phase={state['phase']}, greeted={state['greeted']}")
                print(f"   ✅ Slots: {state['slots']}")
            else:
                state = create_initial_state_machine()
                print(f"   🆕 NEW session created")
        
        # Debug: текущее состояние
        current_slots = TourSlots.from_dict(state["slots"])
        print(f"\n📊 DEBUG STATE BEFORE:")
        print(f"   phase: {state['phase']}")
        print(f"   greeted: {state['greeted']}")
        print(f"   messages: {len(state['messages'])}")
        print(f"   last_question_type: {state.get('last_question_type')}")
        print(f"   slots.country_to: {current_slots.country_to}")
        print(f"   slots.city_from: {current_slots.city_from}")
        
        # ==================== ШАГ 2: ДОБАВЛЯЕМ СООБЩЕНИЕ ====================
        state["messages"].append(Message(role="user", content=user_message))
        
        # Window Buffer
        state["messages"] = apply_window_buffer(
            state["messages"],
            max_messages=MAX_MESSAGES_HISTORY
        )
        
        # ==================== ШАГ 3: ИЗВЛЕЧЕНИЕ СЛОТОВ ====================
        last_question = state.get("last_question_type")
        
        print(f"\n🔍 SLOT EXTRACTION:")
        print(f"   input: '{user_message}'")
        print(f"   last_question_type: {last_question}")
        
        # Извлекаем слоты из текста
        updated_slots = slot_extractor.extract_all(
            text=user_message,
            current_slots=current_slots,
            last_question_type=last_question
        )
        
        # Обновляем слоты в состоянии
        state["slots"] = updated_slots.to_dict()
        
        # Debug: слоты после извлечения
        missing = updated_slots.get_missing_required()
        filled = [s for s in ["country_to", "city_from", "date_start", "nights", "adults"] if s not in missing]
        print(f"   ✅ Filled slots: {filled}")
        print(f"   ❌ Missing slots: {missing}")
        print(f"   country_to: {updated_slots.country_to}")
        print(f"   city_from: {updated_slots.city_from}")
        
        # ==================== ШАГ 4: ОПРЕДЕЛЕНИЕ ФАЗЫ ====================
        # Если все слоты заполнены — переходим к валидации
        if updated_slots.is_complete() and state["phase"] == DialogPhase.COLLECTING.value:
            state["phase"] = DialogPhase.VALIDATING.value
            print(f"   🔄 Transition: COLLECTING → VALIDATING")
        
        # КРИТИЧНО: Если мы уже здоровались — НЕ идём в greeting!
        if state["greeted"] and state["phase"] == DialogPhase.GREETING.value:
            state["phase"] = DialogPhase.COLLECTING.value
            print(f"   🔄 Skip GREETING → COLLECTING (already greeted)")
        
        # ==================== ШАГ 5: ЗАПУСК ГРАФА ====================
        config = session_manager.get_config(thread_id)
        
        print(f"\n🚀 INVOKING GRAPH with phase={state['phase']}")
        
        result = await state_machine_graph.ainvoke(state, config=config)
        
        # ==================== ШАГ 6: ФОРМИРОВАНИЕ ОТВЕТА ====================
        response = result.get("response", "")
        
        if response:
            result["messages"].append(Message(role="assistant", content=response))
        
        # ==================== ШАГ 7: СОХРАНЕНИЕ СОСТОЯНИЯ ====================
        # КРИТИЧНО: Сохраняем в memory storage!
        _session_states[thread_id] = result
        
        # Debug: состояние после
        print(f"\n📊 DEBUG STATE AFTER:")
        print(f"   phase: {result['phase']}")
        print(f"   greeted: {result['greeted']}")
        print(f"   response: {response[:60]}...")
        print(f"   slots: {result['slots']}")
        print(f"   SAVED to memory storage")
        print(f"{'='*60}\n")
        
        # Обновляем метаданные сессии
        session_manager.increment_message_count(thread_id)
        
        return response, result
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Safety fallback
        if state is None:
            state = create_initial_state_machine()
        
        state["error"] = str(e)
        state["response"] = (
            "Произошла техническая ошибка. Пожалуйста, попробуйте ещё раз "
            "или обратитесь к менеджеру."
        )
        return state["response"], state


async def get_session_summary(thread_id: str, state: AgentStateMachine) -> dict:
    """
    Возвращает краткую сводку о сессии.
    
    Используется для отладки и мониторинга.
    """
    slots = TourSlots.from_dict(state["slots"])
    
    return {
        "thread_id": thread_id,
        "phase": state["phase"],
        "message_count": len(state["messages"]),
        "slots_filled": {
            "country_to": slots.country_to,
            "city_from": slots.city_from,
            "date_start": str(slots.date_start) if slots.date_start else None,
            "nights": slots.nights,
            "adults": slots.adults,
            "children_ages": slots.children_ages,
            "stars": slots.stars,
            "food_type": slots.food_type,
        },
        "missing_slots": slots.get_missing_required(),
        "is_complete": slots.is_complete(),
        "error": state.get("error"),
    }


# ==================== ТЕСТИРОВАНИЕ ====================

async def test_slot_filling():
    """Тест Slot Filling логики."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ SLOT FILLING")
    print("=" * 60)
    
    test_cases = [
        ("Хочу в Турцию", {"country_to": "Турция"}),
        ("Из Москвы", {"city_from": "Москва"}),
        ("15 февраля", {"date_start": True}),  # True = должна быть дата
        ("7 ночей", {"nights": 7}),
        ("2 взрослых и 1 ребёнок 5 лет", {"adults": 2, "children_ages": [5]}),
        ("5 звёзд всё включено", {"stars": 5, "food_type": "AI"}),
    ]
    
    for text, expected in test_cases:
        slots = TourSlots()
        result = slot_extractor.extract_all(text, slots)
        
        print(f"\n📝 '{text}'")
        for key, exp_value in expected.items():
            actual = getattr(result, key)
            if exp_value is True:
                passed = actual is not None
            else:
                passed = actual == exp_value
            
            status = "✅" if passed else "❌"
            print(f"   {status} {key}: expected={exp_value}, got={actual}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_slot_filling())

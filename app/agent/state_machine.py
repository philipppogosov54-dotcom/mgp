"""
State Machine для ИИ-ассистента МГП.

Паттерн: Slot Filling с явными состояниями.

Граф состояний:
    START 
      │
      ▼
    Greeting (первое сообщение)
      │
      ▼
    CollectParams ◄────────────────┐
      │                            │
      ├─ [missing_params] ─────────┤ (WAIT_USER_INPUT)
      │                            │
      ▼                            │
    ValidateParams                 │
      │                            │
      ├─ [invalid] ────────────────┘
      │
      ▼
    ConfirmSearch (подтверждение)
      │
      ├─ [rejected] ───────────────► CollectParams
      │
      ▼
    SearchTours
      │
      ├─ [empty] ──────────────────► Fallback
      │
      ▼
    PresentResults
      │
      ▼
    END

Безопасность:
- Все узлы обёрнуты в try-except
- Нет дефолтных значений — агент ВСЕГДА спрашивает
- Валидация перед поиском
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Literal, Any
from dataclasses import dataclass, field
from enum import Enum

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

# Настройка логгера
logger = logging.getLogger(__name__)


# ==================== СОСТОЯНИЯ ДИАЛОГА ====================

class DialogPhase(str, Enum):
    """Фазы диалога (конечный автомат)."""
    GREETING = "greeting"                    # Приветствие
    COLLECTING = "collecting"                # Сбор параметров
    VALIDATING = "validating"                # Валидация
    CONFIRMING = "confirming"                # Подтверждение перед поиском
    SEARCHING = "searching"                  # Поиск туров
    PRESENTING = "presenting"                # Показ результатов
    FALLBACK = "fallback"                    # Расширенный поиск
    FAQ = "faq"                              # Ответ на FAQ
    BOOKING = "booking"                      # Бронирование
    ESCALATION = "escalation"                # Эскалация на менеджера (группа > 6)
    ERROR = "error"                          # Ошибка


class SlotStatus(str, Enum):
    """Статус слота (параметра)."""
    EMPTY = "empty"              # Не заполнен
    FILLED = "filled"            # Заполнен
    INVALID = "invalid"          # Заполнен некорректно
    CONFIRMED = "confirmed"      # Подтверждён пользователем


# ==================== СЛОТЫ (ПАРАМЕТРЫ ПОИСКА) ====================

@dataclass
class TourSlots:
    """
    Слоты для поиска тура (Slot Filling Pattern).
    
    КРИТИЧНО: Все слоты Optional — нет дефолтов!
    Агент ОБЯЗАН спросить каждый незаполненный слот.
    """
    # Обязательные слоты
    country_to: Optional[str] = None          # Страна назначения
    city_from: Optional[str] = None           # Город вылета
    date_start: Optional[date] = None         # Дата начала
    nights: Optional[int] = None              # Количество ночей
    adults: Optional[int] = None              # Взрослые
    
    # Опциональные слоты
    children_ages: list[int] = field(default_factory=list)  # Возрасты детей
    stars: Optional[int] = None               # Звёздность
    food_type: Optional[str] = None           # Тип питания
    hotel_name: Optional[str] = None          # Конкретный отель
    max_price: Optional[int] = None           # Максимальный бюджет
    
    # Флаги
    skip_quality_check: bool = False          # Пропустить вопрос о качестве
    
    def get_missing_required(self) -> list[str]:
        """Возвращает список незаполненных обязательных слотов."""
        missing = []
        if self.country_to is None:
            missing.append("country_to")
        if self.city_from is None:
            missing.append("city_from")
        if self.date_start is None:
            missing.append("date_start")
        if self.nights is None:
            missing.append("nights")
        if self.adults is None:
            missing.append("adults")
        return missing
    
    def is_complete(self) -> bool:
        """Проверяет, все ли обязательные слоты заполнены."""
        return len(self.get_missing_required()) == 0
    
    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        return {
            "country_to": self.country_to,
            "city_from": self.city_from,
            "date_start": self.date_start.isoformat() if self.date_start else None,
            "nights": self.nights,
            "adults": self.adults,
            "children_ages": self.children_ages,
            "stars": self.stars,
            "food_type": self.food_type,
            "hotel_name": self.hotel_name,
            "max_price": self.max_price,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TourSlots":
        """Десериализация из словаря."""
        date_start = None
        if data.get("date_start"):
            if isinstance(data["date_start"], str):
                date_start = date.fromisoformat(data["date_start"])
            else:
                date_start = data["date_start"]
        
        return cls(
            country_to=data.get("country_to"),
            city_from=data.get("city_from"),
            date_start=date_start,
            nights=data.get("nights"),
            adults=data.get("adults"),
            children_ages=data.get("children_ages", []),
            stars=data.get("stars"),
            food_type=data.get("food_type"),
            hotel_name=data.get("hotel_name"),
            max_price=data.get("max_price"),
            skip_quality_check=data.get("skip_quality_check", False),
        )


# ==================== ВОПРОСЫ ДЛЯ СЛОТОВ ====================

SLOT_QUESTIONS = {
    "country_to": "В какую страну планируете поездку?",
    "city_from": "Из какого города планируете вылет?",
    "date_start": "Когда планируете отпуск? (укажите дату или месяц)",
    "nights": "На сколько ночей планируете поездку?",
    "adults": "Сколько взрослых полетит? (и есть ли дети — укажите их возраст)",
    "stars": "Какой уровень отеля предпочитаете — 5★, 4★ или рассмотрим варианты?",
    "food_type": "Какой тип питания: всё включено (AI), полупансион (HB) или только завтраки (BB)?",
}

SLOT_NAMES_RU = {
    "country_to": "страна",
    "city_from": "город вылета", 
    "date_start": "дата",
    "nights": "количество ночей",
    "adults": "состав группы",
    "stars": "звёздность",
    "food_type": "питание",
}


# ==================== СОСТОЯНИЕ АГЕНТА (TypedDict) ====================

from typing import TypedDict


class Message(TypedDict):
    """Сообщение в истории."""
    role: str  # "user" или "assistant"
    content: str


class AgentStateMachine(TypedDict):
    """
    Состояние агента для State Machine.
    
    Это TypedDict для LangGraph StateGraph.
    """
    # История диалога
    messages: list[Message]
    
    # Текущая фаза диалога
    phase: str  # DialogPhase value
    
    # Слоты (параметры поиска)
    slots: dict  # TourSlots.to_dict()
    
    # Текущий слот для заполнения
    current_slot: Optional[str]
    
    # Последний заданный вопрос (для контекста)
    last_question_type: Optional[str]
    
    # Результаты поиска
    tour_offers: list
    
    # Ответ для пользователя
    response: str
    
    # Флаги
    greeted: bool                    # Было ли приветствие
    awaiting_confirmation: bool      # Ждём подтверждения перед поиском
    search_confirmed: bool           # Поиск подтверждён
    fallback_attempted: bool         # Был ли fallback поиск
    
    # Ошибки
    error: Optional[str]
    
    # Intent
    intent: Optional[str]


def create_initial_state_machine() -> AgentStateMachine:
    """Создаёт начальное состояние State Machine."""
    return AgentStateMachine(
        messages=[],
        phase=DialogPhase.GREETING.value,
        slots=TourSlots().to_dict(),
        current_slot=None,
        last_question_type=None,
        tour_offers=[],
        response="",
        greeted=False,
        awaiting_confirmation=False,
        search_confirmed=False,
        fallback_attempted=False,
        error=None,
        intent=None,
    )


# ==================== УЗЛЫ ГРАФА ====================

async def greeting_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел приветствия.
    
    КРИТИЧНО: Выполняется ТОЛЬКО для первого сообщения!
    Если greeted=True — сразу переходим к collect.
    """
    try:
        print(f"\n🔍 DEBUG greeting_node:")
        print(f"   greeted: {state['greeted']}")
        print(f"   messages: {len(state['messages'])}")
        print(f"   phase: {state['phase']}")
        
        # КРИТИЧНО: Если уже здоровались — НЕ здороваемся снова!
        if state["greeted"]:
            print(f"   ⏭️ SKIP: already greeted")
            # Переходим к сбору параметров
            state["phase"] = DialogPhase.COLLECTING.value
            return state
        
        # Первое сообщение — приветствуем
        slots = TourSlots.from_dict(state["slots"])
        
        # Если пользователь сразу указал страну — не задаём вопрос о стране
        if slots.country_to:
            state["response"] = (
                f"Отлично, {slots.country_to}! Из какого города планируете вылет?"
            )
            state["current_slot"] = "city_from"
            state["last_question_type"] = "city_from"
        else:
            state["response"] = (
                "Здравствуйте! Я консультант турагентства МГП. "
                "Помогу подобрать тур. В какую страну планируете поездку?"
            )
            state["current_slot"] = "country_to"
            state["last_question_type"] = "country_to"
        
        state["greeted"] = True
        state["phase"] = DialogPhase.COLLECTING.value
        
        print(f"   ✅ Greeted, phase → COLLECTING")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в greeting_node: {e}")
        print(f"   ❌ ERROR: {e}")
        state["error"] = str(e)
        state["response"] = "Здравствуйте! Чем могу помочь?"
        state["greeted"] = True
        state["phase"] = DialogPhase.COLLECTING.value
        return state


async def collect_params_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел сбора параметров (Slot Filling).
    
    КРИТИЧНО: Не переходит к поиску, пока ВСЕ обязательные слоты не заполнены!
    """
    try:
        print(f"\n🔍 DEBUG collect_params_node:")
        
        slots = TourSlots.from_dict(state["slots"])
        
        print(f"   country_to: {slots.country_to}")
        print(f"   city_from: {slots.city_from}")
        print(f"   date_start: {slots.date_start}")
        print(f"   nights: {slots.nights}")
        print(f"   adults: {slots.adults}")
        
        # Получаем недостающие слоты
        missing = slots.get_missing_required()
        print(f"   missing: {missing}")
        
        if not missing:
            # Все обязательные слоты заполнены
            print(f"   ✅ All slots filled → VALIDATING")
            state["phase"] = DialogPhase.VALIDATING.value
            return state
        
        # Определяем следующий слот для заполнения (по приоритету)
        priority_order = ["country_to", "city_from", "date_start", "nights", "adults"]
        
        next_slot = None
        for slot in priority_order:
            if slot in missing:
                next_slot = slot
                break
        
        print(f"   next_slot to ask: {next_slot}")
        
        if next_slot:
            # Формируем контекст (что уже знаем)
            context_parts = []
            if slots.country_to:
                context_parts.append(slots.country_to)
            if slots.city_from:
                context_parts.append(f"из {slots.city_from}")
            if slots.date_start:
                context_parts.append(f"на {slots.date_start.strftime('%d.%m')}")
            if slots.nights:
                context_parts.append(f"{slots.nights} ночей")
            if slots.adults:
                pax = f"{slots.adults} взр"
                if slots.children_ages:
                    pax += f" + {len(slots.children_ages)} дет"
                context_parts.append(pax)
            
            context = ", ".join(context_parts) if context_parts else ""
            
            # Формируем вопрос
            question = SLOT_QUESTIONS.get(next_slot, "Уточните, пожалуйста?")
            
            if context:
                state["response"] = f"Принято: {context}. {question}"
            else:
                state["response"] = question
            
            state["current_slot"] = next_slot
            state["last_question_type"] = next_slot
            state["phase"] = DialogPhase.COLLECTING.value
            
            print(f"   response: {state['response'][:60]}...")
            print(f"   last_question_type set to: {next_slot}")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в collect_params_node: {e}")
        state["error"] = str(e)
        state["response"] = "Произошла ошибка. Давайте начнём сначала. В какую страну планируете?"
        return state


async def validate_params_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел валидации параметров.
    
    Проверяет:
    1. Корректность заполненных слотов
    2. Эскалация для групп > 6 человек (раздел 2.2 ТЗ)
    """
    try:
        print(f"\n🔍 DEBUG validate_params_node:")
        
        slots = TourSlots.from_dict(state["slots"])
        errors = []
        
        # ==================== ЭСКАЛАЦИЯ (раздел 2.2 ТЗ) ====================
        # Группы > 6 человек требуют менеджера
        total_pax = (slots.adults or 0) + len(slots.children_ages)
        print(f"   total_pax: {total_pax} (adults={slots.adults}, children={len(slots.children_ages)})")
        
        if total_pax > 6:
            print(f"   ⚠️ ESCALATION: группа > 6 человек")
            state["phase"] = DialogPhase.ESCALATION.value
            return state
        
        # ==================== ВАЛИДАЦИЯ ====================
        
        # Валидация даты
        if slots.date_start:
            if slots.date_start < date.today():
                errors.append("Дата вылета не может быть в прошлом")
            if slots.date_start > date.today() + timedelta(days=365):
                errors.append("Бронирование возможно максимум на год вперёд")
        
        # Валидация ночей
        if slots.nights:
            if slots.nights < 1 or slots.nights > 30:
                errors.append("Количество ночей должно быть от 1 до 30")
        
        # Валидация взрослых
        if slots.adults:
            if slots.adults < 1:
                errors.append("Минимум 1 взрослый")
        
        # Валидация детей
        for age in slots.children_ages:
            if age < 0 or age > 17:
                errors.append(f"Возраст ребёнка должен быть от 0 до 17 лет")
                break
        
        if errors:
            state["response"] = "Обнаружены ошибки:\n• " + "\n• ".join(errors)
            state["phase"] = DialogPhase.COLLECTING.value
            return state
        
        print(f"   ✅ Validation passed")
        
        # Валидация пройдена — переходим к подтверждению
        state["phase"] = DialogPhase.CONFIRMING.value
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в validate_params_node: {e}")
        state["error"] = str(e)
        state["phase"] = DialogPhase.COLLECTING.value
        return state


async def escalation_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел эскалации на менеджера (раздел 2.2 ТЗ).
    
    Вызывается когда:
    - Группа > 6 человек
    - Сложный запрос
    - Корпоративный выезд
    """
    try:
        print(f"\n🔍 DEBUG escalation_node:")
        
        slots = TourSlots.from_dict(state["slots"])
        total_pax = (slots.adults or 0) + len(slots.children_ages)
        
        # Формируем сообщение для пользователя
        state["response"] = (
            f"📞 **Требуется помощь менеджера**\n\n"
            f"Для групп от 7 человек (у вас {total_pax}) "
            f"мы подбираем специальные условия и групповые скидки.\n\n"
            f"Пожалуйста:\n"
            f"• Оставьте номер телефона для обратного звонка\n"
            f"• Или позвоните нам: **+7 (495) XXX-XX-XX**\n\n"
            f"Менеджер свяжется с вами в течение 15 минут в рабочее время."
        )
        
        # Ставим флаг ожидания телефона
        state["awaiting_confirmation"] = True
        
        print(f"   ✅ Escalation message sent")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в escalation_node: {e}")
        state["error"] = str(e)
        state["response"] = "Для вашего запроса требуется помощь менеджера. Позвоните нам."
        return state


async def confirm_search_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел подтверждения перед поиском.
    
    Человекочитаемое подтверждение параметров.
    """
    try:
        if state["search_confirmed"]:
            # Уже подтверждено — переходим к поиску
            state["phase"] = DialogPhase.SEARCHING.value
            return state
        
        slots = TourSlots.from_dict(state["slots"])
        
        # Формируем человекочитаемое описание
        date_str = slots.date_start.strftime("%d.%m.%Y") if slots.date_start else "?"
        
        pax_str = f"{slots.adults} взрослых"
        if slots.children_ages:
            ages_str = ", ".join(str(a) for a in slots.children_ages)
            pax_str += f" + дети ({ages_str} лет)"
        
        confirmation = (
            f"📋 **Параметры поиска:**\n"
            f"• Направление: {slots.country_to}\n"
            f"• Вылет из: {slots.city_from}\n"
            f"• Дата: {date_str}\n"
            f"• Длительность: {slots.nights} ночей\n"
            f"• Туристы: {pax_str}\n"
        )
        
        if slots.stars:
            confirmation += f"• Отель: {slots.stars}★\n"
        if slots.food_type:
            confirmation += f"• Питание: {slots.food_type}\n"
        if slots.hotel_name:
            confirmation += f"• Отель: {slots.hotel_name}\n"
        
        confirmation += "\n✅ Ищу туры по этим параметрам..."
        
        state["response"] = confirmation
        state["search_confirmed"] = True
        state["phase"] = DialogPhase.SEARCHING.value
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в confirm_search_node: {e}")
        state["error"] = str(e)
        return state


async def search_tours_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел поиска туров.
    
    Вызывает Tourvisor API с собранными параметрами.
    """
    try:
        from app.services.tourvisor import tourvisor_service
        from app.models.domain import SearchRequest, Destination
        
        slots = TourSlots.from_dict(state["slots"])
        
        logger.info(f"🔍 Поиск туров: {slots.to_dict()}")
        
        # Загружаем справочники
        await tourvisor_service.load_countries()
        await tourvisor_service.load_departures()
        
        # Создаём запрос
        destination = Destination(
            country=slots.country_to,
            region=None,
            resort=None,
            city=None
        )
        
        # Расчёт date_to
        date_to = None
        if slots.date_start and slots.nights:
            date_to = slots.date_start + timedelta(days=slots.nights + 2)  # +2 для гибкости
        
        search_request = SearchRequest(
            adults=slots.adults,
            children=slots.children_ages,
            destination=destination,
            hotel_name=slots.hotel_name,
            stars=slots.stars,
            date_from=slots.date_start,
            date_to=date_to,
            food_type=None,  # TODO: конвертация
            departure_city=slots.city_from,
            nights=slots.nights,
        )
        
        # Выполняем поиск
        result = await tourvisor_service.search_tours(search_request)
        
        if result.found and result.offers:
            state["tour_offers"] = result.offers
            state["phase"] = DialogPhase.PRESENTING.value
        else:
            # Пустой результат — fallback
            state["tour_offers"] = []
            state["phase"] = DialogPhase.FALLBACK.value
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в search_tours_node: {e}")
        state["error"] = str(e)
        state["response"] = (
            "К сожалению, произошла ошибка при поиске туров. "
            "Попробуйте изменить параметры или обратитесь к менеджеру."
        )
        state["phase"] = DialogPhase.ERROR.value
        return state


async def fallback_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел fallback поиска (раздел 2.2 ТЗ).
    
    При нулевом результате предлагает:
    - Соседние даты (±3-5 дней)
    - Смену города вылета
    - Другие варианты питания
    """
    try:
        print(f"\n🔍 DEBUG fallback_node:")
        
        slots = TourSlots.from_dict(state["slots"])
        
        if state["fallback_attempted"]:
            # Уже пробовали — предлагаем связаться с менеджером
            print(f"   ⚠️ Fallback already attempted")
            
            state["response"] = (
                f"😔 К сожалению, туров в {slots.country_to or 'выбранную страну'} "
                f"на указанные даты не найдено.\n\n"
                f"**Что можно сделать:**\n"
                f"• Сдвинуть даты на ±5-7 дней\n"
                f"• Попробовать вылет из другого города\n"
                f"• Рассмотреть соседние курорты\n\n"
                f"📞 Или свяжитесь с менеджером — он подберёт индивидуально."
            )
            state["phase"] = DialogPhase.PRESENTING.value
            return state
        
        # Первая попытка fallback
        print(f"   🔄 First fallback attempt")
        
        # Формируем альтернативы
        date_str = slots.date_start.strftime('%d.%m') if slots.date_start else "указанные даты"
        
        # Альтернативные города вылета
        alt_cities = {
            "Москва": "Санкт-Петербург",
            "Санкт-Петербург": "Москва",
            "Сочи (Адлер)": "Краснодар",
            "Екатеринбург": "Казань",
        }
        alt_city = alt_cities.get(slots.city_from, "Москва")
        
        state["response"] = (
            f"🔍 На {date_str} подходящих туров не нашлось.\n\n"
            f"**Могу предложить:**\n"
            f"1️⃣ Посмотреть соседние даты (±3 дня)\n"
            f"2️⃣ Попробовать вылет из {alt_city}\n"
            f"3️⃣ Убрать фильтр по звёздности/питанию\n\n"
            f"Что выберете?"
        )
        
        state["awaiting_confirmation"] = True
        state["fallback_attempted"] = True
        
        print(f"   ✅ Fallback options offered")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в fallback_node: {e}")
        print(f"   ❌ ERROR: {e}")
        state["error"] = str(e)
        state["response"] = "Произошла ошибка. Попробуйте изменить параметры поиска."
        return state


async def present_results_node(state: AgentStateMachine) -> AgentStateMachine:
    """
    Узел показа результатов (раздел 2.1 ТЗ).
    
    Выдача 3-5 карточек предложений (максимум 5).
    """
    try:
        print(f"\n🔍 DEBUG present_results_node:")
        
        offers = state["tour_offers"]
        
        if not offers:
            # Результатов нет (после fallback)
            print(f"   ⚠️ No offers")
            if not state.get("response"):
                state["response"] = "К сожалению, подходящих туров не найдено."
            return state
        
        slots = TourSlots.from_dict(state["slots"])
        
        # РАЗДЕЛ 2.1 ТЗ: Выдача 3-5 карточек (максимум 5)
        MAX_CARDS = 5
        MIN_CARDS = 3
        
        total_found = len(offers)
        cards_to_show = min(total_found, MAX_CARDS)
        
        # Ограничиваем результаты
        state["tour_offers"] = offers[:cards_to_show]
        
        print(f"   📊 Total found: {total_found}, showing: {cards_to_show}")
        
        # Формируем заголовок
        if total_found > MAX_CARDS:
            header = (
                f"🏝️ Найдено {total_found} вариантов в {slots.country_to}!\n"
                f"Показываю топ-{cards_to_show}. Нажмите «Ещё туры» для дополнительных.\n"
            )
        else:
            header = f"🏝️ Нашёл {cards_to_show} вариантов в {slots.country_to}:\n"
        
        # Добавляем информацию о параметрах поиска
        params_str = []
        if slots.city_from:
            params_str.append(f"из {slots.city_from}")
        if slots.date_start:
            params_str.append(f"с {slots.date_start.strftime('%d.%m')}")
        if slots.nights:
            params_str.append(f"{slots.nights} ночей")
        if slots.adults:
            pax = f"{slots.adults} взр"
            if slots.children_ages:
                pax += f" + {len(slots.children_ages)} дет"
            params_str.append(pax)
        
        if params_str:
            header += f"📋 {', '.join(params_str)}\n"
        
        state["response"] = header
        
        print(f"   ✅ Response: {header[:60]}...")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Ошибка в present_results_node: {e}")
        print(f"   ❌ ERROR: {e}")
        # СКРЫВАЕМ технические ошибки от пользователя
        state["error"] = str(e)
        state["response"] = (
            "Произошла ошибка при показе результатов. "
            "Я уточняю данные у системы, попробуйте ещё раз через минуту."
        )
        return state


# ==================== УСЛОВНЫЕ ПЕРЕХОДЫ ====================

def route_after_greeting(state: AgentStateMachine) -> str:
    """Маршрутизация после приветствия."""
    intent = state.get("intent")
    
    if intent == "faq_visa" or intent == "faq_payment":
        return "faq"
    
    return "collect"


def route_after_collect(state: AgentStateMachine) -> str:
    """Маршрутизация после сбора параметров."""
    slots = TourSlots.from_dict(state["slots"])
    
    if slots.is_complete():
        return "validate"
    
    return "wait"  # Ждём ввода пользователя


def route_after_validate(state: AgentStateMachine) -> str:
    """Маршрутизация после валидации."""
    # Проверяем эскалацию (группа > 6)
    if state["phase"] == DialogPhase.ESCALATION.value:
        return "escalation"
    
    if state.get("error"):
        return "collect"
    
    return "confirm"


def route_after_search(state: AgentStateMachine) -> str:
    """Маршрутизация после поиска."""
    if state["tour_offers"]:
        return "present"
    
    return "fallback"


# ==================== СОЗДАНИЕ ГРАФА ====================

def create_state_machine_graph() -> StateGraph:
    """
    Создаёт State Machine граф для агента МГП.
    
    Граф:
        greeting -> collect -> validate -> confirm -> search -> present
                      ↑          │                       │
                      └──────────┴───────────────────────┘ (fallback)
    """
    from app.core.session import session_manager
    
    workflow = StateGraph(AgentStateMachine)
    
    # Добавляем узлы
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("collect", collect_params_node)
    workflow.add_node("validate", validate_params_node)
    workflow.add_node("confirm", confirm_search_node)
    workflow.add_node("search", search_tours_node)
    workflow.add_node("fallback", fallback_node)
    workflow.add_node("present", present_results_node)
    workflow.add_node("escalation", escalation_node)  # Группы > 6 чел
    
    # Точка входа
    workflow.set_entry_point("greeting")
    
    # Переходы
    workflow.add_conditional_edges(
        "greeting",
        route_after_greeting,
        {
            "collect": "collect",
            "faq": END,  # FAQ обрабатывается отдельно
        }
    )
    
    workflow.add_conditional_edges(
        "collect",
        route_after_collect,
        {
            "validate": "validate",
            "wait": END,  # Ждём ввода пользователя
        }
    )
    
    workflow.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "confirm": "confirm",
            "collect": "collect",  # Вернуться при ошибке
            "escalation": "escalation",  # Группа > 6 человек
        }
    )
    
    # Эскалация — завершаем (ждём звонок менеджера)
    workflow.add_edge("escalation", END)
    
    workflow.add_edge("confirm", "search")
    
    workflow.add_conditional_edges(
        "search",
        route_after_search,
        {
            "present": "present",
            "fallback": "fallback",
        }
    )
    
    workflow.add_edge("fallback", END)
    workflow.add_edge("present", END)
    
    # Компилируем с checkpointer
    return workflow.compile(checkpointer=session_manager.get_checkpointer())


# ==================== ЭКСПОРТ ====================

state_machine_graph = create_state_machine_graph()

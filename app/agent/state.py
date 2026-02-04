"""
Состояние агента LangGraph для ИИ-ассистента МГП.

Каскад вопросов (СТРОГИЙ ПОРЯДОК):
1. Куда? (страна)
2. Откуда? (город вылета) - ОБЯЗАТЕЛЬНО!
3. Когда? (даты)
4. Кто едет? (состав)
5. Детали (звёзды, питание)
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict, Optional
from app.models.domain import TourOffer, FoodType


class PartialSearchParams(TypedDict, total=False):
    """Частично заполненные параметры поиска."""
    # Туристы
    adults: int
    children: list[int]
    
    # Направление
    destination_country: str
    destination_region: str
    destination_resort: str
    destination_city: str
    
    # Даты
    date_from: date
    date_to: date
    nights: int
    
    # Город вылета - ОБЯЗАТЕЛЬНЫЙ ПАРАМЕТР!
    departure_city: str
    
    # Отель
    hotel_name: str
    stars: int
    
    # Питание
    food_type: FoodType
    
    # === НОВЫЕ ПАРАМЕТРЫ (GAP Analysis) ===
    # Услуги отелей (ID для параметра services)
    services: list[int]
    
    # Типы отелей (для параметра hoteltypes)
    hotel_types: list[str]
    
    # Тип тура (для параметра tourtype)
    tour_type: int
    
    # Флаги
    skip_quality_check: bool
    
    # === STRICT SLOT FILLING FLAGS ===
    # КРИТИЧНО: Эти флаги показывают, что параметр ЯВНО указан пользователем!
    adults_explicit: bool       # adults указан явно ("2 человека", "вдвоём")
    dates_confirmed: bool       # Дата указана явно ("15 февраля")
    is_exact_date: bool         # Указана точная дата (не "в феврале")
    children_mentioned: bool    # Упомянуты дети (нужен возраст)
    children_count_mentioned: int  # Сколько детей упомянуто
    
    # === P1: EXPLICIT FILTER FLAGS ===
    # Запрещаем неявные фильтры — добавлять только если явно указано пользователем!
    stars_explicit: bool        # Звёзды указаны явно ("5 звёзд")
    food_type_explicit: bool    # Питание указано явно ("всё включено")
    hotel_name_explicit: bool   # Отель указан явно (не город/курорт)
    
    # === P1: DATE PRECISION ===
    # Точность указания дат (для month-only проверки)
    date_precision: str  # "exact" | "month" | "season" | None


class Message(TypedDict):
    """Сообщение в истории диалога."""
    role: str
    content: str


class AgentState(TypedDict):
    """Состояние агента для LangGraph."""
    messages: list[Message]
    search_params: PartialSearchParams
    missing_info: list[str]
    tour_offers: list[TourOffer]
    response: str
    intent: Optional[str]
    error: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    awaiting_phone: bool
    selected_tour_id: Optional[str]
    cascade_stage: int
    quality_check_asked: bool
    clarification_asked: bool  # Soft Clarification: спрашивали про звёзды/питание
    is_first_message: bool
    # Флаг: было ли приветствие
    greeted: bool
    # P3 FIX: Групповая заявка (7+ человек)
    is_group_request: bool
    group_size: int
    group_warning: bool  # P3: предупреждение для 7-9 человек
    # Невалидная страна
    invalid_country: Optional[str]
    # Флаг гибкого поиска (±5 дней после согласия)
    flex_search: bool
    # Количество дней расширения поиска (по умолчанию 2, после согласия 5)
    flex_days: int
    # Флаг: бот предложил действие, ждём согласия
    awaiting_agreement: bool
    # Тип предложенного действия
    pending_action: Optional[str]  # "flex_dates", "any_hotel", etc.
    # Счётчик попыток поиска (для предотвращения зацикливания)
    search_attempts: int
    # Флаг: уже предлагали другой город вылета
    offered_alt_departure: bool
    # Флаг: уже предлагали другой тип питания (GAP Analysis: Smart Fallback)
    offered_alt_food: bool
    # Флаг: уже предлагали понизить звёзды (GAP Analysis: Smart Fallback)
    offered_lower_stars: bool
    # P5 FIX: Проверка доступных типов питания для отеля
    alt_food_checked: bool
    available_food_types: Optional[list]
    available_food_for_hotel: Optional[str]
    # КРИТИЧНО: количество детей, для которых нужен возраст
    missing_child_ages: int
    # Контекст последнего вопроса (для интерпретации коротких ответов типа "5")
    last_question_type: Optional[str]  # "nights", "adults", "stars", "dates", etc.
    # P2 FIX: Город двойного назначения (Сочи/Анапа), требующий уточнения
    ambiguous_city: Optional[str]
    # === PAGINATION (GAP Analysis) ===
    # ID последнего поискового запроса (для пагинации и continue)
    last_search_id: Optional[str]
    # ID страны последнего поиска
    last_country_id: Optional[int]
    # Текущая страница результатов
    current_page: int
    # Флаг: есть ли ещё результаты для загрузки
    has_more_results: bool
    
    # === SEARCH MODE (Strict Slot Filling) ===
    # "package" — пакетный тур (требует departure_city)
    # "hotel_only" — только отель (НЕ требует departure_city)
    # "burning" — горящие туры (гибкие даты)
    search_mode: str  # "package" | "hotel_only" | "burning"
    
    # === P1: API CALL TRACKING ===
    api_call_made: bool  # Был ли фактический API вызов (для запрета "проверил" без API)
    
    # === FIX 2.3: ПРИЧИНА ОТСУТСТВИЯ ТУРОВ ===
    search_reason: Optional[str]  # Причина отсутствия туров ("no_tours_with_food_type", "no_tours_with_filters", etc.)
    search_suggestion: Optional[str]  # Рекомендации/альтернативы (например, доступные типы питания)
    
    # === FIX: UNKNOWN COUNTRY/DEPARTURE FALLBACK ===
    unknown_country: bool  # Флаг: страна не найдена в справочнике
    unknown_departure: bool  # Флаг: город вылета не найден в справочнике
    awaiting_country_selection: bool  # Ожидаем выбор страны из альтернатив
    awaiting_departure_selection: bool  # Ожидаем выбор города вылета из альтернатив
    
    # === FIX: NO ROUTES FALLBACK ===
    no_routes: bool  # Флаг: нет маршрута из города в направление
    awaiting_route_selection: bool  # Ожидаем выбор альтернативного города/направления


# ==================== КАСКАД ВОПРОСОВ ====================
# СТРОГИЙ ПОРЯДОК: Страна -> Откуда -> Когда -> Кто -> Детали

# P5 FIX: Добавлена Россия для вопроса о звёздности
MASS_DESTINATIONS = ["Турция", "Египет", "ОАЭ", "Таиланд", "Россия"]

# Сезонность стран (для умной обработки "нет результатов")
COUNTRY_SEASONS = {
    "Турция": {
        "high": [5, 6, 7, 8, 9, 10],  # Май-Октябрь
        "low": [11, 12, 1, 2, 3, 4],   # Ноябрь-Апрель
        "low_message": "В это время в Турции зимний сезон, купаться в море холодно. Пляжные отели закрыты."
    },
    "Египет": {
        "high": [1, 2, 3, 4, 5, 10, 11, 12],
        "low": [6, 7, 8, 9],
        "low_message": "Летом в Египте очень жарко (+40°C), но можно отдыхать."
    },
    "ОАЭ": {
        "high": [10, 11, 12, 1, 2, 3, 4],
        "low": [5, 6, 7, 8, 9],
        "low_message": "Летом в ОАЭ очень жарко (+45°C), большинство туристов не едут."
    },
    "Таиланд": {
        "high": [11, 12, 1, 2, 3],
        "low": [4, 5, 6, 7, 8, 9, 10],
        "low_message": "В это время в Таиланде сезон дождей, возможны кратковременные ливни."
    },
}

# Названия параметров
PARAM_NAMES_RU = {
    "destination_country": "страна",
    "departure_city": "город вылета",
    "date_from": "даты",
    "nights": "ночи",
    "adults": "туристы",
    "children": "дети",
    "stars": "звёздность",
    "food_type": "питание",
}

SKIP_QUALITY_PHRASES = [
    "всё равно", "все равно", "не важно", "неважно", "любой", "любые", "любое",
    "на ваш вкус", "на ваше усмотрение", "что-нибудь хорошее",
    "подбери сам", "подберите сами", "без разницы", "не принципиально",
    "оптимальное", "оптимальный", "какой отель", "какой угодно",
    "любой отель", "все равно какой", "всё равно какой", "хороший отель",
    "нормальный", "средний",
    # P1 FIX: Расширенный список для питания
    "любое питание", "любой тип питания", "рассмотрим варианты", "рассмотрю варианты",
    "посмотрим", "покажите разные", "разные варианты", "предложите варианты"
]

# Фразы согласия — пользователь согласен на предложенное действие
AGREEMENT_PHRASES = [
    "хорошо", "ок", "ok", "окей", "давай", "давайте", "погнали", "поехали",
    "да", "конечно", "согласен", "согласна", "пойдёт", "пойдет", "годится",
    "ладно", "можно", "валяй", "вперёд", "вперед", "супер", "отлично",
    "принимается", "договорились", "идёт", "идет", "норм", "нормально",
    "буду рад", "было бы хорошо", "почему бы и нет", "звучит хорошо"
]

# Для совместимости
BASE_PARAMS = ["destination_country", "departure_city", "date_from", "adults"]
DETAIL_PARAMS = ["stars", "food_type"]
REQUIRED_PARAMS = BASE_PARAMS.copy()
CLARIFICATION_QUESTIONS = {
    "destination_country": "В какую страну планируете поездку?",
    "departure_city": "Из какого города планируете вылет?",
    "date_from": "Когда планируете отпуск?",
    "adults": "Сколько человек поедет?",
}
QUALITY_CHECK_QUESTION = "Какой уровень отеля — 5 звёзд всё включено или рассмотрим варианты?"


def get_cascade_stage(params: PartialSearchParams, search_mode: str = "package") -> int:
    """
    Определяет текущий этап каскада.
    
    СТРОГИЙ ПОРЯДОК (согласно ТЗ):
    1 — нужна страна
    2 — нужен город вылета (для package, НЕ для hotel_only!)
    3 — нужны даты
    4 — нужен состав (adults) И длительность (nights)
    5 — нужны детали (звёзды/питание) — для массовых направлений
    6 — всё собрано, можно искать
    
    РЕЖИМЫ:
    - "package" — пакетный тур (требует departure_city)
    - "hotel_only" — только отель (НЕ требует departure_city)
    - "burning" — горящие туры (гибкие даты)
    
    КРИТИЧНО: Не запускаем поиск без adults и nights!
    """
    # Этап 1: нет страны
    # P0 STABILIZATION: Страна ОБЯЗАТЕЛЬНА даже при указании hotel_name!
    # Без страны нельзя искать отель в справочнике Tourvisor.
    if not params.get("destination_country"):
        return 1
    
    # Этап 2: нужен город вылета (ТОЛЬКО для package и burning!)
    # Для hotel_only — пропускаем этот этап
    # ВАЖНО: Даже при указании hotel_name требуем departure_city (если не hotel_only!)
    if search_mode != "hotel_only" and not params.get("departure_city"):
        return 2
    
    # Этап 3: нет дат
    # КРИТИЧНО: dates_confirmed показывает что дата ЯВНО указана
    dates_confirmed = params.get("dates_confirmed", False)
    has_date = params.get("date_from") and dates_confirmed
    
    if not has_date:
        return 3
    
    # Этап 4: нет состава ИЛИ длительности
    # КРИТИЧНО: adults должен быть ЯВНО указан пользователем (adults_explicit)!
    adults_explicit = params.get("adults_explicit", False)
    adults = params.get("adults")
    nights = params.get("nights")
    
    # P0 STABILIZATION: Если есть date_from И date_to — nights вычисляется автоматически!
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    
    # Проверяем: можно ли вычислить nights из дат?
    nights_can_be_calculated = (
        date_from and date_to and 
        date_to != date_from  # Это диапазон, не одна дата
    )
    
    # Если adults не указан ЯВНО — спрашиваем
    if not adults or not adults_explicit:
        return 4
    
    # nights обязателен ТОЛЬКО если НЕТ date_to (или date_to == date_from)
    # FIX CASE-002/008: Для праздников ВСЕГДА спрашиваем nights (если не указан явно)
    # Праздник — это диапазон возможных дат, а не конкретная длительность поездки
    date_precision = params.get("date_precision")
    nights_explicit = params.get("nights_explicit", False)
    
    if date_precision == "holiday" and not nights_explicit:
        # Праздник + nights не указан явно → спрашиваем
        return 4
    
    if not nights and not nights_can_be_calculated:
        return 4
    
    # Этап 5: для массовых направлений нужны детали
    country = params.get("destination_country", "")
    is_mass = country in MASS_DESTINATIONS
    
    if is_mass and not params.get("skip_quality_check"):
        has_stars = params.get("stars") is not None
        has_food = params.get("food_type") is not None
        
        if not has_stars or not has_food:
            return 5
    
    # Всё собрано
    return 6


def get_missing_required_params(params: PartialSearchParams, search_mode: str = "package") -> list[str]:
    """
    Определяет недостающие обязательные параметры.
    
    P0 STABILIZATION:
    - departure_city обязателен для package/burning (не для hotel_only)
    - nights НЕ обязателен если есть date_from + date_to
    """
    missing = []
    
    # Страна — всегда обязательна (даже при hotel_name!)
    if not params.get("destination_country"):
        missing.append("destination_country")
    
    # Город вылета — обязателен для package/burning
    if search_mode != "hotel_only" and not params.get("departure_city"):
        missing.append("departure_city")
    
    # Дата начала — обязательна
    if not params.get("date_from"):
        missing.append("date_from")
    
    # Взрослые — обязательны
    if not params.get("adults"):
        missing.append("adults")
    
    # nights — НЕ обязателен если есть date_from + date_to (диапазон)
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    nights = params.get("nights")
    
    if not nights and not (date_from and date_to and date_to != date_from):
        missing.append("nights")
    
    return missing


def get_funnel_stage(params: PartialSearchParams) -> str:
    """Определяет этап воронки (для совместимости)."""
    stage = get_cascade_stage(params)
    
    if stage <= 4:
        return "base"
    if stage == 5:
        return "details"
    return "search"


def needs_quality_check(params: PartialSearchParams) -> bool:
    """Проверяет, нужен ли вопрос о качестве."""
    if params.get("skip_quality_check"):
        return False
    if params.get("hotel_name"):
        return False
    
    country = params.get("destination_country", "")
    if country not in MASS_DESTINATIONS:
        return False
    
    has_stars = params.get("stars") is not None
    has_food = params.get("food_type") is not None
    
    return not (has_stars and has_food)


def check_skip_quality_phrase(text: str) -> bool:
    """Проверяет, хочет ли пользователь пропустить уточнение."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in SKIP_QUALITY_PHRASES)


def is_off_season(country: str, month: int) -> tuple[bool, str]:
    """
    Проверяет, является ли месяц несезоном для страны.
    
    Returns:
        (is_off_season, message)
    """
    if country not in COUNTRY_SEASONS:
        return False, ""
    
    season_info = COUNTRY_SEASONS[country]
    if month in season_info.get("low", []):
        return True, season_info.get("low_message", "")
    
    return False, ""


def format_context(params: PartialSearchParams) -> str:
    """
    Форматирует контекст (что уже известно) для ответа.
    
    КРИТИЧНО: Показываем ТОЛЬКО подтверждённые параметры!
    - adults показываем только если adults_explicit=True
    - date_from показываем только если dates_confirmed=True
    - departure_city, destination_country показываем всегда (они не галлюцинируются)
    """
    parts = []
    
    # Страна — всегда показываем (не галлюцинируется)
    if params.get("destination_country"):
        parts.append(params["destination_country"])
    if params.get("destination_resort"):
        parts.append(params["destination_resort"])
    
    # Город вылета — всегда показываем (не галлюцинируется)
    if params.get("departure_city"):
        parts.append(f"из {params['departure_city']}")
    
    # Дата — показываем ТОЛЬКО если dates_confirmed=True!
    if params.get("date_from") and params.get("dates_confirmed"):
        d = params["date_from"]
        if isinstance(d, date):
            nights = params.get("nights")
            if nights:
                parts.append(f"{d.strftime('%d.%m')}, {nights} ночей")
            else:
                parts.append(f"{d.strftime('%d.%m')}")
    
    # Количество туристов — показываем ТОЛЬКО если adults_explicit=True!
    if params.get("adults") and params.get("adults_explicit"):
        adults = params["adults"]
        children = params.get("children", [])
        
        if children:
            # КРИТИЧНО: Показываем и количество, и возраст детей!
            # Формат: "2 взр + 1 дет (7 лет)" или "2 взр + 2 дет (5 и 10 лет)"
            if len(children) == 1:
                kids_text = f"1 дет ({children[0]} лет)"
            else:
                ages_text = ", ".join(str(age) for age in children)
                kids_text = f"{len(children)} дет ({ages_text} лет)"
            parts.append(f"{adults} взр + {kids_text}")
        else:
            parts.append(f"{adults} взр")
    if params.get("stars"):
        parts.append(f"{params['stars']}*")
    if params.get("food_type"):
        parts.append(params["food_type"].value)
    
    return ", ".join(parts) if parts else ""


def create_initial_state() -> AgentState:
    """Создаёт начальное состояние агента."""
    return AgentState(
        messages=[],
        search_params={},
        missing_info=[],
        tour_offers=[],
        response="",
        intent=None,
        error=None,
        customer_name=None,
        customer_phone=None,
        awaiting_phone=False,
        selected_tour_id=None,
        cascade_stage=1,
        quality_check_asked=False,
        clarification_asked=False,  # Soft Clarification
        is_first_message=True,
        greeted=False,
        is_group_request=False,
        group_size=0,
        group_warning=False,  # P3 FIX
        invalid_country=None,
        flex_search=False,
        flex_days=2,  # По умолчанию ±2 дня для чартерных рейсов
        awaiting_agreement=False,
        pending_action=None,
        search_attempts=0,
        offered_alt_departure=False,
        offered_alt_food=False,  # GAP Analysis: Smart Fallback по питанию
        offered_lower_stars=False,  # GAP Analysis: Smart Fallback по звёздам
        alt_food_checked=False,  # P5 FIX: проверка питания для отеля
        available_food_types=None,
        available_food_for_hotel=None,
        missing_child_ages=0,
        last_question_type=None,  # Контекст для интерпретации "5" → nights/adults
        ambiguous_city=None,  # P2 FIX: Город двойного назначения
        # === PAGINATION (GAP Analysis) ===
        last_search_id=None,
        last_country_id=None,
        current_page=1,
        has_more_results=False,
        # === SEARCH MODE (Strict Slot Filling) ===
        search_mode="package",  # По умолчанию пакетный тур
        # === P1: API CALL TRACKING ===
        api_call_made=False,  # Был ли фактический API вызов
        # === FIX 2.3: ПРИЧИНА ОТСУТСТВИЯ ТУРОВ ===
        search_reason=None,
        search_suggestion=None,
    )

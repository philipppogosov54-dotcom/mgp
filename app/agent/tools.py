"""
MGP AI Agent Tools Definitions.

Определения инструментов для работы с API Tourvisor.
Реализованы согласно официальной документации Tourvisor API:
- search.php (асинхронный поиск туров)
- result.php (получение результатов)
- hottours.php (горящие туры)
- actualize.php (актуализация цен)
- actdetail.php (детали рейса)
- hotel.php (контент отеля)
- list.php (справочники)

Каждый инструмент имеет строгую схему параметров.
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict
from datetime import date, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


# ==================== SEARCH TYPES ====================

class SearchMode(str, Enum):
    """Режим поиска туров."""
    REGULAR = "regular"      # Обычный поиск (search.php)
    HOT_TOURS = "hot"        # Горящие туры (hottours.php)
    STRICT_HOTEL = "strict"  # Строгий поиск по отелю


# ==================== ENUMS ====================

class MealType(str, Enum):
    """Типы питания."""
    RO = "RO"   # Room Only (без питания)
    BB = "BB"   # Bed & Breakfast (завтрак)
    HB = "HB"   # Half Board (завтрак + ужин)
    FB = "FB"   # Full Board (3-разовое)
    AI = "AI"   # All Inclusive
    UAI = "UAI" # Ultra All Inclusive


class ValidationError(Exception):
    """Ошибка валидации параметров."""
    pass


class BlockingFactor(str, Enum):
    """Блокирующие факторы для поиска."""
    MISSING_CHILD_AGES = "child_ages_required"
    MISSING_DEPARTURE_CITY = "departure_city_required"
    MISSING_COUNTRY = "country_required"
    MISSING_DATES = "dates_required"
    HOTEL_ID_REQUIRED = "hotel_id_required"


# ==================== TOOL SCHEMAS ====================

class HotelSearchResult(TypedDict):
    """Результат поиска отеля по названию."""
    hotel_id: int
    name: str
    stars: int
    country: str
    region: str
    meals_available: list[str]


class SearchToursParams(TypedDict, total=False):
    """
    Параметры поиска туров (строгая схема).
    
    Используется для search.php.
    """
    departure_city: str        # REQUIRED
    country: str               # REQUIRED
    date_from: date           # REQUIRED (формат dd.mm.yyyy)
    date_to: date             # REQUIRED (формат dd.mm.yyyy)
    nights_from: int          # default: 7
    nights_to: int            # default: 10
    adults: int               # REQUIRED
    child_ages: list[int]     # REQUIRED (как childage1, childage2...)
    hotel_ids: list[int]      # optional (список через запятую в API)
    stars: list[str]          # optional: ["3", "4", "5"]
    meal_types: list[str]     # optional: ["AI", "BB", etc.]
    is_strict_hotel: bool     # Строгий поиск по отелю


class HotToursParams(TypedDict, total=False):
    """
    Параметры для получения горящих туров.
    
    Используется для hottours.php (синхронный метод).
    """
    city: int                 # ID города вылета (REQUIRED)
    country: int              # ID страны (optional)
    items: int                # Количество результатов (default: 10)


class ActualizeParams(TypedDict):
    """
    Параметры актуализации тура.
    
    Используется для actualize.php.
    """
    tour_id: str              # REQUIRED - ID тура


class FlightDetailsParams(TypedDict):
    """
    Параметры для получения деталей рейса.
    
    Используется для actdetail.php (новый метод).
    """
    tour_id: str              # REQUIRED - ID тура


class HotelContentParams(TypedDict):
    """
    Параметры для получения контента отеля.
    
    Используется для hotel.php.
    """
    hotel_code: int           # REQUIRED - код отеля


class DictionaryParams(TypedDict, total=False):
    """
    Параметры для справочников.
    
    Используется для list.php.
    """
    type: str                 # country, departure, hotel, region
    hotcountry: int           # ID страны (для отелей)


# ==================== VALIDATION FUNCTIONS ====================

def validate_search_params(params: dict) -> tuple[bool, Optional[BlockingFactor], str]:
    """
    Валидация параметров поиска.
    
    Returns:
        tuple: (is_valid, blocking_factor, error_message)
    """
    # Проверка страны
    if not params.get("country"):
        return (False, BlockingFactor.MISSING_COUNTRY, 
                "В какую страну планируете поездку?")
    
    # Проверка города вылета
    if not params.get("departure_city"):
        return (False, BlockingFactor.MISSING_DEPARTURE_CITY,
                "Из какого города планируете вылет?")
    
    # Проверка дат
    if not params.get("date_from"):
        return (False, BlockingFactor.MISSING_DATES,
                "Когда планируете отпуск?")
    
    # КРИТИЧЕСКАЯ ПРОВЕРКА: дети без возрастов
    children_count = params.get("children_count", 0)
    child_ages = params.get("child_ages", [])
    
    if children_count > 0 and len(child_ages) != children_count:
        missing = children_count - len(child_ages)
        word = "ребёнка" if missing == 1 else "детей"
        return (False, BlockingFactor.MISSING_CHILD_AGES,
                f"Укажите возраст {word}. Это важно для точного расчёта цены.")
    
    # Проверка отеля (если упомянут, но нет ID)
    if params.get("hotel_name") and not params.get("hotel_ids"):
        return (False, BlockingFactor.HOTEL_ID_REQUIRED,
                f"Ищу отель «{params['hotel_name']}» в базе...")
    
    return (True, None, "")


def check_child_ages_required(
    user_text: str, 
    current_children: int, 
    current_ages: list[int]
) -> tuple[bool, str]:
    """
    Проверяет, нужно ли запрашивать возраст детей.
    
    Returns:
        tuple: (need_to_ask, question_text)
    """
    # Ключевые слова, указывающие на наличие детей
    child_keywords = [
        "ребенок", "ребёнок", "дети", "детей", "детьми", 
        "сын", "сына", "сыном", "дочь", "дочери", "дочкой",
        "малыш", "школьник", "подросток"
    ]
    
    text_lower = user_text.lower()
    has_child_mention = any(kw in text_lower for kw in child_keywords)
    
    # Если упомянуты дети, но возрасты не известны
    if has_child_mention and not current_ages:
        # Определяем количество детей из текста
        import re
        
        # "2 детей", "двое детей"
        num_match = re.search(r'(\d+)\s*(?:детей|ребенк|детьми)', text_lower)
        if num_match:
            count = int(num_match.group(1))
            if count == 1:
                return (True, "Сколько лет ребёнку?")
            else:
                return (True, f"Укажите возраст каждого ребёнка ({count} чел.).")
        
        # "с ребенком", "с сыном" — один ребенок
        single_child = re.search(r'с\s+(?:ребенком|ребёнком|сыном|дочкой|дочерью|малышом)', text_lower)
        if single_child:
            return (True, "Сколько лет ребёнку? Это важно для расчёта цены.")
        
        # Просто упоминание "дети" без числа
        if "дети" in text_lower or "детьми" in text_lower:
            return (True, "Сколько детей едет и какого они возраста?")
    
    # Если известно количество, но не все возрасты
    if current_children > len(current_ages):
        missing = current_children - len(current_ages)
        if missing == 1:
            return (True, "Укажите возраст ребёнка.")
        return (True, f"Укажите возраст {missing} детей.")
    
    return (False, "")


# ==================== DATE PARSING ====================

def parse_natural_dates(text: str, current_date: date) -> tuple[Optional[date], Optional[date], Optional[int]]:
    """
    Парсинг естественного языка в даты.
    
    Args:
        text: Текст пользователя
        current_date: Текущая дата
        
    Returns:
        tuple: (date_from, date_to, nights)
    """
    import re
    text_lower = text.lower()
    
    year = current_date.year
    date_from = None
    date_to = None
    nights = None
    
    # Паттерны для месяцев
    month_map = {
        'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4,
        'май': 5, 'мая': 5, 'июн': 6, 'июл': 7, 'август': 8,
        'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12
    }
    
    # "в середине июля" → 10-20 числа
    mid_match = re.search(r'середин[еау]\s+(\w+)', text_lower)
    if mid_match:
        month_text = mid_match.group(1)
        for key, month in month_map.items():
            if key in month_text:
                target = date(year, month, 10)
                if target < current_date:
                    target = date(year + 1, month, 10)
                return (target, target + timedelta(days=10), None)
    
    # "в начале августа" → 1-10 числа
    start_match = re.search(r'начал[еоа]\s+(\w+)', text_lower)
    if start_match:
        month_text = start_match.group(1)
        for key, month in month_map.items():
            if key in month_text:
                target = date(year, month, 1)
                if target < current_date:
                    target = date(year + 1, month, 1)
                return (target, target + timedelta(days=10), None)
    
    # "в конце июля" → 20-31 числа
    end_match = re.search(r'конц[еау]\s+(\w+)', text_lower)
    if end_match:
        month_text = end_match.group(1)
        for key, month in month_map.items():
            if key in month_text:
                # Последний день месяца
                if month == 12:
                    last_day = date(year, 12, 31)
                else:
                    last_day = date(year, month + 1, 1) - timedelta(days=1)
                target = date(year, month, 20)
                if target < current_date:
                    target = date(year + 1, month, 20)
                    last_day = date(year + 1, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 12, 31)
                return (target, last_day, None)
    
    # "на майские" → 1-10 мая
    if "майски" in text_lower:
        target = date(year, 5, 1)
        if target < current_date:
            target = date(year + 1, 5, 1)
        return (target, target + timedelta(days=10), None)
    
    # "на новый год" → 28.12 - 08.01
    if "новый год" in text_lower or "новогодн" in text_lower:
        target = date(year, 12, 28)
        if target < current_date:
            target = date(year + 1, 12, 28)
        return (target, target + timedelta(days=11), None)
    
    # "через неделю"
    if "через недел" in text_lower:
        return (current_date + timedelta(days=7), current_date + timedelta(days=14), 7)
    
    # "через 2 недели"
    weeks_match = re.search(r'через\s+(\d+)\s*недел', text_lower)
    if weeks_match:
        weeks = int(weeks_match.group(1))
        return (current_date + timedelta(days=weeks*7), current_date + timedelta(days=weeks*7 + 7), 7)
    
    # Конкретные даты "с 5 по 12 июня"
    range_match = re.search(r'с\s*(\d{1,2})\s*(?:по|до|-)\s*(\d{1,2})\s+(\w+)', text_lower)
    if range_match:
        day_from = int(range_match.group(1))
        day_to = int(range_match.group(2))
        month_text = range_match.group(3)
        for key, month in month_map.items():
            if key in month_text:
                try:
                    d_from = date(year, month, day_from)
                    d_to = date(year, month, day_to)
                    if d_from < current_date:
                        d_from = date(year + 1, month, day_from)
                        d_to = date(year + 1, month, day_to)
                    return (d_from, d_to, (d_to - d_from).days)
                except ValueError:
                    pass
    
    # Просто месяц "июнь", "в июне"
    for key, month in month_map.items():
        if key in text_lower:
            target = date(year, month, 1)
            if target < current_date:
                target = date(year + 1, month, 1)
            return (target, target + timedelta(days=14), None)
    
    return (None, None, None)


# ==================== HOTEL LOOKUP ====================

# Известные сети отелей с автоопределением страны
HOTEL_CHAINS = {
    # Турция
    "rixos": ("Турция", ["Rixos Premium Belek", "Rixos Sungate", "Rixos Premium Bodrum"]),
    "calista": ("Турция", ["Calista Luxury Resort"]),
    "regnum": ("Турция", ["Regnum Carya"]),
    "maxx royal": ("Турция", ["Maxx Royal Belek", "Maxx Royal Kemer"]),
    "gloria": ("Турция", ["Gloria Serenity", "Gloria Verde", "Gloria Golf"]),
    "titanic": ("Турция", ["Titanic Deluxe Belek", "Titanic Mardan Palace"]),
    "voyage": ("Турция", ["Voyage Belek", "Voyage Sorgun"]),
    
    # Египет
    "baron": ("Египет", ["Baron Palace", "Baron Resort"]),
    "steigenberger": ("Египет", ["Steigenberger Aldau", "Steigenberger Pure Lifestyle"]),
    "rixos sharm": ("Египет", ["Rixos Sharm El Sheikh"]),
    "sunrise": ("Египет", ["Sunrise Arabian Beach", "Sunrise Select Garden Beach"]),
    
    # ОАЭ
    "atlantis": ("ОАЭ", ["Atlantis The Palm", "Atlantis The Royal"]),
    "burj al arab": ("ОАЭ", ["Burj Al Arab"]),
    "jumeirah": ("ОАЭ", ["Jumeirah Beach Hotel", "Jumeirah Zabeel Saray"]),
    "hilton dubai": ("ОАЭ", ["Hilton Dubai Jumeirah", "Hilton Dubai The Walk"]),
    
    # Таиланд
    "centara": ("Таиланд", ["Centara Grand Beach", "Centara Kata Resort"]),
    "banyan tree": ("Таиланд", ["Banyan Tree Phuket", "Banyan Tree Samui"]),
}


def find_hotel_chain(query: str) -> tuple[Optional[str], list[str]]:
    """
    Ищет сеть отелей по названию.
    
    Returns:
        tuple: (country, list_of_hotels) или (None, [])
    """
    query_lower = query.lower()
    
    for chain_key, (country, hotels) in HOTEL_CHAINS.items():
        if chain_key in query_lower:
            return (country, hotels)
    
    return (None, [])


def extract_hotel_name(text: str) -> Optional[str]:
    """
    Извлекает название отеля из текста.
    """
    text_lower = text.lower()
    
    # Проверяем известные сети
    for chain_key in HOTEL_CHAINS:
        if chain_key in text_lower:
            return chain_key.title()
    
    # Паттерны типа "отель X", "в X отеле"
    import re
    
    patterns = [
        r'отел[ьея]\s+[«"]?([^»",.]+)[»"]?',
        r'в\s+[«"]?([^»",.]+)[»"]?\s+отел',
        r'гостиниц[ауе]\s+[«"]?([^»",.]+)[»"]?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1).strip().title()
    
    return None


# ==================== MEAL TYPE HELPERS ====================

MEAL_DESCRIPTIONS = {
    "RO": "без питания",
    "BB": "только завтрак",
    "HB": "завтрак и ужин (полупансион)",
    "FB": "трёхразовое питание (полный пансион)",
    "AI": "всё включено",
    "UAI": "ультра всё включено",
}


def get_meal_description(meal_code: str) -> str:
    """Получить описание типа питания."""
    return MEAL_DESCRIPTIONS.get(meal_code.upper(), meal_code)


def suggest_meal_alternatives(requested: str, available: list[str]) -> str:
    """
    Формирует сообщение об альтернативных типах питания.
    """
    if not available:
        return "Информация о питании недоступна."
    
    requested_desc = get_meal_description(requested)
    available_desc = ", ".join([get_meal_description(m) for m in available])
    
    # Находим лучшую альтернативу
    meal_rank = {"RO": 0, "BB": 1, "HB": 2, "FB": 3, "AI": 4, "UAI": 5}
    requested_rank = meal_rank.get(requested.upper(), 0)
    
    best_alt = None
    best_diff = float('inf')
    
    for meal in available:
        diff = abs(meal_rank.get(meal.upper(), 0) - requested_rank)
        if diff < best_diff:
            best_diff = diff
            best_alt = meal
    
    if best_alt:
        best_desc = get_meal_description(best_alt)
        return f"Тариф «{requested_desc}» недоступен. Ближайший вариант — «{best_desc}»."
    
    return f"Доступные варианты питания: {available_desc}."

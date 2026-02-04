#!/usr/bin/env python3
"""
Русская морфология для текстов ассистента.

Модуль для склонения городов, стран и курортов в правильные падежи.
Использует pymorphy2 если доступен, иначе fallback на словарь.
"""

from functools import lru_cache
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Попытка загрузить pymorphy2
try:
    import pymorphy2
    _morph = pymorphy2.MorphAnalyzer()
    MORPH_AVAILABLE = True
    logger.info("✅ pymorphy2 загружен для склонения")
except ImportError:
    _morph = None
    MORPH_AVAILABLE = False
    logger.warning("⚠️ pymorphy2 не установлен, используем словарь")


# ==================== СЛОВАРИ ИСКЛЮЧЕНИЙ ====================

# Несклоняемые названия (остаются без изменений)
NON_DECLINABLE = {
    "оаэ", "сочи", "баку", "тбилиси", "батуми", "гоа", "бали", "дели",
    "дубай", "абу-даби", "шри-ланка", "пхукет", "самуи", "паттайя",
    "хургада", "шарм-эль-шейх", "макао", "токио", "осло", "мале"
}

# Предлоги для курортов/островов (на вместо в)
PREPOSITION_NA = {
    "пхукет", "самуи", "бали", "гоа", "кипр", "крит", "родос", "корфу",
    "санторини", "мальдивы", "сейшелы", "маврикий", "занзибар", "куба",
    "ямайка", "барбадос", "доминикана", "мальта", "сицилия", "сардиния"
}

# Ручные формы для сложных случаев (им -> род, вин, предл)
MANUAL_FORMS = {
    # Города (расширенный список)
    "москва": {"род": "Москвы", "вин": "Москву", "предл": "Москве"},
    "нижний новгород": {"род": "Нижнего Новгорода", "вин": "Нижний Новгород", "предл": "Нижнем Новгороде"},
    "санкт-петербург": {"род": "Санкт-Петербурга", "вин": "Санкт-Петербург", "предл": "Санкт-Петербурге"},
    "ростов-на-дону": {"род": "Ростова-на-Дону", "вин": "Ростов-на-Дону", "предл": "Ростове-на-Дону"},
    "набережные челны": {"род": "Набережных Челнов", "вин": "Набережные Челны", "предл": "Набережных Челнах"},
    "великий новгород": {"род": "Великого Новгорода", "вин": "Великий Новгород", "предл": "Великом Новгороде"},
    "екатеринбург": {"род": "Екатеринбурга", "вин": "Екатеринбург", "предл": "Екатеринбурге"},
    "казань": {"род": "Казани", "вин": "Казань", "предл": "Казани"},
    "новосибирск": {"род": "Новосибирска", "вин": "Новосибирск", "предл": "Новосибирске"},
    "краснодар": {"род": "Краснодара", "вин": "Краснодар", "предл": "Краснодаре"},
    "самара": {"род": "Самары", "вин": "Самару", "предл": "Самаре"},
    "воркута": {"род": "Воркуты", "вин": "Воркуту", "предл": "Воркуте"},
    "воркуты": {"род": "Воркуты", "вин": "Воркуту", "предл": "Воркуте"},  # Косой падеж
    
    # Страны (расширенный список)
    "турция": {"род": "Турции", "вин": "Турцию", "предл": "Турции"},
    "египет": {"род": "Египта", "вин": "Египет", "предл": "Египте"},
    "таиланд": {"род": "Таиланда", "вин": "Таиланд", "предл": "Таиланде"},
    "вьетнам": {"род": "Вьетнама", "вин": "Вьетнам", "предл": "Вьетнаме"},
    "индонезия": {"род": "Индонезии", "вин": "Индонезию", "предл": "Индонезии"},
    "куба": {"род": "Кубы", "вин": "Кубу", "предл": "Кубе"},
    "оаэ": {"род": "ОАЭ", "вин": "ОАЭ", "предл": "ОАЭ"},
    "сша": {"род": "США", "вин": "США", "предл": "США"},
    "шри-ланка": {"род": "Шри-Ланки", "вин": "Шри-Ланку", "предл": "Шри-Ланке"},
    "доминикана": {"род": "Доминиканы", "вин": "Доминикану", "предл": "Доминикане"},
    "мальдивы": {"род": "Мальдив", "вин": "Мальдивы", "предл": "Мальдивах"},
    "сейшелы": {"род": "Сейшел", "вин": "Сейшелы", "предл": "Сейшелах"},
    "филиппины": {"род": "Филиппин", "вин": "Филиппины", "предл": "Филиппинах"},
    "кипр": {"род": "Кипра", "вин": "Кипр", "предл": "Кипре"},
    "греция": {"род": "Греции", "вин": "Грецию", "предл": "Греции"},
    "испания": {"род": "Испании", "вин": "Испанию", "предл": "Испании"},
    "италия": {"род": "Италии", "вин": "Италию", "предл": "Италии"},
    "россия": {"род": "России", "вин": "Россию", "предл": "России"},
    "антарктида": {"род": "Антарктиды", "вин": "Антарктиду", "предл": "Антарктиде"},
    
    # Курорты
    "шарм-эль-шейх": {"род": "Шарм-эль-Шейха", "вин": "Шарм-эль-Шейх", "предл": "Шарм-эль-Шейхе"},
    "шарм": {"род": "Шарма", "вин": "Шарм", "предл": "Шарме"},
    "хургада": {"род": "Хургады", "вин": "Хургаду", "предл": "Хургаде"},
    "анталья": {"род": "Антальи", "вин": "Анталью", "предл": "Анталье"},
    "анталия": {"род": "Анталии", "вин": "Анталию", "предл": "Анталии"},
    "кемер": {"род": "Кемера", "вин": "Кемер", "предл": "Кемере"},
    "белек": {"род": "Белека", "вин": "Белек", "предл": "Белеке"},
    "сиде": {"род": "Сиде", "вин": "Сиде", "предл": "Сиде"},
    "аланья": {"род": "Аланьи", "вин": "Аланью", "предл": "Аланье"},
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _normalize(name: str) -> str:
    """Нормализация названия для поиска в словарях."""
    return name.lower().strip()


@lru_cache(maxsize=500)
def _decline_with_morph(word: str, case: str) -> Optional[str]:
    """
    Склонение слова через pymorphy2.
    
    Args:
        word: слово для склонения
        case: падеж ('gent' - род., 'accs' - вин., 'loct' - предл.)
    
    Returns:
        Склонённая форма или None если не удалось
    """
    if not MORPH_AVAILABLE or not _morph:
        return None
    
    try:
        parsed = _morph.parse(word)[0]
        inflected = parsed.inflect({case})
        if inflected:
            result = inflected.word
            # Сохраняем оригинальный регистр первой буквы
            if word and word[0].isupper():
                result = result.capitalize()
            return result
    except Exception:
        pass
    
    return None


def _decline_compound(name: str, case: str) -> Optional[str]:
    """
    Склонение составного названия (например, "Нижний Новгород").
    Склоняем каждое слово отдельно.
    """
    if not MORPH_AVAILABLE:
        return None
    
    words = name.split()
    if len(words) < 2:
        return None
    
    result_words = []
    for word in words:
        declined = _decline_with_morph(word, case)
        if declined:
            result_words.append(declined)
        else:
            result_words.append(word)
    
    return " ".join(result_words)


# ==================== ПУБЛИЧНЫЕ ФУНКЦИИ ====================

@lru_cache(maxsize=200)
def from_city(city: str) -> str:
    """
    Склонение города в родительный падеж с предлогом "из".
    
    Примеры:
        "Москва" -> "из Москвы"
        "Санкт-Петербург" -> "из Санкт-Петербурга"
        "Нижний Новгород" -> "из Нижнего Новгорода"
        "Сочи" -> "из Сочи"
    """
    if not city:
        return "из города"
    
    norm = _normalize(city)
    
    # 1. Проверяем несклоняемые
    if norm in NON_DECLINABLE:
        return f"из {city}"
    
    # 2. Проверяем ручной словарь
    if norm in MANUAL_FORMS:
        return f"из {MANUAL_FORMS[norm]['род']}"
    
    # 3. Пробуем pymorphy2
    if MORPH_AVAILABLE:
        # Составное название
        if " " in city:
            declined = _decline_compound(city, "gent")
            if declined:
                return f"из {declined}"
        else:
            declined = _decline_with_morph(city, "gent")
            if declined:
                return f"из {declined}"
    
    # 4. Fallback - возвращаем без склонения
    return f"из {city}"


@lru_cache(maxsize=200)
def to_country(country: str) -> str:
    """
    Склонение страны в винительный падеж с предлогом "в" или "на".
    
    Примеры:
        "Турция" -> "в Турцию"
        "Египет" -> "в Египет"
        "ОАЭ" -> "в ОАЭ"
        "Мальдивы" -> "на Мальдивы"
    """
    if not country:
        return "в страну"
    
    norm = _normalize(country)
    
    # Определяем предлог
    prep = "на" if norm in PREPOSITION_NA else "в"
    
    # 1. Проверяем несклоняемые
    if norm in NON_DECLINABLE:
        return f"{prep} {country}"
    
    # 2. Проверяем ручной словарь
    if norm in MANUAL_FORMS:
        return f"{prep} {MANUAL_FORMS[norm]['вин']}"
    
    # 3. Пробуем pymorphy2
    if MORPH_AVAILABLE:
        declined = _decline_with_morph(country, "accs")
        if declined:
            return f"{prep} {declined}"
    
    # 4. Fallback
    return f"{prep} {country}"


@lru_cache(maxsize=200)
def to_resort(resort: str) -> str:
    """
    Склонение курорта в винительный падеж с предлогом "в" или "на".
    
    Примеры:
        "Анталья" -> "в Анталью"
        "Пхукет" -> "на Пхукет"
        "Шарм-эль-Шейх" -> "в Шарм-эль-Шейх"
    """
    if not resort:
        return "на курорт"
    
    norm = _normalize(resort)
    
    # Определяем предлог
    prep = "на" if norm in PREPOSITION_NA else "в"
    
    # 1. Проверяем несклоняемые
    if norm in NON_DECLINABLE:
        return f"{prep} {resort}"
    
    # 2. Проверяем ручной словарь
    if norm in MANUAL_FORMS:
        return f"{prep} {MANUAL_FORMS[norm]['вин']}"
    
    # 3. Пробуем pymorphy2
    if MORPH_AVAILABLE:
        declined = _decline_with_morph(resort, "accs")
        if declined:
            return f"{prep} {declined}"
    
    # 4. Fallback
    return f"{prep} {resort}"


@lru_cache(maxsize=200)
def in_country(country: str) -> str:
    """
    Склонение страны в предложный падеж с предлогом "в" или "на".
    
    Примеры:
        "Турция" -> "в Турции"
        "Египет" -> "в Египте"
        "Мальдивы" -> "на Мальдивах"
    """
    if not country:
        return "в стране"
    
    norm = _normalize(country)
    
    # Определяем предлог
    prep = "на" if norm in PREPOSITION_NA else "в"
    
    # 1. Проверяем несклоняемые
    if norm in NON_DECLINABLE:
        return f"{prep} {country}"
    
    # 2. Проверяем ручной словарь
    if norm in MANUAL_FORMS:
        return f"{prep} {MANUAL_FORMS[norm]['предл']}"
    
    # 3. Пробуем pymorphy2
    if MORPH_AVAILABLE:
        declined = _decline_with_morph(country, "loct")
        if declined:
            return f"{prep} {declined}"
    
    # 4. Fallback
    return f"{prep} {country}"


def route_text(departure: str, destination: str) -> str:
    """
    Формирование текста маршрута.
    
    Примеры:
        ("Москва", "Турция") -> "из Москвы в Турцию"
        ("Нижний Новгород", "ОАЭ") -> "из Нижнего Новгорода в ОАЭ"
    """
    from_part = from_city(departure)
    to_part = to_country(destination)
    return f"{from_part} {to_part}"


# ==================== ШАГ 17.1: PREFERRED DEPARTURES ====================

# Приоритетные хабы (порядок важен)
# Включаем разные варианты написания для совместимости с DEPARTURES
PREFERRED_DEPARTURE_HUBS = [
    "москва",
    "санкт-петербург", "с.петербург",  # Оба варианта
    "екатеринбург",
    "новосибирск",
    "казань",
    "краснодар",
    "самара",
    "уфа",
    "красноярск",
    "пермь",
    "ростов-на-дону", "ростов",
]


def get_preferred_departures(
    departures_cache: dict[str, int],
    exclude_city: Optional[str] = None,
    limit: int = 5
) -> list[str]:
    """
    Возвращает список предпочтительных городов вылета.
    
    Алгоритм:
    1. Берём пересечение PREFERRED_DEPARTURE_HUBS с реальным кэшем DEPARTURES
    2. Исключаем exclude_city (текущий город вылета пользователя)
    3. Если меньше limit — дозаполняем алфавитно из оставшихся
    4. Возвращаем не более limit городов
    
    Args:
        departures_cache: Словарь DEPARTURES из tourvisor_constants
        exclude_city: Город для исключения (текущий город пользователя)
        limit: Максимальное количество городов (default 5)
    
    Returns:
        Список названий городов (Title Case), не более limit
    """
    result = []
    seen_ids = set()  # Для исключения дубликатов (мск/москва имеют один id)
    exclude_lower = (exclude_city or "").lower()
    
    # 1. Сначала добавляем хабы в порядке приоритета
    for hub in PREFERRED_DEPARTURE_HUBS:
        if hub in departures_cache:
            hub_id = departures_cache[hub]
            if hub_id not in seen_ids and hub != exclude_lower:
                # Выбираем каноническое название (более длинное/полное)
                canonical = hub.title()
                # Специальные случаи для красивого отображения
                if hub == "с.петербург":
                    canonical = "Санкт-Петербург"
                elif hub == "н.новгород":
                    canonical = "Нижний Новгород"
                elif hub == "ростов":
                    canonical = "Ростов-на-Дону"
                
                result.append(canonical)
                seen_ids.add(hub_id)
                
                if len(result) >= limit:
                    return result
    
    # 2. Если меньше limit — дозаполняем алфавитно
    if len(result) < limit:
        # Собираем все уникальные города
        all_cities = {}
        for name, city_id in departures_cache.items():
            if not isinstance(name, str):
                continue
            if city_id in seen_ids:
                continue
            if name == exclude_lower:
                continue
            # Берём более длинное название для каждого id
            if city_id not in all_cities or len(name) > len(all_cities[city_id]):
                all_cities[city_id] = name
        
        # Сортируем алфавитно и добавляем недостающие
        sorted_cities = sorted(all_cities.values())
        for city in sorted_cities:
            city_id = departures_cache.get(city)
            if city_id and city_id not in seen_ids:
                result.append(city.title())
                seen_ids.add(city_id)
                if len(result) >= limit:
                    break
    
    return result[:limit]

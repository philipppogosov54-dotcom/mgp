"""
Slot Extractor для ИИ-ассистента МГП.

Извлекает параметры тура (слоты) из текста пользователя.

Методы извлечения:
1. Regex — быстрое извлечение для очевидных паттернов
2. LLM — для сложных случаев и подтверждения
"""
from __future__ import annotations

import re
import logging
from datetime import date, timedelta
from typing import Optional, Any

from app.agent.state_machine import TourSlots

# Настройка логгера
logger = logging.getLogger(__name__)


# ==================== REGEX ПАТТЕРНЫ ====================

# Страны (основные направления)
COUNTRIES_PATTERN = re.compile(
    r'\b(турци[юяей]|египе?т[ае]?|тайланд[ае]?|таиланд[ае]?|оаэ|эмират[ыа]?|'
    r'мальдив[ыа]?|кипр[ае]?|грец[ияю]|испани[юяей]|итали[юяей]|'
    r'черногори[юяей]|тунис[ае]?|доминикан[ауы]?|куб[ауе]?|вьетнам[ае]?|'
    r'шри[- ]?ланк[ауе]?|индонези[юяей]|бали|сейшел[ыа]?|маврики[йя]?|'
    r'абхази[юяей]|грузи[юяей]|армени[юяей]|узбекистан[ае]?)\b',
    re.IGNORECASE
)

# Нормализация названий стран
COUNTRY_NORMALIZE = {
    "турцию": "Турция", "турции": "Турция", "турция": "Турция", "турцией": "Турция",
    "египет": "Египет", "египта": "Египет", "египте": "Египет",
    "тайланд": "Таиланд", "тайланда": "Таиланд", "тайланде": "Таиланд",
    "таиланд": "Таиланд", "таиланда": "Таиланд", "таиланде": "Таиланд",
    "оаэ": "ОАЭ", "эмираты": "ОАЭ", "эмирата": "ОАЭ",
    "мальдивы": "Мальдивы", "мальдива": "Мальдивы",
    "кипр": "Кипр", "кипра": "Кипр", "кипре": "Кипр",
    "грецию": "Греция", "греция": "Греция", "греции": "Греция",
    "испанию": "Испания", "испания": "Испания", "испании": "Испания",
    "италию": "Италия", "италия": "Италия", "италии": "Италия",
    "черногорию": "Черногория", "черногория": "Черногория",
    "тунис": "Тунис", "туниса": "Тунис", "тунисе": "Тунис",
    "доминикану": "Доминикана", "доминикана": "Доминикана",
    "кубу": "Куба", "куба": "Куба", "кубе": "Куба",
    "вьетнам": "Вьетнам", "вьетнама": "Вьетнам",
    "шри-ланку": "Шри-Ланка", "шри ланку": "Шри-Ланка", "шриланку": "Шри-Ланка",
    "шри-ланка": "Шри-Ланка", "шри ланка": "Шри-Ланка", "шриланка": "Шри-Ланка",
    "индонезию": "Индонезия", "индонезия": "Индонезия", "бали": "Индонезия",
    "сейшелы": "Сейшелы", "сейшела": "Сейшелы",
    "маврикий": "Маврикий", "маврикия": "Маврикий",
    "абхазию": "Абхазия", "абхазия": "Абхазия",
    "грузию": "Грузия", "грузия": "Грузия",
    "армению": "Армения", "армения": "Армения",
    "узбекистан": "Узбекистан", "узбекистана": "Узбекистан",
}

# Города вылета
DEPARTURE_CITIES_PATTERN = re.compile(
    r'\b(?:из\s+)?(москв[ыа]?|питер[ае]?|спб|санкт[- ]?петербург[ае]?|'
    r'казан[ьи]|сочи|екатеринбург[ае]?|екб|новосибирск[ае]?|'
    r'краснодар[ае]?|ростов[ае]?|самар[ыа]?|уф[ыа]?|нижн[ийего]+\s*новгород[ае]?|'
    r'воронеж[ае]?|пермь|красноярск[ае]?|минск[ае]?)\b',
    re.IGNORECASE
)

CITY_NORMALIZE = {
    "москва": "Москва", "москвы": "Москва",
    "питер": "Санкт-Петербург", "питера": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "санкт-петербург": "Санкт-Петербург", "санкт петербург": "Санкт-Петербург",
    "санкт-петербурга": "Санкт-Петербург", "санкт петербурга": "Санкт-Петербург",
    "казань": "Казань", "казани": "Казань",
    "сочи": "Сочи (Адлер)",
    "екатеринбург": "Екатеринбург", "екатеринбурга": "Екатеринбург", "екб": "Екатеринбург",
    "новосибирск": "Новосибирск", "новосибирска": "Новосибирск",
    "краснодар": "Краснодар", "краснодара": "Краснодар",
    "ростов": "Ростов-на-Дону", "ростова": "Ростов-на-Дону",
    "самара": "Самара", "самары": "Самара",
    "уфа": "Уфа", "уфы": "Уфа",
    "нижний новгород": "Нижний Новгород", "нижнего новгорода": "Нижний Новгород",
    "воронеж": "Воронеж", "воронежа": "Воронеж",
    "пермь": "Пермь",
    "красноярск": "Красноярск", "красноярска": "Красноярск",
    "минск": "Минск", "минска": "Минск",
}

# Даты
DATE_PATTERNS = {
    # "15 февраля", "1 марта"
    "day_month": re.compile(
        r'(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        re.IGNORECASE
    ),
    # "с 15 по 22 февраля"
    "date_range": re.compile(
        r'с\s*(\d{1,2})\s*(?:по|до|-)\s*(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        re.IGNORECASE
    ),
    # "15.02", "15.02.2026"
    "numeric_date": re.compile(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?'),
    # "в начале марта", "в конце апреля"
    "month_part": re.compile(
        r'(?:в\s+)?(начал[ое]|середин[ае]|конц[ае])\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        re.IGNORECASE
    ),
    # "майские праздники"
    "holidays": re.compile(r'майск(?:ие|их)\s*(?:праздник|выходн)?', re.IGNORECASE),
    # "новый год", "новогодние"
    "new_year": re.compile(r'нов(?:ый|ого|ому)\s*год[ау]?|новогодн', re.IGNORECASE),
    # "на следующей неделе", "через неделю"
    "relative": re.compile(r'(?:на\s*)?следующ(?:ей|ую)\s*недел[ию]|через\s*недел[юи]', re.IGNORECASE),
    # "завтра", "послезавтра"
    "tomorrow": re.compile(r'завтра|послезавтра', re.IGNORECASE),
}

MONTH_NAMES = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Ночи
NIGHTS_PATTERN = re.compile(
    r'(\d{1,2})\s*(?:ноч[ьеиейям]|дн[яейи]|суток)',
    re.IGNORECASE
)

# Взрослые и дети
ADULTS_PATTERN = re.compile(
    r'(\d)\s*(?:взросл[ыхойаяую]|человек[аи]?|чел\.?|персон[ыа]?)',
    re.IGNORECASE
)

PAX_PATTERNS = {
    # "вдвоём", "вчетвером"
    "together": re.compile(r'вдво[её]м|втро[её]м|вчетвером|впятером', re.IGNORECASE),
    # "2+1" — взрослые + дети
    "plus_notation": re.compile(r'(\d)\s*\+\s*(\d)'),
    # "2 взрослых и 1 ребёнок"
    "adults_and_children": re.compile(
        r'(\d)\s*взросл[ыхойаяую]?\s*(?:и|плюс|\+)?\s*(\d)\s*(?:реб[её]нок|дет[ьеиейям])',
        re.IGNORECASE
    ),
}

TOGETHER_MAP = {
    "вдвоём": 2, "вдвоем": 2,
    "втроём": 3, "втроем": 3,
    "вчетвером": 4,
    "впятером": 5,
}

# Возраст детей
CHILD_AGE_PATTERN = re.compile(
    r'(?:ребёнок|ребенок|дети|детей|дет[ьи])\s*[:\-]?\s*(?:возраст[ае]?)?\s*(\d{1,2})\s*(?:и\s*(\d{1,2}))?\s*(?:лет|год[ав]?)?',
    re.IGNORECASE
)

# Возраст детей в скобках: "(5 лет)", "(5, 8, 12 лет)", "(5 и 8 лет)"
CHILD_AGE_BRACKETS = re.compile(r'\((\d{1,2})(?:\s*,\s*(\d{1,2}))?(?:\s*,\s*(\d{1,2}))?\s*(?:лет|год[ав]?)?\)')
CHILD_AGE_LIST = re.compile(r'\(([0-9,\s]+)\s*(?:лет|год[ав]?)?\)')

# Звёздность
STARS_PATTERN = re.compile(r'(\d)\s*(?:звёзд|звезд[ыа]?|★|\*)', re.IGNORECASE)

# Питание
FOOD_PATTERNS = {
    "AI": re.compile(r'\bвсё\s*включено\b|\bвсе\s*включено\b|\bол\s*инклюзив\b|\ball\s*inclusive\b|\bai\b', re.IGNORECASE),
    "UAI": re.compile(r'\bультра\s*(?:всё|все)\s*включено\b|\buai\b|\bultra\s*all\b', re.IGNORECASE),
    "HB": re.compile(r'\bполупансион\b|\bhalf\s*board\b|\bhb\b', re.IGNORECASE),
    "BB": re.compile(r'\bзавтрак[иам]?\b|\bbreakfast\b|\bbb\b', re.IGNORECASE),
    "FB": re.compile(r'\bполный\s*пансион\b|\bfull\s*board\b|\bfb\b', re.IGNORECASE),
}

# Горящие туры
HOT_TOUR_PATTERN = re.compile(r'горящ(?:ий|ие|ую|его)\s*(?:тур|путёвк|предложен)', re.IGNORECASE)

# ==================== ОТЕЛИ (раздел 2.2 ТЗ) ====================
# Если указан отель — авто-заполняем stars и не спрашиваем!

# Популярные отели (название -> звёздность)
POPULAR_HOTELS = {
    # Турция
    "rixos": 5, "rixos premium": 5, "rixos sungate": 5,
    "titanic": 5, "titanic deluxe": 5, "titanic mardan": 5,
    "regnum carya": 5, "regnum": 5,
    "calista": 5, "calista luxury": 5,
    "maxx royal": 5, "maxx royal kemer": 5, "maxx royal belek": 5,
    "gloria serenity": 5, "gloria verde": 5, "gloria golf": 5,
    "voyage belek": 5, "voyage sorgun": 5,
    "delphin imperial": 5, "delphin be grand": 5,
    "limak atlantis": 5, "limak lara": 5,
    "cornelia diamond": 5, "cornelia": 5,
    "susesi": 5, "susesi luxury": 5,
    "ela quality": 5, "ela": 5,
    "ic hotels": 5, "ic green palace": 5,
    "adalya elite": 5,
    "kaya palazzo": 5,
    "nirvana cosmopolitan": 5,
    "barut": 5, "barut lara": 5, "barut hemera": 5,
    "club marco polo": 4,
    "paloma oceana": 5,
    "orange county": 5,
    "crystal waterworld": 5, "crystal sunset": 5,
    "royal wings": 5,
    "royal holiday palace": 5,
    "akra": 5, "akra barut": 5,
    # Египет
    "albatros": 5, "albatros palace": 5,
    "sunrise": 4, "sunrise royal": 5,
    "steigenberger": 5, "steigenberger aldau": 5,
    "jaz": 4, "jaz aquamarine": 5,
    "coral sea": 4, "coral sea sensatori": 5,
    "cleopatra luxury": 5,
    "siva": 4,
    "hilton": 5, "hilton hurghada": 5,
    "marriott": 5,
    "baron": 4, "baron palace": 5,
    # ОАЭ
    "atlantis": 5, "atlantis the palm": 5,
    "burj al arab": 5,
    "jumeirah": 5,
    "sofitel": 5,
    "fairmont": 5,
    "waldorf astoria": 5,
    "w dubai": 5,
    "one&only": 5,
    "armani": 5,
    "palazzo versace": 5,
    # Мальдивы
    "soneva": 5, "soneva fushi": 5,
    "velaa": 5,
    "cheval blanc": 5,
    "st regis": 5,
    "anantara": 5,
    "como": 5,
    "niyama": 5,
    "baros": 5,
    "gili lankanfushi": 5,
}

# Regex для извлечения названия отеля
HOTEL_NAME_PATTERN = re.compile(
    r'(?:отел[ьеи]\s+|hotel\s+)?([a-zA-Zа-яА-ЯёЁ][a-zA-Zа-яА-ЯёЁ0-9\s&\'-]{2,30}?)(?:\s+(?:resort|hotel|palace|beach|premium|luxury|deluxe|club))?',
    re.IGNORECASE
)


# ==================== ОСНОВНОЙ ЭКСТРАКТОР ====================

class SlotExtractor:
    """
    Извлекает слоты из текста пользователя.
    
    Использует комбинацию regex и контекста для точного извлечения.
    """
    
    def __init__(self):
        self._today = date.today()
    
    def extract_all(
        self, 
        text: str, 
        current_slots: TourSlots,
        last_question_type: Optional[str] = None
    ) -> TourSlots:
        """
        Извлекает все слоты из текста.
        
        КРИТИЧНО: Контекстный парсинг!
        Если мы спрашивали про город, "Москва" = city_from.
        
        Args:
            text: Текст пользователя
            current_slots: Текущие заполненные слоты
            last_question_type: Тип последнего вопроса (для контекста)
            
        Returns:
            Обновлённые слоты
        """
        text_lower = text.lower().strip()
        
        print(f"\n🔍 DEBUG SlotExtractor.extract_all():")
        print(f"   text: '{text}'")
        print(f"   last_question_type: {last_question_type}")
        print(f"   current country_to: {current_slots.country_to}")
        print(f"   current city_from: {current_slots.city_from}")
        
        # ==================== КОНТЕКСТНЫЙ ПАРСИНГ ====================
        
        # 1. Контекстный парсинг чисел
        if text_lower.isdigit():
            num = int(text_lower)
            if last_question_type == "nights" and 1 <= num <= 30:
                current_slots.nights = num
                print(f"   ✅ Context: {num} → nights")
                return current_slots
            elif last_question_type == "adults" and 1 <= num <= 10:
                current_slots.adults = num
                print(f"   ✅ Context: {num} → adults")
                return current_slots
            elif last_question_type == "stars" and 3 <= num <= 5:
                current_slots.stars = num
                print(f"   ✅ Context: {num} → stars")
                return current_slots
        
        # 2. КРИТИЧНО: Контекстный парсинг города вылета
        #    Если мы спрашивали про город, любой ответ = город
        if last_question_type == "city_from":
            city = self._try_extract_city_from_text(text_lower)
            if city:
                current_slots.city_from = city
                print(f"   ✅ Context: '{text}' → city_from='{city}'")
                # Продолжаем извлекать другие слоты
            else:
                # Даже если не распознали как город — может это город без "из"
                # Пробуем распознать как просто название
                for city_name, normalized in CITY_NORMALIZE.items():
                    if city_name in text_lower:
                        current_slots.city_from = normalized
                        print(f"   ✅ Context (fuzzy): '{city_name}' → city_from='{normalized}'")
                        break
        
        # 3. Контекстный парсинг страны
        if last_question_type == "country_to" and not current_slots.country_to:
            # Пользователь отвечает на вопрос о стране
            for country_key, normalized in COUNTRY_NORMALIZE.items():
                if country_key in text_lower:
                    current_slots.country_to = normalized
                    print(f"   ✅ Context: '{country_key}' → country_to='{normalized}'")
                    break
        
        # ==================== СТАНДАРТНОЕ ИЗВЛЕЧЕНИЕ ====================
        # Извлекаем каждый тип слота
        self._extract_country(text_lower, current_slots)
        self._extract_city(text_lower, current_slots)
        self._extract_date(text, current_slots)  # Оригинальный текст для дат
        self._extract_nights(text_lower, current_slots)
        self._extract_pax(text_lower, current_slots)
        self._extract_children(text, current_slots)
        
        # РАЗДЕЛ 2.2 ТЗ: Извлечение отеля с авто-заполнением звёзд
        self._extract_hotel(text, current_slots)
        self._extract_stars(text_lower, current_slots)
        self._extract_food(text_lower, current_slots)
        self._check_hot_tour(text_lower, current_slots)
        
        print(f"   Result: country={current_slots.country_to}, city={current_slots.city_from}")
        
        return current_slots
    
    def _try_extract_city_from_text(self, text: str) -> Optional[str]:
        """
        Пробует извлечь город из текста (контекстный парсинг).
        
        Работает когда пользователь просто отвечает "Москва" на вопрос о городе.
        """
        text = text.lower().strip()
        
        # Убираем префиксы
        for prefix in ["из ", "с ", "от ", "вылет из "]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        # Ищем в словаре
        if text in CITY_NORMALIZE:
            return CITY_NORMALIZE[text]
        
        # Пробуем частичное совпадение
        for city_key, normalized in CITY_NORMALIZE.items():
            if city_key in text or text in city_key:
                return normalized
        
        return None
    
    def _extract_country(self, text: str, slots: TourSlots) -> None:
        """Извлечение страны."""
        match = COUNTRIES_PATTERN.search(text)
        if match:
            raw = match.group(1).lower()
            normalized = COUNTRY_NORMALIZE.get(raw)
            if normalized:
                slots.country_to = normalized
                logger.info(f"   🌍 Страна: {normalized}")
    
    def _extract_city(self, text: str, slots: TourSlots) -> None:
        """Извлечение города вылета."""
        match = DEPARTURE_CITIES_PATTERN.search(text)
        if match:
            raw = match.group(1).lower().replace("-", " ").replace("  ", " ").strip()
            # Убираем "из "
            if raw.startswith("из "):
                raw = raw[3:]
            
            normalized = CITY_NORMALIZE.get(raw)
            if normalized:
                slots.city_from = normalized
                logger.info(f"   ✈️ Город вылета: {normalized}")
    
    def _extract_date(self, text: str, slots: TourSlots) -> None:
        """Извлечение даты."""
        text_lower = text.lower()
        
        # Горящий тур = завтра
        if HOT_TOUR_PATTERN.search(text_lower):
            slots.date_start = self._today + timedelta(days=1)
            logger.info(f"   🔥 Горящий тур → дата: завтра ({slots.date_start})")
            return
        
        # "завтра"
        if "завтра" in text_lower:
            slots.date_start = self._today + timedelta(days=1)
            logger.info(f"   📅 Дата: завтра ({slots.date_start})")
            return
        
        # "послезавтра"
        if "послезавтра" in text_lower:
            slots.date_start = self._today + timedelta(days=2)
            logger.info(f"   📅 Дата: послезавтра ({slots.date_start})")
            return
        
        # "майские праздники"
        match = DATE_PATTERNS["holidays"].search(text_lower)
        if match:
            year = self._today.year
            may_start = date(year, 5, 1)
            if may_start < self._today:
                may_start = date(year + 1, 5, 1)
            slots.date_start = may_start
            logger.info(f"   📅 Майские праздники → {slots.date_start}")
            return
        
        # "новый год"
        match = DATE_PATTERNS["new_year"].search(text_lower)
        if match:
            year = self._today.year
            new_year = date(year, 12, 28)
            if new_year < self._today:
                new_year = date(year + 1, 12, 28)
            slots.date_start = new_year
            logger.info(f"   📅 Новый год → {slots.date_start}")
            return
        
        # Диапазон дат: "с 15 по 22 февраля"
        match = DATE_PATTERNS["date_range"].search(text_lower)
        if match:
            day_from = int(match.group(1))
            day_to = int(match.group(2))
            month = MONTH_NAMES.get(match.group(3).lower())
            if month:
                year = self._today.year
                if month < self._today.month or (month == self._today.month and day_from < self._today.day):
                    year += 1
                try:
                    slots.date_start = date(year, month, day_from)
                    # Вычисляем ночи
                    slots.nights = day_to - day_from
                    logger.info(f"   📅 Диапазон: {slots.date_start} - {day_to}.{month} ({slots.nights} ночей)")
                except ValueError:
                    pass
            return
        
        # "15 февраля"
        match = DATE_PATTERNS["day_month"].search(text_lower)
        if match:
            day = int(match.group(1))
            month = MONTH_NAMES.get(match.group(2).lower())
            if month:
                year = self._today.year
                if month < self._today.month or (month == self._today.month and day < self._today.day):
                    year += 1
                try:
                    slots.date_start = date(year, month, day)
                    logger.info(f"   📅 Дата: {slots.date_start}")
                except ValueError:
                    pass
            return
        
        # "15.02" или "15.02.2026"
        match = DATE_PATTERNS["numeric_date"].search(text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else self._today.year
            if year < 100:
                year += 2000
            try:
                slots.date_start = date(year, month, day)
                logger.info(f"   📅 Дата (число): {slots.date_start}")
            except ValueError:
                pass
            return
        
        # "в начале марта"
        match = DATE_PATTERNS["month_part"].search(text_lower)
        if match:
            part = match.group(1).lower()
            month = MONTH_NAMES.get(match.group(2).lower())
            if month:
                year = self._today.year
                if month < self._today.month:
                    year += 1
                
                if "начал" in part:
                    day = 1
                elif "середин" in part:
                    day = 15
                else:  # конец
                    day = 25
                
                try:
                    slots.date_start = date(year, month, day)
                    logger.info(f"   📅 В {part} месяца: {slots.date_start}")
                except ValueError:
                    pass
    
    def _extract_nights(self, text: str, slots: TourSlots) -> None:
        """Извлечение количества ночей."""
        match = NIGHTS_PATTERN.search(text)
        if match:
            nights = int(match.group(1))
            if 1 <= nights <= 30:
                slots.nights = nights
                logger.info(f"   🌙 Ночей: {nights}")
    
    def _extract_pax(self, text: str, slots: TourSlots) -> None:
        """Извлечение состава группы (взрослые)."""
        # "вдвоём", "втроём"
        for word, count in TOGETHER_MAP.items():
            if word in text:
                slots.adults = count
                logger.info(f"   👥 Взрослых ({word}): {count}")
                return
        
        # "2+1" — 2 взрослых + 1 ребёнок
        match = PAX_PATTERNS["plus_notation"].search(text)
        if match:
            adults = int(match.group(1))
            children_count = int(match.group(2))
            slots.adults = adults
            # Детей запоминаем, но возраст нужно уточнить
            if children_count > 0 and not slots.children_ages:
                # Placeholder — нужен возраст
                pass
            logger.info(f"   👥 {adults}+{children_count}")
            return
        
        # "2 взрослых и 1 ребёнок"
        match = PAX_PATTERNS["adults_and_children"].search(text)
        if match:
            adults = int(match.group(1))
            children_count = int(match.group(2))
            slots.adults = adults
            logger.info(f"   👥 {adults} взр + {children_count} дет")
            return
        
        # "2 взрослых"
        match = ADULTS_PATTERN.search(text)
        if match:
            adults = int(match.group(1))
            if 1 <= adults <= 10:
                slots.adults = adults
                logger.info(f"   👥 Взрослых: {adults}")
    
    def _extract_children(self, text: str, slots: TourSlots) -> None:
        """Извлечение возраста детей."""
        text_lower = text.lower()
        
        # "(5, 8, 12 лет)" — список возрастов в скобках
        match = CHILD_AGE_LIST.search(text)
        if match:
            ages_str = match.group(1)
            # Парсим числа из строки "5, 8, 12"
            ages = re.findall(r'\d+', ages_str)
            for age_str in ages:
                age = int(age_str)
                if 0 <= age <= 17 and age not in slots.children_ages:
                    slots.children_ages.append(age)
                    print(f"   👶 Ребёнок (список): {age} лет")
                    logger.info(f"   👶 Ребёнок: {age} лет")
            if slots.children_ages:
                return
        
        # "ребёнок 7 лет", "дети 5 и 10 лет"
        match = CHILD_AGE_PATTERN.search(text_lower)
        if match:
            age1 = int(match.group(1))
            if 0 <= age1 <= 17:
                if age1 not in slots.children_ages:
                    slots.children_ages.append(age1)
                print(f"   👶 Ребёнок: {age1} лет")
                logger.info(f"   👶 Ребёнок: {age1} лет")
            
            if match.group(2):
                age2 = int(match.group(2))
                if 0 <= age2 <= 17 and age2 not in slots.children_ages:
                    slots.children_ages.append(age2)
                    print(f"   👶 Ребёнок: {age2} лет")
                    logger.info(f"   👶 Ребёнок: {age2} лет")
            return
        
        # "(7 лет)" — одиночный возраст в скобках
        match = CHILD_AGE_BRACKETS.search(text)
        if match:
            for i in range(1, 4):  # До 3 возрастов
                if match.group(i):
                    age = int(match.group(i))
                    if 0 <= age <= 17 and age not in slots.children_ages:
                        slots.children_ages.append(age)
                        print(f"   👶 Ребёнок (скобки): {age} лет")
                        logger.info(f"   👶 Ребёнок: {age} лет")
    
    def _extract_stars(self, text: str, slots: TourSlots) -> None:
        """Извлечение звёздности."""
        match = STARS_PATTERN.search(text)
        if match:
            stars = int(match.group(1))
            if 3 <= stars <= 5:
                slots.stars = stars
                logger.info(f"   ⭐ Звёзд: {stars}")
    
    def _extract_food(self, text: str, slots: TourSlots) -> None:
        """Извлечение типа питания."""
        # UAI должен проверяться первым (более специфичный)
        for food_type, pattern in FOOD_PATTERNS.items():
            if pattern.search(text):
                slots.food_type = food_type
                logger.info(f"   🍽️ Питание: {food_type}")
                return
    
    def _check_hot_tour(self, text: str, slots: TourSlots) -> None:
        """Проверка на горящий тур."""
        if HOT_TOUR_PATTERN.search(text):
            # Для горящего тура: дата = завтра (если не указана)
            if not slots.date_start:
                slots.date_start = self._today + timedelta(days=1)
            # НЕ ставим дефолты для adults и nights!
            logger.info(f"   🔥 Горящий тур")
    
    def _extract_hotel(self, text: str, slots: TourSlots) -> None:
        """
        Извлечение названия отеля (раздел 2.2 ТЗ).
        
        КРИТИЧНО: Если указан отель — авто-заполняем stars!
        Не спрашиваем звёздность, если отель известен.
        """
        text_lower = text.lower()
        
        # Проверяем, есть ли упоминание отеля
        hotel_keywords = ["отел", "hotel", "резорт", "resort", "в отеле", "отель"]
        has_hotel_keyword = any(kw in text_lower for kw in hotel_keywords)
        
        # Ищем известные отели
        for hotel_name, stars in POPULAR_HOTELS.items():
            if hotel_name.lower() in text_lower:
                slots.hotel_name = hotel_name.title()
                
                # АВТО-ЗАПОЛНЯЕМ ЗВЁЗДНОСТЬ!
                if not slots.stars:
                    slots.stars = stars
                    slots.skip_quality_check = True
                    print(f"   🏨 Отель '{hotel_name}' → stars={stars} (auto-fill)")
                    logger.info(f"   🏨 Отель: {hotel_name} ({stars}★)")
                
                return
        
        # Если есть ключевое слово "отель" — пробуем извлечь название
        if has_hotel_keyword:
            # Паттерн: "отель Rixos Premium" или "в Rixos"
            match = re.search(
                r'(?:отел[ьеи]\s+|hotel\s+|в\s+)([A-Za-zА-Яа-яёЁ][A-Za-zА-Яа-яёЁ0-9\s\'-]{2,25})',
                text,
                re.IGNORECASE
            )
            if match:
                hotel = match.group(1).strip()
                # Убираем общие слова
                stop_words = ["этот", "этом", "какой", "хороший", "лучший", "любой"]
                if hotel.lower() not in stop_words:
                    slots.hotel_name = hotel
                    print(f"   🏨 Отель (regex): '{hotel}'")
                    logger.info(f"   🏨 Отель: {hotel}")
    
    def check_group_escalation(self, slots: TourSlots) -> bool:
        """
        Проверка на эскалацию (раздел 2.2 ТЗ).
        
        Если adults + children > 6 — требуется менеджер.
        
        Returns:
            True если нужна эскалация
        """
        total_pax = (slots.adults or 0) + len(slots.children_ages)
        
        if total_pax > 6:
            print(f"   ⚠️ GROUP ESCALATION: {total_pax} человек > 6")
            logger.warning(f"   ⚠️ Эскалация: группа {total_pax} чел > 6")
            return True
        
        return False


# Глобальный экземпляр
slot_extractor = SlotExtractor()

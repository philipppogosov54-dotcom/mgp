"""Pydantic схемы для ИИ-ассистента МГП."""

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class MealType(str, Enum):
    """Типы питания в отелях."""
    RO = "RO"  # Room Only - без питания
    BB = "BB"  # Bed & Breakfast - завтрак
    HB = "HB"  # Half Board - завтрак и ужин
    FB = "FB"  # Full Board - трёхразовое питание
    AI = "AI"  # All Inclusive - всё включено
    UAI = "UAI"  # Ultra All Inclusive - ультра всё включено


class HotelAmenity(str, Enum):
    """Услуги и удобства отеля."""
    SANDY_BEACH = "sandy_beach"  # Песчаный пляж
    AQUAPARK = "aquapark"  # Аквапарк
    KIDS_CLUB = "kids_club"  # Детский клуб
    SPA = "spa"  # СПА-центр
    GYM = "gym"  # Фитнес-зал
    POOL = "pool"  # Бассейн
    WIFI = "wifi"  # Wi-Fi
    FIRST_LINE = "first_line"  # Первая линия
    ANIMATION = "animation"  # Анимация
    TRANSFER = "transfer"  # Трансфер


class TourFilters(BaseModel):
    """Фильтры для поиска туров."""
    
    hotel_category: Optional[list[int]] = Field(
        default=None,
        description="Категория отеля (звёзды): 1-5"
    )
    meal_type: Optional[list[MealType]] = Field(
        default=None,
        description="Тип питания"
    )
    min_rating: Optional[float] = Field(
        default=None,
        ge=0,
        le=10,
        description="Минимальный рейтинг отеля (0-10)"
    )
    amenities: Optional[list[HotelAmenity]] = Field(
        default=None,
        description="Требуемые услуги отеля"
    )
    max_price: Optional[int] = Field(
        default=None,
        gt=0,
        description="Максимальная цена за тур"
    )

    @field_validator("hotel_category")
    @classmethod
    def validate_hotel_category(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is not None:
            for cat in v:
                if cat < 1 or cat > 5:
                    raise ValueError("Категория отеля должна быть от 1 до 5 звёзд")
        return v


class TourSearchRequest(BaseModel):
    """Запрос на поиск тура."""
    
    # Туристы
    adults: int = Field(
        ge=1,
        le=6,
        description="Количество взрослых (1-6)"
    )
    children_under_2: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Количество детей до 2 лет (младенцы)"
    )
    children_2_to_15: list[int] = Field(
        default_factory=list,
        description="Возрасты детей от 2 до 15 лет"
    )
    
    # Направление (иерархия: Страна -> Регион -> Курорт -> Город -> Отель)
    departure_city: str = Field(
        description="Город вылета"
    )
    destination_country: str = Field(
        description="Страна назначения"
    )
    destination_region: Optional[str] = Field(
        default=None,
        description="Регион назначения"
    )
    destination_resort: Optional[str] = Field(
        default=None,
        description="Курорт назначения"
    )
    destination_city: Optional[str] = Field(
        default=None,
        description="Город назначения"
    )
    hotel_name: Optional[str] = Field(
        default=None,
        description="Название конкретного отеля"
    )
    
    # Даты
    date_from: date = Field(
        description="Дата начала тура"
    )
    date_to: Optional[date] = Field(
        default=None,
        description="Дата окончания тура"
    )
    nights_min: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Минимальное количество ночей"
    )
    nights_max: int = Field(
        default=14,
        ge=1,
        le=30,
        description="Максимальное количество ночей"
    )
    
    # Фильтры
    filters: Optional[TourFilters] = Field(
        default=None,
        description="Дополнительные фильтры"
    )

    @field_validator("children_2_to_15")
    @classmethod
    def validate_children_ages(cls, v: list[int]) -> list[int]:
        for age in v:
            if age < 2 or age > 15:
                raise ValueError("Возраст детей должен быть от 2 до 15 лет")
        if len(v) > 4:
            raise ValueError("Максимум 4 ребёнка в возрасте 2-15 лет")
        return v

    @field_validator("nights_max")
    @classmethod
    def validate_nights_range(cls, v: int, info) -> int:
        nights_min = info.data.get("nights_min", 7)
        if v < nights_min:
            raise ValueError("nights_max должен быть >= nights_min")
        return v


class HotelInfo(BaseModel):
    """Информация об отеле."""
    
    id: int = Field(description="ID отеля в системе")
    name: str = Field(description="Название отеля")
    category: int = Field(ge=1, le=5, description="Категория (звёзды)")
    rating: Optional[float] = Field(default=None, description="Рейтинг отеля")
    country: str = Field(description="Страна")
    region: Optional[str] = Field(default=None, description="Регион")
    resort: Optional[str] = Field(default=None, description="Курорт")
    photo_url: Optional[str] = Field(default=None, description="URL фото отеля")
    amenities: list[HotelAmenity] = Field(default_factory=list, description="Удобства")


class TourOffer(BaseModel):
    """Карточка предложения тура (3-5 на выдачу)."""
    
    id: str = Field(description="Уникальный ID предложения")
    hotel: HotelInfo = Field(description="Информация об отеле")
    
    # Даты и длительность
    departure_date: date = Field(description="Дата вылета")
    return_date: date = Field(description="Дата возвращения")
    nights: int = Field(description="Количество ночей")
    
    # Стоимость
    price: int = Field(description="Цена за весь тур")
    price_per_person: int = Field(description="Цена за человека")
    currency: str = Field(default="RUB", description="Валюта")
    
    # Питание и размещение
    meal_type: MealType = Field(description="Тип питания")
    room_type: str = Field(description="Тип номера")
    
    # Перелёт
    departure_city: str = Field(description="Город вылета")
    flight_included: bool = Field(default=True, description="Перелёт включён")
    
    # Оператор
    operator_name: str = Field(description="Туроператор")
    
    # Ссылка на подробности
    details_url: Optional[str] = Field(default=None, description="Ссылка на детали")


class ChatMessage(BaseModel):
    """Сообщение в чате."""
    
    role: str = Field(
        description="Роль отправителя: user или assistant"
    )
    content: str = Field(
        description="Текст сообщения"
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ["user", "assistant", "system"]:
            raise ValueError("role должен быть 'user', 'assistant' или 'system'")
        return v


class ChatRequest(BaseModel):
    """Запрос к чату с ассистентом."""
    
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Сообщение пользователя"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="ID сессии для продолжения диалога"
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="История сообщений"
    )


class ChatResponse(BaseModel):
    """Ответ ассистента."""
    
    message: str = Field(
        description="Текст ответа ассистента"
    )
    tour_offers: Optional[list[TourOffer]] = Field(
        default=None,
        description="Найденные предложения туров (3-5 карточек)"
    )
    follow_up_questions: Optional[list[str]] = Field(
        default=None,
        description="Уточняющие вопросы"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="ID сессии"
    )


class TourRequest(BaseModel):
    """Заявка на бронирование тура."""
    
    tour_offer_id: str = Field(description="ID выбранного предложения")
    
    # Контактные данные
    customer_name: str = Field(min_length=2, description="ФИО клиента")
    customer_phone: str = Field(description="Телефон клиента")
    customer_email: Optional[str] = Field(default=None, description="Email клиента")
    
    # Дополнительная информация
    comment: Optional[str] = Field(default=None, description="Комментарий к заявке")
    
    # Параметры тура
    search_params: Optional[TourSearchRequest] = Field(
        default=None,
        description="Параметры поиска"
    )


class TourRequestResponse(BaseModel):
    """Ответ на создание заявки."""
    
    request_id: str = Field(description="Номер заявки")
    status: str = Field(description="Статус заявки")
    message: str = Field(description="Сообщение для клиента")

"""
API схемы для ИИ-ассистента МГП.

Модели запросов и ответов для REST API.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from typing import Any


class ChatRequest(BaseModel):
    """
    Запрос к чату с ассистентом.
    
    Attributes:
        message: Текст сообщения пользователя
        conversation_id: ID диалога для продолжения (опционально)
    """
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Сообщение пользователя"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="ID диалога для продолжения беседы"
    )


class ChatResponse(BaseModel):
    """
    Ответ чата с ассистентом.
    
    Attributes:
        reply: Текстовый ответ ассистента
        tour_cards: Карточки туров (3-5 штук), если найдены
        conversation_id: ID диалога для последующих сообщений
    """
    reply: str = Field(
        description="Ответ ассистента"
    )
    tour_cards: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Найденные предложения туров (3-5 карточек) с полными данными для UI"
    )
    conversation_id: str = Field(
        description="ID диалога"
    )


class HealthResponse(BaseModel):
    """Ответ проверки здоровья сервиса."""
    status: str = Field(description="Статус сервиса")
    service: str = Field(description="Название сервиса")
    version: str = Field(description="Версия")


class ErrorResponse(BaseModel):
    """Ответ с ошибкой."""
    error: str = Field(description="Описание ошибки")
    detail: Optional[str] = Field(default=None, description="Детали ошибки")

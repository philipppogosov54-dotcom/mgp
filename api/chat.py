"""Эндпоинт чата с ИИ-ассистентом."""

from fastapi import APIRouter, HTTPException
from models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Обработка сообщения пользователя и генерация ответа ассистента.
    
    Основной эндпоинт для взаимодействия с ИИ-ассистентом МГП.
    """
    # TODO: Интеграция с LangGraph агентом
    return ChatResponse(
        message="Привет! Я ИИ-ассистент МГП. Чем могу помочь с подбором тура?",
        tour_offers=None,
        follow_up_questions=["Куда бы вы хотели поехать?", "На какие даты планируете поездку?"]
    )

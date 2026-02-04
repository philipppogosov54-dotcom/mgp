"""Эндпоинт для заявок на туры."""

from fastapi import APIRouter, HTTPException
from models.schemas import TourRequest, TourRequestResponse

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/", response_model=TourRequestResponse)
async def create_request(request: TourRequest) -> TourRequestResponse:
    """
    Создание заявки на бронирование тура.
    
    После выбора тура пользователем, создается заявка для обработки менеджером.
    """
    # TODO: Интеграция с CRM системой
    return TourRequestResponse(
        request_id="REQ-2026-001",
        status="pending",
        message="Ваша заявка принята! Менеджер свяжется с вами в ближайшее время."
    )


@router.get("/{request_id}", response_model=TourRequestResponse)
async def get_request(request_id: str) -> TourRequestResponse:
    """
    Получение статуса заявки по ID.
    """
    # TODO: Получение данных из БД/CRM
    return TourRequestResponse(
        request_id=request_id,
        status="pending",
        message="Заявка в обработке"
    )

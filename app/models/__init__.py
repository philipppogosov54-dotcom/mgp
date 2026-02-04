"""Pydantic схемы и модели данных."""

from app.models.domain import (
    SearchRequest,
    TourOffer,
    TourFilters,
    HotelDetails,
    SearchResponse,
    FoodType,
    HotelType,
    HotelAmenity,
    Destination,
    Child
)

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ErrorResponse
)

__all__ = [
    # Domain models
    "SearchRequest",
    "TourOffer",
    "TourFilters",
    "HotelDetails",
    "SearchResponse",
    "FoodType",
    "HotelType",
    "HotelAmenity",
    "Destination",
    "Child",
    # API schemas
    "ChatRequest",
    "ChatResponse",
    "HealthResponse",
    "ErrorResponse"
]

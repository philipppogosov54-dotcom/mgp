"""API эндпоинты для ИИ-ассистента МГП."""

from api.chat import router as chat_router
from api.requests import router as requests_router

__all__ = ["chat_router", "requests_router"]

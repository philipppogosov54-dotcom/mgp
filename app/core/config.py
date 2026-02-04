"""Конфигурация приложения через переменные окружения."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки приложения.
    
    Загружаются из переменных окружения или файла .env
    """
    
    # Приложение
    APP_NAME: str = "MGP AI Assistant"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # API сервер
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS (разрешаем все origins для разработки)
    CORS_ORIGINS: list[str] = [
        "http://localhost:5555",
        "http://127.0.0.1:5555",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "*"
    ]
    
    # ==================== PostgreSQL ====================
    # Connection string для PostgreSQL
    # Если пусто - используется MemorySaver (для разработки без БД)
    DATABASE_URL: str = ""
    
    # ==================== Аналитика ====================
    # Сохранять диалоги и статистику в БД
    ENABLE_ANALYTICS: bool = True
    
    # Очистка старых сессий (часы)
    SESSION_CLEANUP_HOURS: int = 24
    
    # Логирование API вызовов в БД
    LOG_API_CALLS: bool = True
    
    # ==================== Tourvisor API ====================
    TOURVISOR_API_KEY: str = ""  # Deprecated: use AUTH_LOGIN/AUTH_PASS
    TOURVISOR_AUTH_LOGIN: str = ""  # Логин для классической авторизации
    TOURVISOR_AUTH_PASS: str = ""   # Пароль для классической авторизации
    TOURVISOR_BASE_URL: str = "http://tourvisor.ru/xml"
    TOURVISOR_TIMEOUT: int = 30  # Таймаут запросов в секундах
    TOURVISOR_MOCK: bool = True  # Mock-режим для тестирования без API
    
    # ==================== YandexGPT API ====================
    YANDEX_FOLDER_ID: str = ""
    YANDEX_API_KEY: str = ""
    YANDEX_MODEL: str = "yandexgpt-lite"
    YANDEX_GPT_ENABLED: bool = False  # Включить YandexGPT (иначе mock)
    
    # ==================== Настройки поиска ====================
    DEFAULT_NIGHTS_MIN: int = 7
    DEFAULT_NIGHTS_MAX: int = 14
    MAX_TOUR_OFFERS: int = 5
    
    # ==================== Admin Panel ====================
    # API ключ для доступа к админ-панели (пустой = без авторизации)
    ADMIN_API_KEY: str = ""
    
    # ==================== Rate Limiting ====================
    # Включить rate limiting
    RATE_LIMIT_ENABLED: bool = True
    # Лимит запросов в минуту для /chat
    RATE_LIMIT_CHAT_PER_MINUTE: int = 30
    # Лимит запросов в минуту для общих endpoints
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 60
    
    # ==================== Sentry (опционально) ====================
    SENTRY_DSN: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    @property
    def use_postgres(self) -> bool:
        """Использовать ли PostgreSQL для session persistence."""
        return bool(self.DATABASE_URL)


@lru_cache
def get_settings() -> Settings:
    """Получение настроек приложения с кэшированием."""
    return Settings()


settings = get_settings()

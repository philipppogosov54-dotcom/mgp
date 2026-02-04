"""
Подключение к PostgreSQL и модели для аналитики диалогов.

LangGraph использует свои таблицы через PostgresSaver (создаются автоматически).
Мы добавляем свои таблицы для аналитики диалогов.

Использование:
    from app.core.database import init_db, get_db, DialogHistory, SessionAnalytics
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean, Float, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

# ==================== DATABASE CONNECTION ====================

# Получаем connection string из окружения
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://mgp_user:mgp_dev_password@localhost:5432/mgp_assistant"
)

# Преобразуем postgresql:// в postgresql+psycopg:// для использования psycopg3
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# Добавляем параметр кодировки UTF-8 если его нет
if DATABASE_URL and "client_encoding" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{separator}client_encoding=utf8"

# Создаем engine с пулом соединений
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,     # Проверка соединения перед использованием
    pool_size=10,           # Размер пула соединений
    max_overflow=20,        # Максимум дополнительных соединений
    pool_timeout=30,        # Таймаут получения соединения из пула
    pool_recycle=1800,      # Переподключение каждые 30 минут
    echo=False              # Не логировать SQL запросы (для production)
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base для моделей
Base = declarative_base()


# ==================== МОДЕЛИ АНАЛИТИКИ ====================

class DialogHistory(Base):
    """
    История диалогов для аналитики.
    
    Сохраняет каждый ход диалога (turn):
    - Сообщение пользователя
    - Ответ ассистента
    - Параметры поиска
    - Найденные туры
    
    Индексы оптимизированы для:
    - Поиска по conversation_id
    - Фильтрации по дате
    - Анализа intent'ов
    """
    __tablename__ = "dialog_history"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(255), nullable=False, comment="Thread ID из LangGraph")
    turn_id = Column(Integer, nullable=False, comment="Номер хода в диалоге (1, 2, 3...)")
    
    # Тексты
    user_text = Column(Text, nullable=False, comment="Сообщение пользователя")
    assistant_text = Column(Text, nullable=False, comment="Ответ ассистента")
    
    # JSON поля для детального анализа
    search_params = Column(JSON, nullable=True, comment="Собранные параметры поиска")
    tour_offers = Column(JSON, nullable=True, comment="Карточки туров (если найдены)")
    missing_params = Column(JSON, nullable=True, comment="Недостающие параметры")
    
    # Метаданные диалога
    intent = Column(String(50), nullable=True, comment="Определенный intent")
    search_mode = Column(String(50), nullable=True, comment="Режим поиска (package/burning/hotel)")
    cascade_stage = Column(Integer, nullable=True, comment="Этап каскада квалификации (1-5)")
    
    # Метрики
    response_time_ms = Column(Float, nullable=True, comment="Время генерации ответа в мс")
    tours_found_count = Column(Integer, default=0, comment="Количество найденных туров")
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="Время создания")
    
    # Составной индекс для быстрого поиска по сессии
    __table_args__ = (
        Index('idx_dialog_conversation_turn', 'conversation_id', 'turn_id'),
        Index('idx_dialog_created_at', 'created_at'),
        Index('idx_dialog_intent', 'intent'),
    )
    
    def __repr__(self):
        return f"<DialogHistory(id={self.id}, conv={self.conversation_id[:8]}..., turn={self.turn_id})>"


class SessionAnalytics(Base):
    """
    Аналитика сессий пользователей.
    
    Один record = одна сессия (conversation_id).
    Используется для:
    - Отслеживания конверсии
    - Анализа поведения пользователей
    - Выявления проблемных сценариев
    """
    __tablename__ = "session_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(255), unique=True, nullable=False, comment="Thread ID")
    user_id = Column(String(255), nullable=True, comment="User ID (если передан в заголовке)")
    
    # Статистика сообщений
    message_count = Column(Integer, default=0, comment="Общее количество сообщений")
    user_messages = Column(Integer, default=0, comment="Сообщений от пользователя")
    bot_messages = Column(Integer, default=0, comment="Сообщений от бота")
    
    # Статистика поиска
    tour_searches = Column(Integer, default=0, comment="Количество поисков туров")
    tours_found = Column(Integer, default=0, comment="Всего найдено туров")
    tours_shown = Column(Integer, default=0, comment="Показано пользователю")
    
    # Собранные параметры (для анализа воронки)
    collected_params = Column(JSON, nullable=True, comment="Какие параметры собраны")
    final_search_params = Column(JSON, nullable=True, comment="Финальные параметры поиска")
    
    # Статусы и флаги
    status = Column(String(50), default="active", comment="active/completed/abandoned/escalated")
    has_booking_intent = Column(Boolean, default=False, comment="Была ли попытка бронирования")
    was_escalated = Column(Boolean, default=False, comment="Была ли эскалация на менеджера")
    is_group_request = Column(Boolean, default=False, comment="Групповой запрос (>6 человек)")
    
    # Качество диалога
    successful_search = Column(Boolean, default=False, comment="Был ли успешный поиск с результатами")
    reached_booking = Column(Boolean, default=False, comment="Дошел ли до этапа бронирования")
    
    # Источник (для маркетинговой аналитики)
    source = Column(String(100), nullable=True, comment="Источник трафика")
    device_type = Column(String(50), nullable=True, comment="Тип устройства")
    
    # Времена
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True, comment="Время завершения сессии")
    
    # Длительность (вычисляется при завершении)
    duration_seconds = Column(Integer, nullable=True, comment="Длительность сессии в секундах")
    
    # Индексы для аналитики
    __table_args__ = (
        Index('idx_session_status', 'status'),
        Index('idx_session_started', 'started_at'),
        Index('idx_session_user', 'user_id'),
        Index('idx_session_booking', 'has_booking_intent'),
    )
    
    def __repr__(self):
        return f"<SessionAnalytics(id={self.id}, conv={self.conversation_id[:8]}..., msgs={self.message_count})>"


class TestNote(Base):
    """
    Заметки тестировщиков к сессиям.
    
    Позволяет:
    - Добавлять комментарии к конкретным сессиям
    - Помечать сессии как проблемные
    - Связывать баги с конкретными диалогами
    """
    __tablename__ = "test_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(255), nullable=False, comment="Thread ID сессии")
    
    # Автор заметки
    author = Column(String(100), nullable=True, comment="Имя тестировщика")
    
    # Содержимое
    note_type = Column(String(50), default="comment", comment="comment/bug/question/suggestion")
    content = Column(Text, nullable=False, comment="Текст заметки")
    
    # К какому конкретному сообщению относится (опционально)
    turn_id = Column(Integer, nullable=True, comment="К какому ходу диалога относится")
    
    # Приоритет/важность
    priority = Column(String(20), default="normal", comment="low/normal/high/critical")
    
    # Статус обработки
    status = Column(String(50), default="open", comment="open/in_progress/resolved/wont_fix")
    resolution = Column(Text, nullable=True, comment="Как была решена проблема")
    
    # Теги для фильтрации
    tags = Column(JSON, nullable=True, comment="Массив тегов ['ui', 'logic', 'api']")
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_test_note_conversation', 'conversation_id'),
        Index('idx_test_note_type', 'note_type'),
        Index('idx_test_note_status', 'status'),
        Index('idx_test_note_priority', 'priority'),
    )
    
    def __repr__(self):
        return f"<TestNote(id={self.id}, conv={self.conversation_id[:8]}..., type={self.note_type})>"


class APICallLog(Base):
    """
    Логи вызовов внешних API (Tourvisor, YandexGPT).
    
    Используется для:
    - Мониторинга производительности API
    - Отслеживания ошибок
    - Анализа стоимости (для YandexGPT)
    """
    __tablename__ = "api_call_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(255), nullable=True, comment="Thread ID (если в контексте диалога)")
    turn_id = Column(Integer, nullable=True, comment="Номер хода")
    
    # API информация
    api_name = Column(String(50), nullable=False, comment="tourvisor/yandexgpt")
    endpoint = Column(String(255), nullable=False, comment="Endpoint API")
    method = Column(String(10), default="GET", comment="HTTP метод")
    
    # Запрос/ответ (без sensitive данных)
    request_params = Column(JSON, nullable=True, comment="Параметры запроса (sanitized)")
    response_summary = Column(Text, nullable=True, comment="Краткое описание ответа")
    
    # Метрики
    status_code = Column(Integer, nullable=True, comment="HTTP статус код")
    elapsed_ms = Column(Float, nullable=True, comment="Время выполнения в мс")
    result_count = Column(Integer, nullable=True, comment="Количество результатов")
    
    # Ошибки
    error = Column(Text, nullable=True, comment="Текст ошибки (если есть)")
    is_success = Column(Boolean, default=True, comment="Успешный ли вызов")
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_api_call_api_name', 'api_name'),
        Index('idx_api_call_created', 'created_at'),
        Index('idx_api_call_success', 'is_success'),
    )
    
    def __repr__(self):
        return f"<APICallLog(id={self.id}, api={self.api_name}, status={self.status_code})>"


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

def init_db() -> bool:
    """
    Создание всех таблиц в БД.
    
    Вызывается при старте приложения.
    LangGraph создаст свои таблицы автоматически через PostgresSaver.setup().
    
    Returns:
        True если успешно, False если ошибка
    """
    try:
        logger.info("🔨 Создание таблиц в БД...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Таблицы созданы успешно")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        return False


def check_connection() -> bool:
    """
    Проверка подключения к БД.
    
    Returns:
        True если соединение успешно
    """
    from sqlalchemy import text
    
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ PostgreSQL connection OK")
        return True
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        return False


def get_db() -> Generator[Session, None, None]:
    """
    Dependency для получения сессии БД.
    
    Использование в FastAPI:
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager для получения сессии БД.
    
    Использование:
        with get_db_session() as db:
            db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==================== HELPER FUNCTIONS ====================

def get_database_stats() -> dict:
    """
    Получить статистику по БД.
    
    Returns:
        dict со статистикой таблиц
    """
    from sqlalchemy import func, text
    
    with get_db_session() as db:
        try:
            dialogs_count = db.query(func.count(DialogHistory.id)).scalar()
            sessions_count = db.query(func.count(SessionAnalytics.id)).scalar()
            api_calls_count = db.query(func.count(APICallLog.id)).scalar()
            
            # Размер БД (PostgreSQL specific)
            result = db.execute(text(
                "SELECT pg_database_size(current_database())"
            )).scalar()
            db_size_mb = round(result / 1024 / 1024, 2) if result else 0
            
            return {
                "dialogs_count": dialogs_count,
                "sessions_count": sessions_count,
                "api_calls_count": api_calls_count,
                "database_size_mb": db_size_mb
            }
        except Exception as e:
            logger.error(f"Error getting DB stats: {e}")
            return {
                "error": str(e)
            }

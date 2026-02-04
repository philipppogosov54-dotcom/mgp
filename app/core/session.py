"""
Session Persistence для ИИ-ассистента МГП.

Реализует сохранение контекста диалога между HTTP-запросами.

Архитектура:
- MemorySaver (для разработки без БД)
- AsyncPostgresSaver (для продакшена с PostgreSQL)

Thread-based persistence:
- Каждый пользователь имеет уникальный thread_id
- Состояние сохраняется в checkpointer между запросами
- Window Buffer ограничивает историю сообщений

Автоматический выбор:
- Если DATABASE_URL установлен -> AsyncPostgresSaver
- Иначе -> MemorySaver
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Any
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver

# Настройка логгера
logger = logging.getLogger(__name__)


# ==================== CHECKPOINTER CONFIG ====================

# Window Buffer: максимальное количество сообщений в истории
MAX_MESSAGES_HISTORY = 20

# Время жизни сессии (в секундах) - 24 часа
SESSION_TTL_SECONDS = 86400


# ==================== BASE SESSION MANAGER ====================

class BaseSessionManager:
    """
    Базовый класс для менеджеров сессий.
    
    Определяет интерфейс для MemorySaver и PostgresSaver.
    """
    
    def __init__(self):
        self.checkpointer = None
        # Метаданные сессий (время создания, последний запрос)
        self._session_metadata: dict[str, dict[str, Any]] = {}
    
    def get_config(self, thread_id: str) -> dict:
        """
        Создаёт конфигурацию для LangGraph с thread_id.
        
        Args:
            thread_id: Уникальный идентификатор сессии/пользователя
            
        Returns:
            Конфигурация для ainvoke: {"configurable": {"thread_id": "..."}}
        """
        # Обновляем метаданные
        if thread_id not in self._session_metadata:
            self._session_metadata[thread_id] = {
                "created_at": datetime.now(),
                "last_access": datetime.now(),
                "message_count": 0
            }
        else:
            self._session_metadata[thread_id]["last_access"] = datetime.now()
        
        return {
            "configurable": {
                "thread_id": thread_id
            }
        }
    
    def get_checkpointer(self):
        """Возвращает checkpointer для компиляции графа."""
        return self.checkpointer
    
    def get_session_metadata(self, thread_id: str) -> Optional[dict]:
        """Получить метаданные сессии."""
        return self._session_metadata.get(thread_id)
    
    def increment_message_count(self, thread_id: str) -> None:
        """Увеличить счётчик сообщений."""
        if thread_id in self._session_metadata:
            self._session_metadata[thread_id]["message_count"] += 1
    
    def get_active_sessions_count(self) -> int:
        """Количество активных сессий."""
        return len(self._session_metadata)
    
    def cleanup_old_sessions(self) -> int:
        """
        Очистка старых сессий (TTL).
        
        Returns:
            Количество удалённых сессий
        """
        now = datetime.now()
        to_delete = []
        
        for thread_id, meta in self._session_metadata.items():
            age_seconds = (now - meta["last_access"]).total_seconds()
            if age_seconds > SESSION_TTL_SECONDS:
                to_delete.append(thread_id)
        
        for thread_id in to_delete:
            del self._session_metadata[thread_id]
        
        if to_delete:
            logger.info(f"🧹 Очищено {len(to_delete)} старых сессий из метаданных")
        
        return len(to_delete)
    
    async def initialize_async(self):
        """Асинхронная инициализация (переопределяется в ProductionSessionManager)."""
        pass
    
    def close(self):
        """Закрытие ресурсов (переопределяется в ProductionSessionManager)."""
        pass


# ==================== MEMORY SAVER (Development) ====================

class SessionManager(BaseSessionManager):
    """
    Менеджер сессий для LangGraph агента (In-Memory).
    
    Использует MemorySaver для разработки и тестирования.
    Данные теряются при перезапуске сервера.
    """
    
    def __init__(self):
        super().__init__()
        # MemorySaver - хранит состояние в памяти
        self.checkpointer = MemorySaver()
        logger.info("🔒 SessionManager инициализирован (MemorySaver - in-memory)")


# ==================== POSTGRES SAVER (Production) ====================

class ProductionSessionManager(BaseSessionManager):
    """
    Production Session Manager с PostgreSQL.
    
    Использует AsyncPostgresSaver для асинхронного сохранения состояния LangGraph
    в PostgreSQL между запросами и перезапусками сервера.
    
    ВАЖНО: Требует вызова initialize_async() после создания!
    """
    
    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: PostgreSQL connection string
                Формат: postgresql://user:password@host:port/database
        """
        super().__init__()
        self.connection_string = connection_string
        self.pool = None
        self._initialized = False
        
        # Сначала используем MemorySaver, потом заменим на AsyncPostgresSaver
        self.checkpointer = MemorySaver()
        logger.info("🔒 SessionManager создан (ожидает async инициализации)")
    
    async def initialize_async(self):
        """
        Асинхронная инициализация AsyncPostgresSaver.
        
        Должна быть вызвана при старте приложения (в lifespan).
        """
        if self._initialized:
            return
        
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool
            
            # Добавляем client_encoding к connection string если нет
            conn_str = self.connection_string
            if "client_encoding" not in conn_str:
                separator = "&" if "?" in conn_str else "?"
                conn_str = f"{conn_str}{separator}client_encoding=utf8"
            
            # Создаём асинхронный пул соединений
            self.pool = AsyncConnectionPool(
                conn_str,
                min_size=2,
                max_size=10,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                }
            )
            
            # Открываем пул
            await self.pool.open()
            
            # Создаём AsyncPostgresSaver
            self.checkpointer = AsyncPostgresSaver(self.pool)
            
            # Создаём таблицы
            await self.checkpointer.setup()
            
            self._initialized = True
            logger.info("🔒 AsyncPostgresSaver инициализирован успешно")
            
        except ImportError as e:
            logger.error(f"❌ Не удалось импортировать AsyncPostgresSaver: {e}")
            logger.warning("⚠️ Используем MemorySaver")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации AsyncPostgresSaver: {e}")
            logger.warning("⚠️ Используем MemorySaver")
    
    async def close(self):
        """Закрытие пула соединений."""
        if self.pool:
            try:
                await self.pool.close()
                logger.info("🔒 PostgreSQL async pool closed")
            except Exception as e:
                logger.error(f"Error closing pool: {e}")


# ==================== FACTORY ====================

def create_session_manager() -> BaseSessionManager:
    """
    Фабрика для создания правильного SessionManager.
    
    Если DATABASE_URL есть в окружении -> ProductionSessionManager (требует async init)
    Иначе -> MemorySaver (для локальной разработки)
    
    Returns:
        SessionManager или ProductionSessionManager
    """
    database_url = os.getenv("DATABASE_URL", "")
    
    if database_url:
        logger.info(f"🗄️ DATABASE_URL найден, используем PostgreSQL")
        return ProductionSessionManager(database_url)
    else:
        logger.info("💾 DATABASE_URL не задан, используем MemorySaver (development)")
        return SessionManager()


# ==================== WINDOW BUFFER ====================

def apply_window_buffer(messages: list, max_messages: int = MAX_MESSAGES_HISTORY) -> list:
    """
    Window Buffer: ограничивает историю сообщений.
    
    Сохраняет:
    - Последние N сообщений
    - Ключевые параметры (в state.search_params)
    
    Args:
        messages: Полная история сообщений
        max_messages: Максимальное количество сообщений
        
    Returns:
        Обрезанная история
    """
    if len(messages) <= max_messages:
        return messages
    
    # Берём последние N сообщений
    # При этом сохраняем первое сообщение (контекст приветствия)
    first_message = messages[0] if messages else None
    recent_messages = messages[-(max_messages - 1):]
    
    if first_message and first_message not in recent_messages:
        return [first_message] + recent_messages
    
    return recent_messages


# ==================== GLOBAL INSTANCE ====================

# Глобальный экземпляр менеджера сессий
# Автоматически выбирает PostgresSaver или MemorySaver
session_manager = create_session_manager()

"""
ИИ-ассистент МГП — Точка входа FastAPI приложения.

Запуск:
    uvicorn app.main:app --reload

Или:
    python -m app.main

Функции:
- Авто-синхронизация справочников Tourvisor (каждые 24 часа)
- REST API для чата с ИИ-ассистентом
- PostgreSQL для session persistence и аналитики
"""

from contextlib import asynccontextmanager
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.admin import router as admin_router

# Rate Limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    Limiter = None

# Настройка логгера
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальный экземпляр планировщика
scheduler: Optional[AsyncIOScheduler] = None


async def sync_tourvisor_job():
    """
    Фоновая задача синхронизации справочников Tourvisor.
    Запускается каждые 24 часа.
    """
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from scripts.sync_tourvisor_data import sync_dictionaries
        
        logger.info("🔄 [SCHEDULER] Запуск авто-синхронизации справочников...")
        countries, departures = await sync_dictionaries(verbose=False)
        logger.info(f"🔄 [SCHEDULER] Синхронизировано: {countries} стран, {departures} городов")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Ошибка синхронизации: {e}")


async def cleanup_sessions_job():
    """
    Фоновая задача очистки старых сессий.
    Запускается каждые N часов (настраивается в SESSION_CLEANUP_HOURS).
    """
    try:
        from app.services.analytics import analytics_service
        
        count = analytics_service.cleanup_abandoned_sessions(
            hours=settings.SESSION_CLEANUP_HOURS
        )
        if count > 0:
            logger.info(f"🧹 [SCHEDULER] Очищено {count} abandoned сессий")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Ошибка очистки сессий: {e}")


async def initial_sync():
    """
    Начальная синхронизация при старте приложения.
    Выполняется если файл констант отсутствует или устарел.
    """
    from pathlib import Path
    from datetime import datetime, timedelta
    
    constants_file = Path(__file__).parent / "core" / "tourvisor_constants.py"
    
    should_sync = False
    
    if not constants_file.exists():
        logger.info("📋 Файл констант не найден — требуется синхронизация")
        should_sync = True
    else:
        # Проверяем возраст файла (синхронизируем если старше 24 часов)
        try:
            from app.core.tourvisor_constants import LAST_SYNC
            last_sync = datetime.fromisoformat(LAST_SYNC)
            age = datetime.now() - last_sync
            if age > timedelta(hours=24):
                logger.info(f"📋 Константы устарели ({age.total_seconds() / 3600:.1f}ч) — требуется синхронизация")
                should_sync = True
            else:
                logger.info(f"📋 Константы актуальны (возраст: {age.total_seconds() / 3600:.1f}ч)")
        except Exception:
            should_sync = True
    
    if should_sync:
        await sync_tourvisor_job()


def init_database():
    """
    Инициализация PostgreSQL базы данных.
    
    - Проверяет подключение
    - Создаёт таблицы для аналитики
    - LangGraph создаёт свои таблицы автоматически
    """
    if not settings.DATABASE_URL:
        logger.info("💾 DATABASE_URL не задан — используем MemorySaver")
        return False
    
    try:
        from app.core.database import check_connection, init_db
        
        # Проверяем подключение
        if check_connection():
            logger.info("✅ PostgreSQL connection OK")
            
            # Создаём таблицы аналитики
            if init_db():
                logger.info("✅ Analytics tables initialized")
                return True
            else:
                logger.warning("⚠️ Failed to initialize analytics tables")
                return False
        else:
            logger.warning("⚠️ PostgreSQL connection failed — using MemorySaver")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle события приложения.
    
    Startup:
    - Инициализация PostgreSQL (если настроен)
    - Инициализация планировщика задач
    - Начальная синхронизация справочников (если нужно)
    - Запуск периодической синхронизации каждые 24 часа
    - Запуск очистки старых сессий
    
    Shutdown:
    - Остановка планировщика
    - Закрытие соединений с БД
    - Освобождение ресурсов
    """
    global scheduler
    
    # === STARTUP ===
    print("=" * 60)
    print(f"🚀 Запуск {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"📍 Сервер: http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Документация: http://{settings.HOST}:{settings.PORT}/docs")
    print("=" * 60)
    
    # ==================== DATABASE INITIALIZATION ====================
    db_initialized = init_database()
    
    # ==================== SESSION MANAGER ASYNC INIT ====================
    # Инициализируем AsyncPostgresSaver если используем PostgreSQL
    from app.core.session import session_manager
    await session_manager.initialize_async()
    
    # Пересоздаём граф с новым checkpointer
    from app.agent.graph import reinitialize_graph
    reinitialize_graph()
    
    if db_initialized:
        print("✅ PostgreSQL: подключен, таблицы созданы")
        print(f"   📊 Аналитика: {'включена' if settings.ENABLE_ANALYTICS else 'выключена'}")
        print(f"   📝 Логирование API: {'включено' if settings.LOG_API_CALLS else 'выключено'}")
    else:
        print("💾 Режим: In-Memory (MemorySaver)")
        print("   ⚠️ Данные не сохраняются между перезапусками")
    
    # ==================== SCHEDULER ====================
    # Инициализируем планировщик
    scheduler = AsyncIOScheduler()
    
    # Добавляем задачу синхронизации справочников (каждые 24 часа)
    scheduler.add_job(
        sync_tourvisor_job,
        trigger=IntervalTrigger(hours=24),
        id="tourvisor_sync",
        name="Синхронизация справочников Tourvisor",
        replace_existing=True,
        max_instances=1,
    )
    
    # Добавляем задачу очистки сессий (если БД подключена)
    if db_initialized and settings.ENABLE_ANALYTICS:
        scheduler.add_job(
            cleanup_sessions_job,
            trigger=IntervalTrigger(hours=settings.SESSION_CLEANUP_HOURS),
            id="session_cleanup",
            name="Очистка старых сессий",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"📅 [SCHEDULER] Очистка сессий каждые {settings.SESSION_CLEANUP_HOURS}ч")
    
    # Запускаем планировщик
    scheduler.start()
    logger.info("📅 [SCHEDULER] Планировщик запущен")
    
    # Начальная синхронизация (если нужно)
    await initial_sync()
    
    print("=" * 60)
    print("✅ Сервер готов к работе!")
    print("=" * 60)
    
    yield
    
    # === SHUTDOWN ===
    print("\n👋 Остановка сервера...")
    
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("📅 [SCHEDULER] Планировщик остановлен")
    
    # Закрываем соединение с БД
    if settings.DATABASE_URL:
        try:
            from app.core.session import session_manager
            if hasattr(session_manager, 'close'):
                import asyncio
                if asyncio.iscoroutinefunction(session_manager.close):
                    await session_manager.close()
                else:
                    session_manager.close()
                logger.info("🔒 PostgreSQL connection closed")
        except Exception as e:
            logger.warning(f"Error closing DB connection: {e}")
    
    print("✅ Сервер остановлен")


# ==================== RATE LIMITER ====================
# Инициализируем rate limiter если доступен
limiter = None
if SLOWAPI_AVAILABLE and settings.RATE_LIMIT_ENABLED:
    limiter = Limiter(key_func=get_remote_address)
    logger.info("📊 Rate limiting: включен")
else:
    logger.info("📊 Rate limiting: выключен")

# Создание FastAPI приложения
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## ИИ-ассистент туристического агентства МГП

### Возможности:
- 🔍 **Поиск туров** через интеграцию с Tourvisor API
- 🤖 **Интеллектуальный диалог** на базе YandexGPT
- ❓ **FAQ** по визам, оплате, возвратам
- 📝 **Создание заявок** на бронирование
- 📊 **Аналитика** диалогов и сессий

### Бизнес-логика:
- Поддержка групп от 1 до 6 взрослых
- Дети: младенцы (0-2 года) и дети (2-15 лет)
- Автоматический расчёт ночей из дат
- Иерархия: Страна → Регион → Курорт → Город → Отель
- Выдача 3-5 карточек предложений

### Session Persistence:
- PostgreSQL для сохранения сессий между запросами
- Аналитика диалогов для отслеживания конверсии
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Middleware для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все origins для локальной разработки
    allow_credentials=False,  # Отключаем credentials для совместимости с "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting Middleware
if limiter and SLOWAPI_AVAILABLE:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/", tags=["root"])
async def root():
    """Корневой эндпоинт с информацией о сервисе."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "ИИ-ассистент туристического агентства МГП",
        "docs": "/docs",
        "health": "/health",
        "analytics": "/api/v1/analytics/global" if settings.DATABASE_URL else None
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    Проверка состояния сервиса.
    
    Используется для мониторинга и балансировщиков нагрузки.
    """
    health_status = {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if settings.DATABASE_URL else "not_configured",
        "analytics_enabled": settings.ENABLE_ANALYTICS and bool(settings.DATABASE_URL)
    }
    
    # Проверяем реальное подключение к БД
    if settings.DATABASE_URL:
        try:
            from app.core.database import check_connection
            if check_connection():
                health_status["database"] = "connected"
            else:
                health_status["database"] = "disconnected"
                health_status["status"] = "degraded"
        except Exception:
            health_status["database"] = "error"
            health_status["status"] = "degraded"
    
    return health_status


# Подключение API роутеров
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])

# Монтирование статических файлов (фронтенд)
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

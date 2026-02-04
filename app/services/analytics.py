"""
Сервис для сохранения и анализа диалогов.

Работает параллельно с LangGraph PostgresSaver:
- LangGraph сохраняет состояние агента (checkpoints)
- Мы сохраняем диалоги для аналитики и отчетов

Использование:
    from app.services.analytics import analytics_service
    
    # Сохранение хода диалога
    await analytics_service.save_turn(
        conversation_id="abc-123",
        turn_id=1,
        user_text="Хочу в Египет",
        assistant_text="Из какого города вылетаете?"
    )
    
    # Получение статистики
    stats = analytics_service.get_global_stats()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _serialize_for_json(obj: Any) -> Any:
    """
    Рекурсивно конвертирует datetime.date/datetime объекты в ISO строки.
    
    Нужно для сохранения в JSON поля БД (SQLAlchemy).
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()  # "2026-01-24"
    return obj


class AnalyticsService:
    """
    Сервис для работы с аналитикой диалогов.
    
    Асинхронно сохраняет данные в PostgreSQL,
    не блокируя основной поток обработки запросов.
    """
    
    # ==================== SAVING METHODS ====================
    
    @staticmethod
    async def save_turn(
        conversation_id: str,
        turn_id: int,
        user_text: str,
        assistant_text: str,
        search_params: Optional[dict] = None,
        tour_offers: Optional[list] = None,
        missing_params: Optional[list] = None,
        intent: Optional[str] = None,
        search_mode: Optional[str] = None,
        cascade_stage: Optional[int] = None,
        response_time_ms: Optional[float] = None
    ) -> None:
        """
        Сохранение хода диалога в БД (асинхронно).
        
        Args:
            conversation_id: Thread ID сессии
            turn_id: Номер хода в диалоге
            user_text: Сообщение пользователя
            assistant_text: Ответ ассистента
            search_params: Собранные параметры поиска
            tour_offers: Найденные туры (список dict)
            missing_params: Недостающие параметры
            intent: Определенный intent
            search_mode: Режим поиска
            cascade_stage: Этап каскада
            response_time_ms: Время генерации ответа
        """
        # Проверяем что аналитика включена и DATABASE_URL задан
        if not settings.ENABLE_ANALYTICS or not settings.DATABASE_URL:
            return
        
        try:
            # Выполняем DB операции в отдельном thread pool
            await asyncio.to_thread(
                AnalyticsService._save_turn_sync,
                conversation_id=conversation_id,
                turn_id=turn_id,
                user_text=user_text,
                assistant_text=assistant_text,
                search_params=search_params,
                tour_offers=tour_offers,
                missing_params=missing_params,
                intent=intent,
                search_mode=search_mode,
                cascade_stage=cascade_stage,
                response_time_ms=response_time_ms
            )
        except Exception as e:
            logger.error(f"❌ Error saving analytics: {e}")
    
    @staticmethod
    def _save_turn_sync(
        conversation_id: str,
        turn_id: int,
        user_text: str,
        assistant_text: str,
        search_params: Optional[dict],
        tour_offers: Optional[list],
        missing_params: Optional[list],
        intent: Optional[str],
        search_mode: Optional[str],
        cascade_stage: Optional[int],
        response_time_ms: Optional[float]
    ) -> None:
        """Синхронное сохранение (вызывается из asyncio.to_thread)."""
        from app.core.database import SessionLocal, DialogHistory, SessionAnalytics
        
        db = SessionLocal()
        
        try:
            tours_count = len(tour_offers) if tour_offers else 0
            
            # Сериализуем datetime.date объекты для JSON полей
            serialized_params = _serialize_for_json(search_params)
            serialized_offers = _serialize_for_json(tour_offers)
            
            # 1. Сохраняем ход диалога
            dialog = DialogHistory(
                conversation_id=conversation_id,
                turn_id=turn_id,
                user_text=user_text,
                assistant_text=assistant_text,
                search_params=serialized_params,
                tour_offers=serialized_offers,
                missing_params=missing_params,
                intent=intent,
                search_mode=search_mode,
                cascade_stage=cascade_stage,
                response_time_ms=response_time_ms,
                tours_found_count=tours_count,
                created_at=datetime.utcnow()
            )
            db.add(dialog)
            
            # 2. Обновляем или создаем аналитику сессии
            session = db.query(SessionAnalytics).filter_by(
                conversation_id=conversation_id
            ).first()
            
            if session:
                # Обновляем существующую сессию
                session.message_count += 1
                session.user_messages += 1
                session.bot_messages += 1
                session.last_activity = datetime.utcnow()
                
                # Обновляем статистику поиска
                if tours_count > 0:
                    session.tour_searches += 1
                    session.tours_found += tours_count
                    session.tours_shown += min(tours_count, 5)  # Показываем максимум 5
                    session.successful_search = True
                
                # Сохраняем собранные параметры
                if search_params:
                    session.final_search_params = search_params
                    # Считаем какие параметры собраны
                    collected = []
                    if search_params.get("destination_country"):
                        collected.append("country")
                    if search_params.get("departure_city"):
                        collected.append("departure")
                    if search_params.get("date_from"):
                        collected.append("date")
                    if search_params.get("adults"):
                        collected.append("adults")
                    if search_params.get("nights"):
                        collected.append("nights")
                    session.collected_params = collected
                
                # Проверяем бронирование и эскалацию
                if intent == "booking":
                    session.has_booking_intent = True
                    session.reached_booking = True
                if intent == "escalation" or "группа" in assistant_text.lower() or "менеджер" in assistant_text.lower():
                    session.was_escalated = True
                    
            else:
                # Создаем новую сессию
                is_group = False
                if search_params and search_params.get("adults", 0) > 6:
                    is_group = True
                
                session = SessionAnalytics(
                    conversation_id=conversation_id,
                    message_count=1,
                    user_messages=1,
                    bot_messages=1,
                    tour_searches=1 if tours_count > 0 else 0,
                    tours_found=tours_count,
                    tours_shown=min(tours_count, 5) if tours_count > 0 else 0,
                    has_booking_intent=(intent == "booking"),
                    is_group_request=is_group,
                    successful_search=(tours_count > 0),
                    final_search_params=search_params,
                    started_at=datetime.utcnow(),
                    last_activity=datetime.utcnow(),
                    status="active"
                )
                db.add(session)
            
            db.commit()
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ DB error in _save_turn_sync: {e}")
            raise
        finally:
            db.close()
    
    @staticmethod
    async def log_api_call(
        conversation_id: Optional[str],
        turn_id: Optional[int],
        api_name: str,
        endpoint: str,
        request_params: Optional[dict] = None,
        status_code: Optional[int] = None,
        elapsed_ms: Optional[float] = None,
        result_count: Optional[int] = None,
        error: Optional[str] = None,
        response_summary: Optional[str] = None
    ) -> None:
        """
        Логирование вызова внешнего API.
        
        Args:
            conversation_id: Thread ID (опционально)
            turn_id: Номер хода (опционально)
            api_name: Название API (tourvisor/yandexgpt)
            endpoint: Endpoint API
            request_params: Параметры запроса (будут sanitized)
            status_code: HTTP статус код
            elapsed_ms: Время выполнения
            result_count: Количество результатов
            error: Текст ошибки
            response_summary: Краткое описание ответа
        """
        if not settings.LOG_API_CALLS or not settings.DATABASE_URL:
            return
        
        try:
            await asyncio.to_thread(
                AnalyticsService._log_api_call_sync,
                conversation_id=conversation_id,
                turn_id=turn_id,
                api_name=api_name,
                endpoint=endpoint,
                request_params=AnalyticsService._sanitize_params(request_params),
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                result_count=result_count,
                error=error,
                response_summary=response_summary
            )
        except Exception as e:
            logger.error(f"❌ Error logging API call: {e}")
    
    @staticmethod
    def _log_api_call_sync(
        conversation_id: Optional[str],
        turn_id: Optional[int],
        api_name: str,
        endpoint: str,
        request_params: Optional[dict],
        status_code: Optional[int],
        elapsed_ms: Optional[float],
        result_count: Optional[int],
        error: Optional[str],
        response_summary: Optional[str]
    ) -> None:
        """Синхронное логирование API вызова."""
        from app.core.database import SessionLocal, APICallLog
        
        db = SessionLocal()
        
        try:
            log_entry = APICallLog(
                conversation_id=conversation_id,
                turn_id=turn_id,
                api_name=api_name,
                endpoint=endpoint,
                request_params=request_params,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                result_count=result_count,
                error=error,
                response_summary=response_summary[:500] if response_summary and len(response_summary) > 500 else response_summary,
                is_success=(error is None and status_code and status_code < 400),
                created_at=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"❌ DB error logging API call: {e}")
        finally:
            db.close()
    
    @staticmethod
    def _sanitize_params(params: Optional[dict]) -> Optional[dict]:
        """Удаление sensitive данных из параметров."""
        if not params:
            return None
        
        sensitive_keys = {
            "authlogin", "authpass", "auth_login", "auth_pass",
            "api_key", "apikey", "token", "secret", "password"
        }
        
        sanitized = {}
        for key, value in params.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***MASKED***"
            elif isinstance(value, dict):
                sanitized[key] = AnalyticsService._sanitize_params(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    # ==================== READING METHODS ====================
    
    @staticmethod
    def get_session_stats(conversation_id: str) -> Optional[dict]:
        """
        Получить статистику по конкретной сессии.
        
        Returns:
            dict с информацией о сессии или None
        """
        if not settings.DATABASE_URL:
            return None
        
        from app.core.database import SessionLocal, SessionAnalytics
        
        db = SessionLocal()
        
        try:
            session = db.query(SessionAnalytics).filter_by(
                conversation_id=conversation_id
            ).first()
            
            if not session:
                return None
            
            return {
                "conversation_id": session.conversation_id,
                "user_id": session.user_id,
                "message_count": session.message_count,
                "user_messages": session.user_messages,
                "bot_messages": session.bot_messages,
                "tour_searches": session.tour_searches,
                "tours_found": session.tours_found,
                "tours_shown": session.tours_shown,
                "successful_search": session.successful_search,
                "has_booking_intent": session.has_booking_intent,
                "reached_booking": session.reached_booking,
                "was_escalated": session.was_escalated,
                "is_group_request": session.is_group_request,
                "status": session.status,
                "collected_params": session.collected_params,
                "final_search_params": session.final_search_params,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "last_activity": session.last_activity.isoformat() if session.last_activity else None,
                "duration_seconds": session.duration_seconds
            }
        finally:
            db.close()
    
    @staticmethod
    def get_global_stats() -> dict:
        """
        Получить глобальную статистику по всем сессиям.
        
        Returns:
            dict со статистикой
        """
        if not settings.DATABASE_URL:
            return {"error": "Database not configured"}
        
        from sqlalchemy import func
        from app.core.database import SessionLocal, SessionAnalytics, DialogHistory, APICallLog
        
        db = SessionLocal()
        
        try:
            # Общая статистика сессий
            total_sessions = db.query(SessionAnalytics).count()
            active_sessions = db.query(SessionAnalytics).filter_by(status="active").count()
            completed_sessions = db.query(SessionAnalytics).filter_by(status="completed").count()
            abandoned_sessions = db.query(SessionAnalytics).filter_by(status="abandoned").count()
            
            # Статистика сообщений
            avg_messages = db.query(func.avg(SessionAnalytics.message_count)).scalar() or 0
            total_dialogs = db.query(DialogHistory).count()
            
            # Статистика поиска
            total_searches = db.query(func.sum(SessionAnalytics.tour_searches)).scalar() or 0
            total_tours = db.query(func.sum(SessionAnalytics.tours_found)).scalar() or 0
            successful_searches = db.query(SessionAnalytics).filter_by(successful_search=True).count()
            
            # Конверсия
            sessions_with_booking = db.query(SessionAnalytics).filter_by(has_booking_intent=True).count()
            reached_booking = db.query(SessionAnalytics).filter_by(reached_booking=True).count()
            escalated = db.query(SessionAnalytics).filter_by(was_escalated=True).count()
            
            # API статистика
            total_api_calls = db.query(APICallLog).count()
            failed_api_calls = db.query(APICallLog).filter_by(is_success=False).count()
            avg_api_time = db.query(func.avg(APICallLog.elapsed_ms)).scalar() or 0
            
            # Расчет conversion rates
            conversion_to_search = round(successful_searches / total_sessions * 100, 2) if total_sessions > 0 else 0
            conversion_to_booking = round(sessions_with_booking / total_sessions * 100, 2) if total_sessions > 0 else 0
            
            return {
                "sessions": {
                    "total": total_sessions,
                    "active": active_sessions,
                    "completed": completed_sessions,
                    "abandoned": abandoned_sessions
                },
                "messages": {
                    "total_dialogs": total_dialogs,
                    "avg_per_session": round(float(avg_messages), 2)
                },
                "search": {
                    "total_searches": total_searches,
                    "total_tours_found": total_tours,
                    "successful_sessions": successful_searches,
                    "conversion_rate": conversion_to_search
                },
                "booking": {
                    "sessions_with_intent": sessions_with_booking,
                    "reached_booking": reached_booking,
                    "escalated_to_manager": escalated,
                    "conversion_rate": conversion_to_booking
                },
                "api": {
                    "total_calls": total_api_calls,
                    "failed_calls": failed_api_calls,
                    "avg_response_time_ms": round(float(avg_api_time), 2),
                    "success_rate": round((total_api_calls - failed_api_calls) / total_api_calls * 100, 2) if total_api_calls > 0 else 100
                }
            }
        finally:
            db.close()
    
    @staticmethod
    def get_dialog_history(conversation_id: str) -> Optional[List[dict]]:
        """
        Получить полную историю диалога.
        
        Returns:
            Список ходов диалога в хронологическом порядке
        """
        if not settings.DATABASE_URL:
            return None
        
        from app.core.database import SessionLocal, DialogHistory
        
        db = SessionLocal()
        
        try:
            dialogs = db.query(DialogHistory).filter_by(
                conversation_id=conversation_id
            ).order_by(DialogHistory.turn_id).all()
            
            if not dialogs:
                return None
            
            result = []
            for dialog in dialogs:
                result.append({
                    "turn_id": dialog.turn_id,
                    "user_text": dialog.user_text,
                    "assistant_text": dialog.assistant_text,
                    "search_params": dialog.search_params,
                    "tour_offers_count": dialog.tours_found_count,
                    "missing_params": dialog.missing_params,
                    "intent": dialog.intent,
                    "search_mode": dialog.search_mode,
                    "cascade_stage": dialog.cascade_stage,
                    "response_time_ms": dialog.response_time_ms,
                    "created_at": dialog.created_at.isoformat() if dialog.created_at else None
                })
            
            return result
        finally:
            db.close()
    
    @staticmethod
    def get_recent_sessions(limit: int = 20, status: Optional[str] = None) -> List[dict]:
        """
        Получить последние сессии.
        
        Args:
            limit: Количество сессий
            status: Фильтр по статусу (active/completed/abandoned)
            
        Returns:
            Список сессий
        """
        if not settings.DATABASE_URL:
            return []
        
        from app.core.database import SessionLocal, SessionAnalytics
        
        db = SessionLocal()
        
        try:
            query = db.query(SessionAnalytics)
            
            if status:
                query = query.filter_by(status=status)
            
            sessions = query.order_by(SessionAnalytics.last_activity.desc()).limit(limit).all()
            
            result = []
            for session in sessions:
                result.append({
                    "conversation_id": session.conversation_id,
                    "message_count": session.message_count,
                    "tour_searches": session.tour_searches,
                    "tours_found": session.tours_found,
                    "successful_search": session.successful_search,
                    "has_booking_intent": session.has_booking_intent,
                    "status": session.status,
                    "started_at": session.started_at.isoformat() if session.started_at else None,
                    "last_activity": session.last_activity.isoformat() if session.last_activity else None
                })
            
            return result
        finally:
            db.close()
    
    @staticmethod
    def mark_session_completed(conversation_id: str) -> bool:
        """
        Пометить сессию как завершенную.
        
        Returns:
            True если успешно
        """
        if not settings.DATABASE_URL:
            return False
        
        from app.core.database import SessionLocal, SessionAnalytics
        
        db = SessionLocal()
        
        try:
            session = db.query(SessionAnalytics).filter_by(
                conversation_id=conversation_id
            ).first()
            
            if session:
                session.status = "completed"
                session.completed_at = datetime.utcnow()
                
                # Вычисляем длительность
                if session.started_at:
                    duration = (session.completed_at - session.started_at).total_seconds()
                    session.duration_seconds = int(duration)
                
                db.commit()
                return True
            
            return False
        finally:
            db.close()
    
    @staticmethod
    def cleanup_abandoned_sessions(hours: int = 24) -> int:
        """
        Пометить старые сессии как abandoned.
        
        Args:
            hours: Сессии старше N часов помечаются как abandoned
            
        Returns:
            Количество помеченных сессий
        """
        if not settings.DATABASE_URL:
            return 0
        
        from app.core.database import SessionLocal, SessionAnalytics
        
        db = SessionLocal()
        
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            sessions = db.query(SessionAnalytics).filter(
                SessionAnalytics.last_activity < cutoff,
                SessionAnalytics.status == "active"
            ).all()
            
            count = 0
            for session in sessions:
                session.status = "abandoned"
                session.completed_at = session.last_activity
                if session.started_at:
                    duration = (session.last_activity - session.started_at).total_seconds()
                    session.duration_seconds = int(duration)
                count += 1
            
            db.commit()
            
            if count > 0:
                logger.info(f"🧹 Помечено {count} сессий как abandoned")
            
            return count
        finally:
            db.close()
    
    @staticmethod
    def delete_session_cascade(conversation_id: str) -> Dict[str, int]:
        """
        Удаление сессии и всех связанных данных (cascade delete).
        
        Удаляет:
        - DialogHistory записи
        - TestNote записи
        - APICallLog записи
        - SessionAnalytics запись
        
        Args:
            conversation_id: ID сессии для удаления
            
        Returns:
            Dict с количеством удалённых записей по каждой таблице
        """
        if not settings.DATABASE_URL:
            return {"error": "Database not configured"}
        
        from app.core.database import SessionLocal, DialogHistory, SessionAnalytics, TestNote, APICallLog
        
        db = SessionLocal()
        deleted = {"dialogs": 0, "notes": 0, "api_calls": 0, "sessions": 0}
        
        try:
            # 1. Удаляем диалоги
            deleted["dialogs"] = db.query(DialogHistory).filter_by(
                conversation_id=conversation_id
            ).delete(synchronize_session=False)
            
            # 2. Удаляем заметки
            deleted["notes"] = db.query(TestNote).filter_by(
                conversation_id=conversation_id
            ).delete(synchronize_session=False)
            
            # 3. Удаляем API логи
            deleted["api_calls"] = db.query(APICallLog).filter_by(
                conversation_id=conversation_id
            ).delete(synchronize_session=False)
            
            # 4. Удаляем сессию
            deleted["sessions"] = db.query(SessionAnalytics).filter_by(
                conversation_id=conversation_id
            ).delete(synchronize_session=False)
            
            db.commit()
            
            total = sum(deleted.values())
            if total > 0:
                logger.info(f"🗑️ Cascade delete для {conversation_id}: {deleted}")
            
            return deleted
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка cascade delete: {e}")
            return {"error": str(e)}
        finally:
            db.close()
    
    @staticmethod
    def cleanup_old_data(days: int = 30) -> Dict[str, int]:
        """
        Очистка старых данных (старше N дней).
        
        Удаляет ВСЕ данные по сессиям старше указанного количества дней.
        Используется для периодической очистки БД.
        
        Args:
            days: Данные старше N дней удаляются
            
        Returns:
            Dict с количеством удалённых записей
        """
        if not settings.DATABASE_URL:
            return {"error": "Database not configured"}
        
        from app.core.database import SessionLocal, DialogHistory, SessionAnalytics, TestNote, APICallLog
        
        db = SessionLocal()
        deleted = {"dialogs": 0, "notes": 0, "api_calls": 0, "sessions": 0}
        
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            # 1. Получаем ID старых сессий
            old_sessions = db.query(SessionAnalytics.conversation_id).filter(
                SessionAnalytics.last_activity < cutoff
            ).all()
            
            old_conv_ids = [s[0] for s in old_sessions]
            
            if not old_conv_ids:
                return deleted
            
            # 2. Удаляем связанные данные
            deleted["dialogs"] = db.query(DialogHistory).filter(
                DialogHistory.conversation_id.in_(old_conv_ids)
            ).delete(synchronize_session=False)
            
            deleted["notes"] = db.query(TestNote).filter(
                TestNote.conversation_id.in_(old_conv_ids)
            ).delete(synchronize_session=False)
            
            deleted["api_calls"] = db.query(APICallLog).filter(
                APICallLog.conversation_id.in_(old_conv_ids)
            ).delete(synchronize_session=False)
            
            # 3. Удаляем сами сессии
            deleted["sessions"] = db.query(SessionAnalytics).filter(
                SessionAnalytics.conversation_id.in_(old_conv_ids)
            ).delete(synchronize_session=False)
            
            db.commit()
            
            logger.info(f"🧹 Очистка данных старше {days} дней: {deleted}")
            
            return deleted
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка очистки старых данных: {e}")
            return {"error": str(e)}
        finally:
            db.close()


# Глобальный экземпляр сервиса
analytics_service = AnalyticsService()

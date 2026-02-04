"""
Debug Logger для диагностики диалогов и API вызовов.

Включается через переменную окружения DEBUG_LOGS=1.
Записывает события в debug_bundle/LOGS/app.jsonl в формате JSONL.

Использование:
    from app.core.debug_logger import debug_logger
    
    # Логирование turn (сообщение пользователя/ответ)
    debug_logger.log_turn(
        conversation_id="abc-123",
        turn_id=1,
        user_text="Хочу в Египет",
        assistant_text="Из какого города вылетаете?",
        search_mode="package",
        cascade_stage=2,
        search_params={"destination_country": "египет"},
        missing_params=["departure_city"],
        detected_intent="search_tour",
        last_question_type="departure"
    )
    
    # Логирование API вызова
    debug_logger.log_api_trace(
        conversation_id="abc-123",
        turn_id=1,
        endpoint="search.php",
        request_params={"country": 1, "departure": 1},
        status_code=200,
        elapsed_ms=1523,
        result_count=15,
        error=None,
        response_summary="requestid=ABC123"
    )
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class DebugLogger:
    """
    JSONL Logger для диагностики диалогов.
    
    Потокобезопасный. Записывает только если DEBUG_LOGS=1.
    """
    
    # Поля, которые нужно маскировать в request_params
    SENSITIVE_FIELDS = {
        "authlogin", "authpass", "auth_login", "auth_pass",
        "api_key", "apikey", "token", "secret", "password",
        "TOURVISOR_AUTH_LOGIN", "TOURVISOR_AUTH_PASS",
        "YANDEX_API_KEY", "YANDEX_FOLDER_ID"
    }
    
    def __init__(self):
        self._lock = threading.Lock()
        self._log_file: Optional[Path] = None
        self._enabled: Optional[bool] = None
    
    @property
    def enabled(self) -> bool:
        """Проверка, включено ли логирование."""
        if self._enabled is None:
            self._enabled = os.getenv("DEBUG_LOGS", "0") == "1"
        return self._enabled
    
    @property
    def log_file(self) -> Path:
        """Путь к файлу логов."""
        if self._log_file is None:
            # Ищем корень проекта (где находится app/)
            current = Path(__file__).resolve()
            project_root = current.parent.parent.parent  # app/core/debug_logger.py -> project root
            
            self._log_file = project_root / "debug_bundle" / "LOGS" / "app.jsonl"
            
            # Создаём директорию если нужно
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
        
        return self._log_file
    
    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Маскирование секретных полей в параметрах.
        
        Args:
            params: Исходные параметры
            
        Returns:
            dict: Параметры с замаскированными секретами
        """
        if not params:
            return {}
        
        sanitized = {}
        for key, value in params.items():
            key_lower = key.lower()
            
            # Проверяем, является ли поле секретным
            is_sensitive = any(
                sensitive.lower() in key_lower 
                for sensitive in self.SENSITIVE_FIELDS
            )
            
            if is_sensitive:
                sanitized[key] = "***MASKED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_params(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_params(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _write_event(self, event: dict[str, Any]) -> None:
        """
        Запись события в JSONL файл (потокобезопасно).
        
        Args:
            event: Событие для записи
        """
        if not self.enabled:
            return
        
        # Добавляем timestamp если нет
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        try:
            with self._lock:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            # Не падаем если логирование сломалось
            print(f"[DEBUG_LOGGER] Error writing log: {e}")
    
    def log_turn(
        self,
        conversation_id: str,
        turn_id: int,
        user_text: str,
        assistant_text: str,
        search_mode: Optional[str] = None,
        cascade_stage: Optional[int] = None,
        search_params: Optional[dict] = None,
        missing_params: Optional[list[str]] = None,
        detected_intent: Optional[str] = None,
        last_question_type: Optional[str] = None,
        extra: Optional[dict] = None
    ) -> None:
        """
        Логирование turn (сообщение пользователя + ответ ассистента).
        
        Args:
            conversation_id: ID сессии/диалога
            turn_id: Номер хода в диалоге
            user_text: Текст пользователя
            assistant_text: Ответ ассистента
            search_mode: Режим поиска (package/burning/hotel_only)
            cascade_stage: Текущий этап каскада (1-5)
            search_params: Собранные параметры поиска (будут санитизированы)
            missing_params: Список недостающих параметров
            detected_intent: Определённый intent
            last_question_type: Тип последнего заданного вопроса
            extra: Дополнительные данные
        """
        if not self.enabled:
            return
        
        event = {
            "type": "turn",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "user_text": user_text,
            "assistant_text": assistant_text,
        }
        
        if search_mode:
            event["search_mode"] = search_mode
        if cascade_stage is not None:
            event["cascade_stage"] = cascade_stage
        if search_params:
            event["search_params"] = self._sanitize_params(search_params)
        if missing_params:
            event["missing_params"] = missing_params
        if detected_intent:
            event["detected_intent"] = detected_intent
        if last_question_type:
            event["last_question_type"] = last_question_type
        if extra:
            event["extra"] = self._sanitize_params(extra)
        
        self._write_event(event)
    
    def log_api_trace(
        self,
        conversation_id: str,
        turn_id: int,
        endpoint: str,
        request_params: Optional[dict] = None,
        status_code: Optional[int] = None,
        elapsed_ms: Optional[float] = None,
        result_count: Optional[int] = None,
        error: Optional[str] = None,
        response_summary: Optional[str] = None,
        extra: Optional[dict] = None
    ) -> None:
        """
        Логирование вызова Tourvisor API.
        
        Args:
            conversation_id: ID сессии/диалога
            turn_id: Номер хода в диалоге
            endpoint: Endpoint API (search.php, hottours.php, etc.)
            request_params: Параметры запроса (будут санитизированы)
            status_code: HTTP статус код
            elapsed_ms: Время выполнения в мс
            result_count: Количество результатов
            error: Текст ошибки (если есть)
            response_summary: Краткое описание ответа (НЕ полный raw)
            extra: Дополнительные данные
        """
        if not self.enabled:
            return
        
        event = {
            "type": "api_trace",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "endpoint": endpoint,
        }
        
        if request_params:
            event["request_params"] = self._sanitize_params(request_params)
        if status_code is not None:
            event["status_code"] = status_code
        if elapsed_ms is not None:
            event["elapsed_ms"] = round(elapsed_ms, 2)
        if result_count is not None:
            event["result_count"] = result_count
        if error:
            event["error"] = error
        if response_summary:
            # Ограничиваем длину summary
            event["response_summary"] = response_summary[:500] if len(response_summary) > 500 else response_summary
        if extra:
            event["extra"] = self._sanitize_params(extra)
        
        self._write_event(event)
    
    def log_error(
        self,
        conversation_id: str,
        turn_id: int,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        context: Optional[dict] = None
    ) -> None:
        """
        Логирование ошибки.
        
        Args:
            conversation_id: ID сессии/диалога
            turn_id: Номер хода в диалоге
            error_type: Тип ошибки (exception class name)
            error_message: Текст ошибки
            stack_trace: Stack trace (опционально)
            context: Дополнительный контекст
        """
        if not self.enabled:
            return
        
        event = {
            "type": "error",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "error_type": error_type,
            "error_message": error_message,
        }
        
        if stack_trace:
            # Ограничиваем длину stack trace
            event["stack_trace"] = stack_trace[:2000] if len(stack_trace) > 2000 else stack_trace
        if context:
            event["context"] = self._sanitize_params(context)
        
        self._write_event(event)


# Глобальный экземпляр логгера
debug_logger = DebugLogger()

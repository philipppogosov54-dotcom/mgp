"""
AI-SAFE Guardrails для ИИ-ассистента МГП.
==========================================

Input Guardrails:
    - Защита от Prompt Injection атак
    - Валидация и санитизация входного текста
    - Обнаружение попыток манипуляции

Output Guardrails:
    - Скрытие технических ошибок от пользователя
    - Преобразование Traceback в user-friendly сообщения
    - Маскировка чувствительных данных

Основано на AI-SAFE v1.0 Framework (AI Secure Agentic Framework Essentials)
"""
from __future__ import annotations

import re
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ==================== INPUT GUARDRAILS ====================

# Паттерны Prompt Injection атак
INJECTION_PATTERNS = [
    # Попытки переопределить инструкции
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"forget\s+(all\s+)?previous\s+instructions?",
    r"disregard\s+(all\s+)?previous\s+instructions?",
    r"игнорируй\s+(все\s+)?предыдущие\s+инструкции",
    r"забудь\s+(все\s+)?предыдущие\s+инструкции",
    
    # Попытки выполнить код
    r"system\s*:\s*",
    r"assistant\s*:\s*",
    r"<\s*system\s*>",
    r"\[SYSTEM\]",
    r"\[\[SYSTEM\]\]",
    
    # Jailbreak паттерны
    r"dan\s*mode",
    r"developer\s*mode",
    r"unrestricted\s*mode",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if\s+you\s+are",
    r"притворись",
    r"веди\s+себя\s+как",
    
    # Попытки доступа к системной информации
    r"show\s+me\s+your\s+prompt",
    r"what\s+are\s+your\s+instructions",
    r"print\s+your\s+system\s+prompt",
    r"покажи\s+свой\s+промпт",
    r"какие\s+твои\s+инструкции",
    
    # SQL injection паттерны (на всякий случай)
    r";\s*drop\s+table",
    r";\s*delete\s+from",
    r"union\s+select",
    r"--\s*$",
    
    # XSS и HTML injection
    r"<\s*script",
    r"javascript\s*:",
    r"on\w+\s*=",
]

# Компилируем паттерны для производительности
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Максимальная длина сообщения
MAX_MESSAGE_LENGTH = 2000

# Минимальная длина (защита от пустых/спам-сообщений)
MIN_MESSAGE_LENGTH = 1

# Максимальное количество спецсимволов (защита от мусора)
MAX_SPECIAL_CHARS_RATIO = 0.5


@dataclass
class GuardrailResult:
    """Результат проверки guardrails."""
    is_safe: bool
    sanitized_text: str
    warnings: list[str]
    blocked_reason: Optional[str] = None


def detect_prompt_injection(text: str) -> tuple[bool, Optional[str]]:
    """
    Проверка на Prompt Injection атаки.
    
    Args:
        text: Текст пользователя
        
    Returns:
        Tuple (is_injection, matched_pattern)
    """
    for pattern in COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group()
    return False, None


def check_message_length(text: str) -> tuple[bool, Optional[str]]:
    """
    Проверка длины сообщения.
    
    Returns:
        Tuple (is_valid, error_message)
    """
    if len(text) < MIN_MESSAGE_LENGTH:
        return False, "Сообщение слишком короткое"
    
    if len(text) > MAX_MESSAGE_LENGTH:
        return False, f"Сообщение слишком длинное (максимум {MAX_MESSAGE_LENGTH} символов)"
    
    return True, None


def check_special_chars(text: str) -> tuple[bool, Optional[str]]:
    """
    Проверка на избыточное количество специальных символов.
    
    Returns:
        Tuple (is_valid, error_message)
    """
    if not text:
        return True, None
    
    # Считаем спецсимволы (не буквы, цифры и базовые знаки препинания)
    special_count = sum(1 for c in text if not c.isalnum() and c not in ' .,!?;:-()"\'\n')
    ratio = special_count / len(text)
    
    if ratio > MAX_SPECIAL_CHARS_RATIO:
        return False, "Сообщение содержит слишком много специальных символов"
    
    return True, None


def sanitize_text(text: str) -> str:
    """
    Санитизация входного текста.
    
    Удаляет потенциально опасные конструкции,
    сохраняя смысл сообщения.
    """
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    
    # Убираем управляющие символы (кроме newline)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # Убираем HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    
    # Нормализуем кавычки
    text = text.replace('«', '"').replace('»', '"')
    
    return text.strip()


def validate_input(text: str) -> GuardrailResult:
    """
    Главная функция валидации входного текста.
    
    Выполняет все проверки и возвращает структурированный результат.
    
    Args:
        text: Текст пользователя
        
    Returns:
        GuardrailResult с результатом проверки
    """
    warnings = []
    
    # Базовая проверка на None/пустоту
    if text is None:
        return GuardrailResult(
            is_safe=False,
            sanitized_text="",
            warnings=[],
            blocked_reason="Получено пустое сообщение"
        )
    
    # Санитизация
    sanitized = sanitize_text(text)
    
    # Проверка длины
    is_valid_length, length_error = check_message_length(sanitized)
    if not is_valid_length:
        return GuardrailResult(
            is_safe=False,
            sanitized_text=sanitized[:MAX_MESSAGE_LENGTH],
            warnings=[],
            blocked_reason=length_error
        )
    
    # Проверка на спецсимволы
    is_valid_chars, chars_error = check_special_chars(sanitized)
    if not is_valid_chars:
        warnings.append(chars_error)
        # Не блокируем, но предупреждаем
    
    # Проверка на Prompt Injection
    is_injection, pattern = detect_prompt_injection(sanitized)
    if is_injection:
        logger.warning(f"🚨 Prompt Injection detected: '{pattern}'")
        return GuardrailResult(
            is_safe=False,
            sanitized_text="",
            warnings=[],
            blocked_reason="Обнаружена попытка манипуляции системой"
        )
    
    return GuardrailResult(
        is_safe=True,
        sanitized_text=sanitized,
        warnings=warnings,
        blocked_reason=None
    )


# ==================== OUTPUT GUARDRAILS ====================

# Паттерны технических ошибок для маскировки
ERROR_PATTERNS = [
    r"Traceback \(most recent call last\):",
    r"File \"[^\"]+\", line \d+",
    r"^\s*raise\s+\w+Error",
    r"^\s*Exception:\s*",
    r"^\s*Error:\s*",
    r"httpx\..*Error",
    r"aiohttp\..*Error",
    r"ConnectionError",
    r"TimeoutError",
    r"KeyError:\s*",
    r"ValueError:\s*",
    r"TypeError:\s*",
    r"AttributeError:\s*",
    r"IndexError:\s*",
]

COMPILED_ERROR_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in ERROR_PATTERNS]

# Стандартные user-friendly сообщения
USER_FRIENDLY_ERRORS = {
    "default": "Произошла техническая ошибка. Попробуйте ещё раз или обратитесь к менеджеру.",
    "timeout": "К сожалению, поиск занял слишком много времени. Попробуйте сузить параметры.",
    "connection": "Не удалось связаться с сервисом поиска. Попробуйте через несколько минут.",
    "validation": "Пожалуйста, проверьте введённые данные и попробуйте снова.",
    "not_found": "По вашему запросу ничего не найдено. Попробуйте изменить параметры.",
}


def contains_technical_error(text: str) -> bool:
    """Проверка, содержит ли текст технические ошибки."""
    for pattern in COMPILED_ERROR_PATTERNS:
        if pattern.search(text):
            return True
    return False


def get_user_friendly_error(error: Exception) -> str:
    """
    Преобразование исключения в user-friendly сообщение.
    
    Args:
        error: Исключение Python
        
    Returns:
        User-friendly сообщение для пользователя
    """
    error_str = str(error).lower()
    
    if "timeout" in error_str or "timed out" in error_str:
        return USER_FRIENDLY_ERRORS["timeout"]
    
    if "connection" in error_str or "connect" in error_str:
        return USER_FRIENDLY_ERRORS["connection"]
    
    if "validation" in error_str or "invalid" in error_str:
        return USER_FRIENDLY_ERRORS["validation"]
    
    if "not found" in error_str or "404" in error_str:
        return USER_FRIENDLY_ERRORS["not_found"]
    
    return USER_FRIENDLY_ERRORS["default"]


def sanitize_output(text: str) -> str:
    """
    Санитизация выходного текста.
    
    Удаляет технические детали, сохраняя user-friendly содержимое.
    
    Args:
        text: Текст для отправки пользователю
        
    Returns:
        Очищенный текст
    """
    if not text:
        return text
    
    # Если обнаружены технические ошибки — заменяем на стандартное сообщение
    if contains_technical_error(text):
        logger.warning(f"🔒 Technical error detected in output, masking...")
        return USER_FRIENDLY_ERRORS["default"]
    
    # Убираем потенциальные пути к файлам
    text = re.sub(r'/[^\s]+\.py', '[internal]', text)
    text = re.sub(r'line \d+', '', text)
    
    return text.strip()


def mask_sensitive_data(text: str) -> str:
    """
    Маскировка чувствительных данных в тексте.
    
    Маскирует:
    - API ключи
    - Токены
    - Пароли
    """
    # API ключи и токены
    text = re.sub(r'(api[_-]?key|token|password|secret)\s*[=:]\s*["\']?[\w-]+["\']?', 
                  r'\1=***MASKED***', text, flags=re.IGNORECASE)
    
    # Bearer токены
    text = re.sub(r'Bearer\s+[\w.-]+', 'Bearer ***MASKED***', text)
    
    return text


# ==================== MIDDLEWARE ====================

async def apply_input_guardrails(user_message: str) -> tuple[str, Optional[str]]:
    """
    Применение Input Guardrails к сообщению пользователя.
    
    Args:
        user_message: Исходное сообщение
        
    Returns:
        Tuple (sanitized_message, error_message)
        error_message = None если сообщение прошло проверку
    """
    result = validate_input(user_message)
    
    if not result.is_safe:
        logger.warning(f"🚫 Input blocked: {result.blocked_reason}")
        return "", result.blocked_reason
    
    if result.warnings:
        for warning in result.warnings:
            logger.info(f"⚠️ Input warning: {warning}")
    
    return result.sanitized_text, None


def apply_output_guardrails(response: str, error: Optional[Exception] = None) -> str:
    """
    Применение Output Guardrails к ответу системы.
    
    Args:
        response: Ответ для пользователя
        error: Исключение (если было)
        
    Returns:
        Безопасный ответ
    """
    if error:
        return get_user_friendly_error(error)
    
    response = sanitize_output(response)
    response = mask_sensitive_data(response)
    
    return response

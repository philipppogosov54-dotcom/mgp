# ==================== MGP AI Assistant ====================
# Dockerfile для продакшн-деплоя на TimeWeb Cloud
# 
# Сборка: docker build -t mgp-assistant .
# Запуск: docker run -p 8000:8000 --env-file .env mgp-assistant

FROM python:3.11-slim

# Метаданные
LABEL maintainer="MGP Team"
LABEL description="ИИ-ассистент туристического агентства МГП"
LABEL version="1.0.0"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Системные зависимости (для psycopg + curl для healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY frontend/ ./frontend/

# Создаём непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Порт
EXPOSE 8000

# Health check (увеличен start-period для инициализации БД)
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск через gunicorn для production (1 worker чтобы избежать race condition при создании таблиц)
CMD ["gunicorn", "app.main:app", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "120"]

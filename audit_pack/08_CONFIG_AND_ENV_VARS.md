# Config and Environment Variables

## Configuration Source

**File:** `app/core/config.py`  
**Method:** Pydantic BaseSettings with `.env` file support

## All Environment Variables

### Application

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `APP_NAME` | str | "MGP AI Assistant" | No | Application name |
| `APP_VERSION` | str | "1.0.0" | No | Version |
| `DEBUG` | bool | false | No | Debug mode (verbose logging) |

### Server

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `HOST` | str | "0.0.0.0" | No | Bind address |
| `PORT` | int | 8000 | No | Bind port |
| `CORS_ORIGINS` | list | [...] | No | Allowed CORS origins |

### Tourvisor API

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `TOURVISOR_AUTH_LOGIN` | str | "" | **Yes** | API login |
| `TOURVISOR_AUTH_PASS` | str | "" | **Yes** | API password |
| `TOURVISOR_BASE_URL` | str | "http://tourvisor.ru/xml" | No | API base URL |
| `TOURVISOR_TIMEOUT` | int | 30 | No | Request timeout (sec) |
| `TOURVISOR_MOCK` | bool | true | No | Use mock mode |

### YandexGPT API

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `YANDEX_FOLDER_ID` | str | "" | If GPT enabled | Cloud folder ID |
| `YANDEX_API_KEY` | str | "" | If GPT enabled | API key |
| `YANDEX_MODEL` | str | "yandexgpt-lite" | No | Model name |
| `YANDEX_GPT_ENABLED` | bool | false | No | Enable LLM |

### PostgreSQL

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `DATABASE_URL` | str | "" | No | PostgreSQL connection string |
| `ENABLE_ANALYTICS` | bool | true | No | Save dialogs to DB |
| `SESSION_CLEANUP_HOURS` | int | 24 | No | Cleanup interval |
| `LOG_API_CALLS` | bool | true | No | Log API calls to DB |

### Rate Limiting

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `RATE_LIMIT_ENABLED` | bool | true | No | Enable rate limiting |
| `RATE_LIMIT_CHAT_PER_MINUTE` | int | 30 | No | /chat limit |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | int | 60 | No | Default limit |

### Search Defaults

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `DEFAULT_NIGHTS_MIN` | int | 7 | No | Min nights for range |
| `DEFAULT_NIGHTS_MAX` | int | 14 | No | Max nights for range |
| `MAX_TOUR_OFFERS` | int | 5 | No | Max results to show |

### Admin

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `ADMIN_API_KEY` | str | "" | No | Admin endpoint auth |

### Monitoring

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `SENTRY_DSN` | str | None | No | Sentry error tracking |

## Usage in Code

**Location:** `app/core/config.py:98-104`

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

**Import:**
```python
from app.core.config import settings

if settings.DEBUG:
    ...
```

## .env.example

**Location:** `env.example` (root of project)

```env
# Application
APP_NAME="MGP AI Assistant"
APP_VERSION="1.0.0"
DEBUG=true

# Server
HOST=0.0.0.0
PORT=8000

# Tourvisor API
TOURVISOR_AUTH_LOGIN=your_login
TOURVISOR_AUTH_PASS=your_password
TOURVISOR_BASE_URL=http://tourvisor.ru/xml
TOURVISOR_TIMEOUT=30
TOURVISOR_MOCK=true

# YandexGPT API
YANDEX_FOLDER_ID=
YANDEX_API_KEY=
YANDEX_MODEL=yandexgpt-lite
YANDEX_GPT_ENABLED=false

# PostgreSQL (optional)
DATABASE_URL=

# Search
DEFAULT_NIGHTS_MIN=7
DEFAULT_NIGHTS_MAX=14
MAX_TOUR_OFFERS=5
```

## Auto-Generated Constants

**File:** `app/core/tourvisor_constants.py`

Auto-synced from Tourvisor API every 24 hours.

Contains:
- `COUNTRIES` — dict of country_name → country_id
- `DEPARTURES` — dict of city_name → departure_id
- `LAST_SYNC` — ISO timestamp of last sync

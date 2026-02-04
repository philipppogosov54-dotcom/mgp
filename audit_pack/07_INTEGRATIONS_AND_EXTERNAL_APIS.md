# Integrations and External APIs

## 1. Tourvisor API

**Client:** `app/services/tourvisor.py` (2580 lines)  
**Base URL:** `http://tourvisor.ru/xml`  
**Auth:** Classic auth (`authlogin`, `authpass` query params)

### Endpoints Used

| Endpoint | Purpose | Location |
|----------|---------|----------|
| `search.php` | Initiate tour search | `tourvisor.py:~800` |
| `result.php?type=status` | Poll search status | `tourvisor.py:~900` |
| `result.php?type=result` | Get search results | `tourvisor.py:~950` |
| `hottours.php` | Hot tours listing | `tourvisor.py:~1200` |
| `list.php?type=country` | Countries dictionary | `tourvisor.py:~200` |
| `list.php?type=departure` | Departure cities dictionary | `tourvisor.py:~300` |
| `list.php?type=region` | Regions/resorts by country | `tourvisor.py:~400` |
| `list.php?type=hotel` | Hotels by country | `tourvisor.py:~500` |
| `hotel.php` | Hotel content (photos, description) | `tourvisor.py:~1500` |

### Search Request Parameters

**Location:** `app/models/domain.py` — `SearchRequest`

```python
@dataclass
class SearchRequest:
    departure: int          # Departure city ID
    country: int            # Country ID
    datefrom: date          # Start date
    dateto: date            # End date
    nightsfrom: int         # Min nights
    nightsto: int           # Max nights
    adults: int             # Adults count
    children: list[int]     # Children ages
    stars: Optional[int]    # Star rating
    meal: Optional[int]     # Meal type ID
    hotel: Optional[int]    # Specific hotel ID
    region: Optional[int]   # Region/resort ID
```

### Response Parsing

**Location:** `app/services/tourvisor.py:~1000-1100`

Maps Tourvisor JSON to `TourOffer` domain model.

### Error Handling

```python
try:
    response = await self.client.get(url, timeout=settings.TOURVISOR_TIMEOUT)
    response.raise_for_status()
except httpx.TimeoutException:
    logger.error("Tourvisor timeout")
    return SearchResponse(offers=[], status="timeout")
except httpx.HTTPError as e:
    logger.error(f"Tourvisor HTTP error: {e}")
    return SearchResponse(offers=[], status="error")
```

### Caching

- Countries/Departures: cached in `tourvisor_constants.py` (synced every 24h)
- Regions: cached in `_REGIONS_CACHE` dict (in-memory)

## 2. YandexGPT API

**Client:** `app/agent/llm.py`  
**Base URL:** `https://llm.api.cloud.yandex.net/foundationModels/v1/completion`  
**Auth:** API Key in `Authorization: Api-Key {key}` header

### Usage

**Location:** `app/agent/nodes.py:2505` — `extract_entities_with_llm()`

Called when regex extraction incomplete. LLM extracts:
- Intent
- Country
- Dates
- Adults/children
- Hotel preferences

### Request Format

```json
{
  "modelUri": "gpt://{folder_id}/{model}",
  "completionOptions": {
    "stream": false,
    "temperature": 0.1,
    "maxTokens": 500
  },
  "messages": [
    {"role": "system", "text": "...system prompt..."},
    {"role": "user", "text": "user message"}
  ]
}
```

### Response Parsing

Expects JSON in response text:
```json
{
  "intent": "search_tour",
  "country": "Турция",
  "departure": "Москва",
  "date": "15.02.2026",
  "nights": 7,
  "adults": 2,
  "children": [5]
}
```

### Fallback

If `YANDEX_GPT_ENABLED=false` → regex-only extraction

## 3. PostgreSQL

**Connection:** `app/core/database.py`  
**ORM:** Raw psycopg2 (no ORM)

### Tables

| Table | Purpose | Location |
|-------|---------|----------|
| `checkpoints` | LangGraph state persistence | Created by LangGraph |
| `dialog_turns` | Dialog history for analytics | `app/services/analytics.py` |
| `sessions` | Session metadata | `app/services/analytics.py` |

### Usage

**Location:** `app/core/session.py`

```python
if settings.DATABASE_URL:
    checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
else:
    checkpointer = MemorySaver()
```

## 4. CRM (Stub)

**Location:** `app/services/crm.py`

Currently NOT IMPLEMENTED. Stub for future integration.

```python
class CRMService:
    async def create_lead(self, name, phone, tour_id):
        # TODO: Implement CRM integration
        pass
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TOURVISOR_AUTH_LOGIN` | Yes | — | Tourvisor login |
| `TOURVISOR_AUTH_PASS` | Yes | — | Tourvisor password |
| `TOURVISOR_BASE_URL` | No | `http://tourvisor.ru/xml` | API base URL |
| `TOURVISOR_TIMEOUT` | No | 30 | Request timeout (seconds) |
| `TOURVISOR_MOCK` | No | true | Use mock data (dev mode) |
| `YANDEX_FOLDER_ID` | If GPT enabled | — | Yandex Cloud folder ID |
| `YANDEX_API_KEY` | If GPT enabled | — | Yandex Cloud API key |
| `YANDEX_MODEL` | No | `yandexgpt-lite` | Model name |
| `YANDEX_GPT_ENABLED` | No | false | Enable LLM extraction |
| `DATABASE_URL` | No | — | PostgreSQL connection string |

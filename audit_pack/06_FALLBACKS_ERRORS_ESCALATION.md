# Fallbacks, Errors, and Escalation

## Fallback Messages

### 1. Unknown Intent

**Location:** `app/agent/nodes.py:3808` — `generate_fallback_response()`

When no intent detected:
```
"Я могу помочь с подбором тура. Куда бы вы хотели поехать?"
```

### 2. Invalid Country

**Location:** `app/agent/nodes.py:3720` — `invalid_country_handler()`

When country not in VALID_COUNTRIES:
```
"К сожалению, мы не организуем туры в {country}. 
Рекомендую рассмотреть: Турция, Египет, ОАЭ, Таиланд."
```

### 3. No Tours Found

**Location:** `app/agent/nodes.py:4728` — `generate_no_results_explanation()`

Returns explanation based on reason:
- No tours with filters → suggest relaxing stars/food
- Off-season → explain seasonality
- No routes → suggest alternative departure city

### 4. Unknown Departure City

**Location:** `app/agent/nodes.py` — handled in `input_analyzer()`

When city not found:
```
"Не нашёл город {city}. Уточните город вылета или выберите из списка..."
```

## Error Handling

### API Layer

**Location:** `app/api/v1/endpoints/chat.py:224-232`

```python
except Exception as e:
    logger.error(f"❌ Chat error: {e}")
    user_friendly_error = apply_output_guardrails("", error=e)
    return ChatResponse(reply=user_friendly_error, ...)
```

### Output Guardrails

**Location:** `app/core/guardrails.py`

```python
def apply_output_guardrails(text: str, error=None) -> str:
    if error:
        # Never expose Python tracebacks
        return "Произошла техническая ошибка. Попробуйте ещё раз."
    # ... sanitization ...
```

### Tourvisor API Errors

**Location:** `app/services/tourvisor.py`

```python
try:
    response = await self._make_request(...)
except httpx.TimeoutException:
    logger.error("Tourvisor timeout")
    return []
except httpx.HTTPError as e:
    logger.error(f"HTTP error: {e}")
    return []
```

## Escalation to Manager

### P3: Large Groups (10+ people)

**Location:** `app/agent/nodes.py:3495-3544` (in `input_analyzer()`)

```python
total_people = adults + actual_children_count

if total_people >= 10:
    # P3 escalation
    state["is_group_request"] = True
    state["group_size"] = total_people
    state["response"] = (
        f"Для группы {total_people} человек рекомендую связаться с менеджером. "
        "Оставьте номер телефона, и мы подготовим индивидуальное предложение."
    )
    state["awaiting_phone"] = True
    return state
```

### P3: Warning for 7-9 people

**Location:** Same as above

```python
if total_people >= 7:
    state["group_warning"] = True
    # Warning message added to response
```

### Booking Handler

**Location:** `app/agent/nodes.py:5407` — `booking_handler()`

When user wants to book:
```python
if state.get("awaiting_phone"):
    # Wait for phone number
    ...
else:
    state["awaiting_phone"] = True
    state["response"] = "Отлично! Оставьте номер телефона, менеджер свяжется с вами."
```

## Phone Number Collection

**Location:** `app/agent/nodes.py:2435` — `detect_phone_number()`

Regex pattern:
```python
r'\+?[78]?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
```

When detected → saved to `state["customer_phone"]`

## Partial Data Handling

### Missing Child Ages

**Location:** `app/agent/nodes.py:3740` — `child_ages_handler()`

When children mentioned but no ages:
```
"Уточните, пожалуйста, возраст ребёнка (или детей)?"
```

State: `state["missing_child_ages"] = count`

### Missing Required Params

**Location:** `app/agent/nodes.py:4852` — `responder()`

Checks `get_missing_required_params()` and generates appropriate question.

## Search Retry Logic

**Location:** `app/agent/nodes.py:3901` — `tour_searcher()`

```python
state["search_attempts"] = state.get("search_attempts", 0) + 1

if state["search_attempts"] >= 3:
    # Stop retrying, offer alternatives
    state["response"] = "Не удалось найти подходящие варианты. Попробуйте изменить параметры."
```

## Flex Search (Date Expansion)

**Location:** `app/agent/nodes.py` — in `tour_searcher()`

When no results:
1. First attempt: exact dates
2. If empty → suggest flex_search (±5 days)
3. If user agrees → `state["flex_search"] = True`, `state["flex_days"] = 5`

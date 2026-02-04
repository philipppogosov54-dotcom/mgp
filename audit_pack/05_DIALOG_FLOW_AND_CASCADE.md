# Dialog Flow and Cascade

## Cascade Stages (Strict Order)

**Location:** `app/agent/state.py:244` — `get_cascade_stage()`

| Stage | Question | Required Slot | Skip Condition |
|-------|----------|---------------|----------------|
| 1 | "В какую страну?" | `destination_country` | — |
| 2 | "Из какого города вылет?" | `departure_city` | `search_mode == "hotel_only"` |
| 3 | "Когда планируете?" | `date_from` + `dates_confirmed` | — |
| 4 | "Сколько человек?" + "Сколько ночей?" | `adults` + `adults_explicit` + `nights` | nights auto-calculated from date_to |
| 5 | "Звёзды и питание?" | `stars` + `food_type` | Non-mass destination or `skip_quality_check` |
| 6 | Search ready | All collected | — |

## Mass Destinations (Require Stage 5)

**Location:** `app/agent/state.py:172`

```python
MASS_DESTINATIONS = ["Турция", "Египет", "ОАЭ", "Таиланд", "Россия"]
```

## Slot Extraction

**Location:** `app/agent/nodes.py:1169` — `extract_entities_regex()`

### Countries (lines ~105-148)
- Regex patterns for all Russian declensions
- Map: "турцию" → "Турция", "египте" → "Египет"

### Departure Cities (lines ~200-400)
- Dictionary DEPARTURE_TYPOS for typo correction
- Fuzzy matching with thefuzz

### Dates (lines ~1300-1800)
- Exact dates: "15 февраля", "15.02", "15/02"
- Relative: "через неделю", "на следующей неделе"
- Month-only: "в марте", "в середине апреля"
- Holidays: "на майские", "на новый год"

### Adults/Children (lines ~1900-2200)
- "2 взрослых", "вдвоём", "мы с женой"
- "с ребёнком 5 лет", "2 детей 4 и 9 лет"
- Format "2+1" → adults=2, children=[unknown]

### Stars/Food (lines ~2200-2400)
- "5 звёзд", "пять звёзд", "5*"
- "всё включено", "ультра", "полупансион"

## "Don't Re-ask" Rules

**Location:** `app/agent/nodes.py:2754` — `input_analyzer()`

### Explicit Slot Flags

| Flag | Meaning | Set When |
|------|---------|----------|
| `adults_explicit` | Adults explicitly stated | "2 взрослых", "вдвоём" found |
| `dates_confirmed` | Date explicitly stated | Date pattern matched |
| `nights_explicit` | Nights explicitly stated | "7 ночей" found |
| `stars_explicit` | Stars explicitly stated | "5 звёзд" found |
| `food_type_explicit` | Food explicitly stated | "всё включено" found |

### Merge Logic (nodes.py ~3100-3200)

```python
# Only overwrite if NOT already explicit
if not existing_params.get("adults_explicit"):
    merged_params["adults"] = new_entities.get("adults")
```

## Clarification Rules

### Ambiguous Dates

**Location:** `app/agent/nodes.py:1500-1600`

- "в феврале" → `date_precision = "month"` → ask for specific date
- "середина марта" → expand to range (10-20)

### Multiple Cities

**Location:** `app/agent/nodes.py:1104` — `resolve_dual_city_context()`

- Сочи, Анапа — can be departure OR destination
- If `last_question_type == "departure"` → departure
- If `last_question_type == "destination"` → destination

### Contradictions

**Location:** `app/agent/nodes.py:3200-3300`

- If new value conflicts with explicit old value → ask for confirmation
- Currently: new value wins (TODO: add confirmation dialog)

## "Skip Quality" Detection

**Location:** `app/agent/state.py:210-220`

```python
SKIP_QUALITY_PHRASES = [
    "всё равно", "не важно", "любой", "на ваш вкус",
    "рассмотрим варианты", "покажите разные"
]
```

When detected → `skip_quality_check = True` → skip Stage 5

## Quality Check Question

**Location:** `app/agent/state.py:241`

```python
QUALITY_CHECK_QUESTION = "Какой уровень отеля — 5 звёзд всё включено или рассмотрим варианты?"
```

## Search Modes

**Location:** `app/agent/nodes.py:784` — `detect_search_mode()`

| Mode | Trigger | Cascade Difference |
|------|---------|---------------------|
| `package` | Default | Requires departure_city |
| `hotel_only` | "только отель", "без перелёта" | Skips departure_city |
| `burning` | "горящие", "горящий тур" | Flexible dates |

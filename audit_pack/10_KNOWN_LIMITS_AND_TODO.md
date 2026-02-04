# Known Limits and TODO

## Known Limitations

### 1. Group Size Limit

**Location:** `app/agent/nodes.py:3495-3544`

- Groups ≥10 people → automatic escalation to manager
- Tourvisor API may not return results for large groups
- **Workaround:** Manual handling by manager

### 2. Children Ages Required

**Location:** `app/agent/nodes.py:3740`

- Children without ages cannot be searched
- Must ask user for each child's age
- **Limitation:** No default age assumption

### 3. LLM Hallucinations

**Location:** `app/agent/nodes.py:2505`

- YandexGPT may hallucinate children/adults
- **Mitigation:** `children_explicit_from_text` flag
- Only regex-confirmed children are sent to API

### 4. Date Parsing Ambiguity

**Location:** `app/agent/nodes.py:1300-1800`

- "через 2 недели" → calculated from today
- "в середине марта" → approximate (10-20)
- **Limitation:** May not match user expectation exactly

### 5. City Disambiguation

**Location:** `app/agent/nodes.py:1104`

- Сочи, Анапа can be departure OR destination
- Relies on `last_question_type` context
- **Limitation:** May misinterpret in single-message requests

### 6. Concurrent Sessions

**Location:** `app/core/session.py`

- MemorySaver: in-memory only, lost on restart
- AsyncPostgresSaver: requires PostgreSQL
- **Limitation:** No clustering support without external DB

### 7. Rate Limiting

**Location:** `app/main.py:266`

- slowapi optional dependency
- If not installed → no rate limiting
- **Limitation:** May be vulnerable to abuse without slowapi

### 8. CRM Integration

**Location:** `app/services/crm.py`

- **NOT IMPLEMENTED** — stub only
- Booking requests logged but not sent to CRM

## TODO/FIXME from Code

### High Priority

| Location | Issue |
|----------|-------|
| `nodes.py:3200` | TODO: Add confirmation dialog for contradicting slots |
| `tourvisor.py:~1500` | TODO: Implement hotel content caching |
| `crm.py` | TODO: Implement CRM integration |

### Medium Priority

| Location | Issue |
|----------|-------|
| `nodes.py:4728` | FIXME: Improve no-results explanation for edge cases |
| `state.py:~300` | TODO: Add nights validation (max 30) |
| `graph.py:~150` | TODO: Add retry logic for graph execution failures |

### Low Priority

| Location | Issue |
|----------|-------|
| `fuzzy_matcher.py` | TODO: Add more departure city typos |
| `prompts.py` | TODO: Expand FAQ knowledge base |
| `ru_text.py` | TODO: Add more declension patterns |

## Technical Debt

### 1. nodes.py Size

- **5849 lines** — too large
- Should be split into:
  - `extractors.py` — entity extraction
  - `handlers.py` — node handlers
  - `formatters.py` — response formatting

### 2. Tourvisor Service Size

- **2580 lines** — too large
- Should be split into:
  - `search.py` — search logic
  - `dictionaries.py` — reference data
  - `hotels.py` — hotel content

### 3. Hardcoded Strings

- Many Russian strings hardcoded in nodes.py
- Should be moved to prompts.py or i18n

### 4. Test Coverage

- No pytest fixtures for mocking Tourvisor
- Human tests rely on live API
- Unit tests don't cover all handlers

## Performance Considerations

### Tourvisor API Latency

- Search: 30-60 seconds (async polling)
- Dictionaries: cached for 24 hours
- **Bottleneck:** Search polling time

### LLM Latency

- YandexGPT: 1-3 seconds per request
- **Mitigation:** LLM disabled by default, regex-only

### Memory Usage

- MemorySaver grows with sessions
- No automatic cleanup in dev mode
- **Mitigation:** SESSION_CLEANUP_HOURS for PostgreSQL

## Security Notes

### 1. No Authentication

- API endpoints are public
- Only rate limiting for protection
- ADMIN_API_KEY optional

### 2. Input Guardrails

**Location:** `app/core/guardrails.py`

- Basic prompt injection detection
- XSS sanitization
- **Limitation:** Not comprehensive

### 3. Secret Management

- Secrets in .env file
- No vault integration
- **Risk:** Secrets in git if .env committed

## Future Improvements

1. **Multi-language support** — currently Russian only
2. **Voice input** — not supported
3. **Image processing** — not supported
4. **Booking confirmation** — requires CRM
5. **Payment integration** — not implemented
6. **Telegram/WhatsApp bot** — not implemented

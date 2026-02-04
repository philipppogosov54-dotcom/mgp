# Tests and Fixtures

## Test Files

### Unit Tests (tests/)

| File | Description | Run Command |
|------|-------------|-------------|
| `test_children_explicit.py` | Children detection & P3 group logic | `python tests/test_children_explicit.py` |
| `test_filter_relaxation.py` | Filter relaxation logic | `python tests/test_filter_relaxation.py` |
| `test_no_routes_fallback.py` | No routes fallback | `python tests/test_no_routes_fallback.py` |
| `test_preferred_departures.py` | Preferred departures | `python tests/test_preferred_departures.py` |
| `test_unknown_country_fallback.py` | Unknown country handling | `python tests/test_unknown_country_fallback.py` |
| `test_unknown_departure_fallback.py` | Unknown departure handling | `python tests/test_unknown_departure_fallback.py` |
| `test_relative_dates.py` | Relative date parsing | `python tests/test_relative_dates.py` |
| `test_date_range_nights.py` | Date range & nights calculation | `python tests/test_date_range_nights.py` |
| `test_ru_text.py` | Russian text declension | `python tests/test_ru_text.py` |
| `test_case001_resort_guard.py` | Resort guard regression | — |
| `test_case002_008_holiday_nights.py` | Holiday nights regression | — |
| `test_case003_country_equals_resort.py` | Country=resort regression | — |
| `test_case009_012_composition.py` | Composition regression | — |
| `test_case013_no_offers_fallback.py` | No offers fallback | — |
| `test_case018_food_only_ask_stars.py` | Food-only ask stars | — |

### Human Test Suite (tests/human/)

| File | Description |
|------|-------------|
| `runner.py` | Human test runner with baseline comparison |
| `cases.yaml` | 36 test cases (CASE-001 to CASE-036) |
| `baseline/baseline.json` | Baseline snapshot |
| `results/run_*.json` | Test run results |

**Run Human Tests:**
```bash
cd tests/human
python runner.py --compare
```

**Create Baseline:**
```bash
python runner.py --save-baseline
```

### Human Suite v2 (tests/human_suite/)

| File | Description |
|------|-------------|
| `run_human_suite.py` | Alternative human test runner |
| `dialogues.md` | Dialogue scenarios |
| `test_matrix.md` | Test coverage matrix |

## Test Dialogues (tests/dialogues/)

Regression dialogues organized by feature:

| Folder | Feature |
|--------|---------|
| `F1/` | Entity extraction (countries, resorts, dates, etc.) |
| `F2/` | Cascade flow |
| `F3/` | Search logic |
| `F4/` | API integration |
| `F5/` | Booking flow |
| `F6/` | FAQ |
| `F7/` | Safety/guardrails |
| `PR1-5/` | PR regression packs |
| `BASELINE/` | Baseline regression |
| `Chains/` | Multi-turn dialogues |

## Reports

| File | Description |
|------|-------------|
| `tests/DEFECT_REGISTER.md` | Known defects |
| `tests/FINAL_REPORT.md` | Final test report |
| `tests/COVERAGE_DIFF.md` | Coverage diff |
| `tests/MASTER_DEFECT_LIST.md` | Master defect list |

## Running Tests

### All Unit Tests
```bash
cd _production_mgp
python -m pytest tests/test_*.py -v
```

Note: pytest may not be installed. Alternative:
```bash
python tests/test_children_explicit.py
python tests/test_filter_relaxation.py
# etc.
```

### Human Tests with Comparison
```bash
cd tests/human
python runner.py --compare
```

### Single Human Test Case
```bash
python runner.py --case CASE-001
```

## Fixtures

### Mock Tourvisor Responses

**Location:** Not implemented as separate fixtures.  
Mock mode enabled via `TOURVISOR_MOCK=true` in env.

### Test Data

**Location:** `tests/human/cases.yaml`

Each case contains:
```yaml
CASE-001:
  name: "Базовый запрос"
  h_ref: H1.1
  status: PASS
  fingerprint:
    destination: Турция
    departure: Москва
  dialogue:
    - "Хочу в Турцию из Москвы на 7 ночей"
    - "2 взрослых"
  expected:
    has_tours: true
```

## Test Results Location

| Path | Content |
|------|---------|
| `tests/human/results/run_*.json` | Human test run snapshots |
| `tests/results/*.jsonl` | Manual test logs |
| `test_results/run_*/` | Automated scenario results |

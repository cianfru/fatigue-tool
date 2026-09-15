# CLAUDE.md - AI Assistant Guide

## Project Overview

EASA-compliant biomathematical fatigue risk assessment tool for airline pilots. Implements the Borbely Two-Process Model (homeostatic Process S + circadian Process C) with aviation workload integration and realistic sleep behavior modeling.

**Purpose**: Predict pilot fatigue across multi-day rosters, identify WOCL (Window of Circadian Low, 02:00-05:59) risks, calculate sleep debt, and generate safety recommendations aligned with EU Regulation 965/2012 (EASA ORO.FTL).

## Repository Structure

```
fatigue-tool/
├── core/                          # Fatigue model engine
│   ├── __init__.py                # Public API exports
│   ├── fatigue_model.py           # BorbelyFatigueModel (main engine)
│   ├── sleep_calculator.py        # UnifiedSleepCalculator (5 strategies)
│   ├── compliance.py              # EASAComplianceValidator
│   ├── workload.py                # WorkloadModel (flight phase multipliers)
│   └── parameters.py              # All configuration dataclasses
├── models/                        # Data structures
│   ├── __init__.py
│   └── data_models.py             # Duty, Roster, SleepBlock, Airport, etc.
├── api/                           # FastAPI REST backend
│   └── api_server.py              # POST /api/analyze endpoint
├── parsers/                       # Roster file parsing
│   ├── __init__.py
│   ├── roster_parser.py           # PDF/CSV parser + AirportDatabase
│   └── qatar_crewlink_parser.py   # Qatar Airways CrewLink format
├── visualization/                 # Charts and plots
│   ├── __init__.py
│   ├── chronogram.py              # 30-min resolution timeline
│   └── aviation_calendar.py       # Monthly heatmap
├── scripts/                       # Utility scripts
│   └── analyze_sleep_debt.py
├── tests/                         # Print-based test suite
│   ├── test_sleep_strategies.py
│   ├── test_sleep_efficiency.py
│   ├── test_comprehensive_improvements.py
│   └── test_performance_improvements.py
├── requirements.txt               # Python dependencies
├── Procfile                       # Railway deployment (uvicorn)
├── railway.json                   # Railway CI/CD config
└── Aptfile                        # System-level dependencies (cairo, pango)
```

## Tech Stack

- **Language**: Python 3.8+
- **Web framework**: FastAPI + Uvicorn
- **Data validation**: Pydantic v2
- **Timezone handling**: pytz (all storage in UTC)
- **Airport data**: airportsdata (~7,800 IATA airports)
- **Numerics**: NumPy, Pandas
- **PDF parsing**: pdfplumber (no Java dependency)
- **Visualization**: Plotly, Matplotlib, Pillow
- **Deployment**: Railway.app (NIXPACKS builder)

## Development Commands

### Run the API server
```bash
uvicorn api.api_server:app --reload --host 0.0.0.0 --port 8000
```
OpenAPI docs available at `http://localhost:8000/docs`

### Run tests
Tests use **print-based validation** (not pytest). Run each directly:
```bash
python tests/test_sleep_strategies.py
python tests/test_sleep_efficiency.py
python tests/test_comprehensive_improvements.py
python tests/test_performance_improvements.py
```
Expected output: `✅ TEST PASSED` or `❌ TEST FAILED`

### Install dependencies
```bash
pip install -r requirements.txt
```

## Key Architecture Concepts

### Three-Layer Design
1. **Data Models** (`models/data_models.py`) - Dataclasses for rosters, duties, flights, sleep blocks
2. **Core Engine** (`core/`) - `BorbelyFatigueModel` with sleep strategies, compliance, workload
3. **API Layer** (`api/api_server.py`) - FastAPI server with Pydantic response models

### Sleep Strategy Dispatch
The `UnifiedSleepCalculator.estimate_sleep_blocks()` routes to one of 5 strategies:

| Strategy | Trigger | Behavior |
|----------|---------|----------|
| Night Departure | Report >= 20:00 or < 04:00 | Morning sleep + 2h pre-duty nap |
| Early Morning | Report < 07:00 | Roach (2012) regression, 4-6.6h |
| WOCL Anchor | WOCL crossing + >6h duty | 4.5h consolidated anchor sleep |
| Recovery | Post-duty hotel/home | Environment-adjusted sleep block |
| Normal | Default | 23:00-07:00 home bed |

### Performance Calculation
Per simulation step (default 5 minutes), in `integrate_performance()`:
```
alertness   = (1 - S) * 0.50 + ((C + 1) / 2) * 0.50   # additive, 50/50 weighted
alertness  *= (1 - W)                                  # sleep inertia
alertness  -= time_on_task_rate * hours_on_duty        # linear decrement
alertness  *= 1 - (workload_multiplier - 1) * workload_performance_sensitivity
Performance = 20 + 80 * alertness
```
S and C are combined additively, not multiplicatively — a weighted average with
a small resilience boost in the S 0.15-0.30 band. Workload scales the
performance output; it must never be folded into the time input of Process S,
which is a function of time awake and asleep alone (Borbely 1982).

Result on 0-100 scale with 5 risk levels: Low (75-100), Moderate (65-75), High (55-65), Critical (45-55), Extreme (0-45).

### Cumulative Sleep Debt
Settled in `simulate_roster()` **before** each duty is simulated, then passed
into `simulate_duty(cumulative_sleep_debt=...)` where it raises `s_at_wake` by
`debt * sleep_debt_to_s_coefficient`, capped at `sleep_debt_s_offset_cap`. This
is what makes consecutive early starts compound; if debt is computed after the
simulation it can never reach the prediction.

- The ledger spans the **whole inter-duty gap**, not the 48h `relevant_sleep`
  window used for Process S — otherwise multi-day breaks charge a full scaled
  need against partial sleep and manufacture debt.
- It compares **effective** (quality-weighted) hours against
  `baseline_effective_sleep_need_hours` (7.4h), not raw hours against 8.0h.
  Effective hours already encode fragmentation and circadian misalignment.
- Deficit adds to the ledger; a met need repays it by exponential decay.
  Decay is the *only* repayment mechanism — do not also credit surplus hours.

### Configuration Presets
Four presets in `core/parameters.py` via `ModelConfig`:
- `default_easa_config()` - Balanced (recommended)
- `conservative_config()` - Stricter thresholds
- `liberal_config()` - Airline-friendly assumptions
- `research_config()` - Pure Borbely, 50/50 S/C weighting

## Code Conventions

### Time Handling
- **Storage**: All datetimes in UTC (`report_time_utc`, `release_time_utc`)
- **Display**: Convert to home base timezone using `pytz.timezone(tz).normalize()`
- **Multi-day duties**: Parser adjusts report times crossing midnight via `_validate_duty_times()`
- **Never hardcode UTC offsets** - always use `Airport.timezone` attribute

### Parameters and Configuration
- All model parameters live in `core/parameters.py` - never hardcode values elsewhere
- Every parameter must cite its peer-reviewed source in the docstring:
  ```python
  tau_i: float = 18.2  # Buildup during wake (hours) - Jewett & Kronauer (1999)
  ```

### Sleep Quality Factors
Seven multiplicative factors applied to raw sleep duration in `SleepBlock.effective_hours`:
1. Time of day alignment (circadian)
2. Sleep pressure (homeostatic debt)
3. Fragmentation penalty
4. Environment (home=1.0, hotel=0.88, airport_hotel=0.82, crew_rest=0.70)
5. WOCL boost (1.10 when sleep includes 02:00-06:00)
6. Jet lag penalty
7. Sleep inertia (within 30 min of wake)

### Testing Conventions
- Tests manually construct `Duty` objects with UTC datetimes
- No pytest, no fixtures, no test discovery - each file runs standalone
- Direct assertions on model outputs with explicit pass/fail printing
- Test pattern:
  ```python
  from models.data_models import Duty, FlightSegment, Airport
  duty = Duty(duty_id='D001', segments=[segment], ...)
  model = BorbelyFatigueModel()
  timeline = model.simulate_duty(duty)
  assert timeline.landing_performance > 55
  print("✅ TEST PASSED")
  ```

### API Response Contract
All `/api/analyze` responses include:
- `duties[]` with nested `sleep_blocks[]` and `performance_points[]`
- `rest_days[]` with recovery sleep
- `summary.risk_assessment` with EASA regulatory references
- `time_validation_warnings[]` for data quality issues

Frontend expects ISO format datetimes and specific field names defined in Pydantic models (`api/api_server.py`).

## Common Pitfalls

1. **Sleep overlap**: Every sleep generation path MUST call `_validate_sleep_no_overlap()` to prevent duty-sleep collisions
2. **Confidence scores**: If you constrain sleep duration, reduce `confidence_score` to 0.60-0.70
3. **Overnight duties**: Multi-day duties require `timedelta(days=1)` shifts for report times
4. **Post-duty sleep environment**: Layover = any non-home-base arrival (`'hotel'`), home base = `'home'` - generate sleep in the actual arrival timezone, not home timezone. `roster.pilot_base` is optional and usually unset, so never detect home base by comparing against it alone; fall back to the timezone.
5. **Breaking API contract**: Do not rename fields or change datetime format without updating frontend expectations. Serializers must match the dataclass — `PinchEvent` exposes `time_utc`/`performance`, not `timestamp_utc`/`performance_value`.
6. **Import paths**: After recent refactoring, imports use module paths (e.g., `from core.fatigue_model import BorbelyFatigueModel`, `from models.data_models import Duty`)
7. **pytz timezone attachment**: Never use `datetime.replace(tzinfo=pytz_zone)` — it attaches the zone's Local Mean Time offset (`+03:26` for `Asia/Qatar`, not `+03:00`). Use `tz.localize(naive)` for local wall times and `dt.astimezone(tz)` for instants.
8. **Parser time reconstruction**: Report/release and STD/STA are station-local clock times with no date. Always guard the ordering — arrival before departure, or release before report, means the value rolls to the next day.

## Regulatory Context (EASA FTL)

When implementing features, reference these regulations:
- **ORO.FTL.120** - Rest requirements (12h minimum, 8h sleep opportunity)
- **ORO.FTL.235** - Cumulative duty hours, standby periods
- **AMC1 ORO.FTL.105(10)** - WOCL definition (02:00-05:59 home base time)
- **AMC1 ORO.FTL.105(1)** - Acclimatization (±2h timezone band, 3 local nights)

## Key Files for Context

| File | Purpose |
|------|---------|
| `core/fatigue_model.py` | Main model, sleep strategies, Borbely equations |
| `core/sleep_calculator.py` | Unified sleep calculator with 5 strategies |
| `core/parameters.py` | All configurable parameters with scientific citations |
| `models/data_models.py` | All data structures, sleep quality logic |
| `api/api_server.py` | REST API, Pydantic models, endpoint definitions |
| `parsers/roster_parser.py` | PDF/CSV parsing, time validation, duty construction |
| `parsers/qatar_crewlink_parser.py` | Qatar Airways CrewLink format parser |

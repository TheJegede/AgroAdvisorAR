# F4 Dicamba — Phase 0: Rules-as-Data Foundation

**Status:** Ready to build. First phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** A versioned, effective-dated dicamba rules config + loader. No UI, no gate logic.
**Why first:** Everything downstream (`/check`, gates, record) reads from this. It is pure
transcription + a small loader — smallest, most-verifiable unit.

## Context

PRD §5 calls for a "versioned rules module — the Arkansas + federal rules stored as *data with
effective dates*, not hardcoded, so a record from June 2026 reflects the June 2026 rules even after
they change." The repo's existing config-as-data (`backend/data/alert_rules.json`, loaded by
`backend/services/alert_engine.py`) is flat with **no effective dates** — so this is genuinely new,
but the loading/caching idiom is reusable.

## Cross-cutting principles (this phase)

- Each rule record is the **full ruleset** valid for its `[effective_start, effective_end]` window;
  resolution picks the record whose window contains the query date.
- Ship **all four gates'** thresholds now (including B buffers + D equipment) so adding Gate B/D
  evaluators later needs **no rules-file migration**.
- Honesty: seeded 2026 AR specifics are **unverified** until Phase 6 attorney/Extension review —
  mark every record with `source_citation` and flag in PRD §8 open-questions.

## Files

### New: `backend/data/dicamba_rules.json`

Array of effective-dated records. `effective_end: null` = current/open-ended. Dates ISO `YYYY-MM-DD`.
Buffers in **feet** (1 mi = 5280, ½ mi = 2640, ¼ mi = 1320) so Gate B can compute numerically later.

```json
[
  {
    "rule_version": "2026-AR-OTT",
    "jurisdiction": "AR",
    "effective_start": "2026-01-01",
    "effective_end": null,
    "source_citation": "AR State Plant Board dicamba regs 2026; UA Extension MP44 — UNVERIFIED, re-confirm each season (PRD §8)",
    "season_window": {
      "start": "2026-04-15",
      "end": "2026-06-30",
      "cutoff_note": "No OTT applications after June 30 or past V4/R1, whichever first"
    },
    "buffers_ft": {
      "research_station": 5280,
      "organic_specialty": 2640,
      "non_tolerant_crop": 1320
    },
    "approved_products": [
      {"id": "engenia",   "name": "Engenia",   "epa_reg_no": "7969-345"},
      {"id": "xtendimax", "name": "XtendiMax",  "epa_reg_no": "264-1210"},
      {"id": "tavium",    "name": "Tavium",     "epa_reg_no": "100-1623"}
    ],
    "required_additives":  [
      {"id": "vra", "name": "Approved volatility-reduction agent (VRA)"},
      {"id": "dra", "name": "Approved drift-reduction agent (DRA)"}
    ],
    "prohibited_additives": [
      {"id": "ammonium_sulfate", "name": "Ammonium sulfate (AMS)"}
    ],
    "weather_thresholds": {
      "wind_mph": {"min": 3.0, "max": 10.0},
      "boom_height_ft_max": 2.0,
      "droplet_size": "Ultra Coarse or coarser (per label)",
      "time_of_day": {"earliest": "sunrise", "latest": "sunset",
                      "note": "OTT only between 1h after sunrise and 2h before sunset"},
      "rain_free_hours_required": 48,
      "air_temp_f": {"min": 50.0, "max": 91.0}
    }
  }
]
```

### New: `backend/services/spray_rules.py`

Mirror `alert_engine.py` path resolution (`Path(__file__).parent.parent / "data"`) + module-level cache.

```python
class RulesNotFoundError(Exception):
    """No rule record's effective window contains the requested date+jurisdiction."""

def _load_records(rules_path: str | None = None) -> list[dict]:
    """Load + cache dicamba_rules.json. rules_path overrides for tests."""

def resolve_rules(on_date: date, jurisdiction: str = "AR", rules_path: str | None = None) -> dict:
    """Record effective on on_date: effective_start <= on_date <= (effective_end or +inf),
    matching jurisdiction. If several match, pick latest effective_start (most recent
    supersedes). Raise RulesNotFoundError if none."""

# Pure accessors (date-free, dict in → value out):
def in_season(rules: dict, on_date: date) -> bool: ...
def approved_product_ids(rules: dict) -> set[str]: ...
def wind_bounds(rules: dict) -> tuple[float, float]: ...
def temp_bounds(rules: dict) -> tuple[float, float]: ...
def rain_free_hours_required(rules: dict) -> int: ...
```

## TDD — `backend/tests/test_spray_rules.py`

Write tests first; pass a fixture `rules_path` (small 2-record array) — no real I/O.

- `test_resolve_rules_returns_record_in_window`
- `test_resolve_rules_picks_latest_effective_start_when_overlapping`
- `test_resolve_rules_open_ended_effective_end_null`
- `test_resolve_rules_raises_when_no_window_contains_date`
- `test_resolve_rules_respects_jurisdiction`
- `test_in_season_true_within_window`
- `test_in_season_false_before_start`
- `test_in_season_false_after_end`
- `test_buffer_and_threshold_accessors_return_expected_values`

## Verification

`cd backend && pytest tests/test_spray_rules.py` — all green. Then full suite `pytest` stays at
131+ pass. No frontend/lint impact this phase.

## Out of scope

No endpoint, no gate evaluation, no UI — those are Phase 1+. Federal-vs-state precedence beyond a
single AR record is deferred (only AR jurisdiction needed for MVP).

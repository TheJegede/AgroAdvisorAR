# F3 — RWW + Palmer Amaranth Proactive County Alerts

**Date:** 2026-05-27  
**Status:** Approved  
**Approach:** Option B — Service classes + nightly orchestrator

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Farmer activity filter | 30 days | 90-day PRD default too broad for active-season relevance |
| CI execution | Direct Python in GH Actions | No cold-start risk, secrets already set |
| Redis dedup TTL | 5 days | Matches RWW "apply within 5–7 days" urgency |
| Alert CTA behavior | Pre-fill only (no auto-submit) | Farmer reviews before sending |
| GDD data source | Open-Meteo historical archive | Reuses F4 pattern, single call per county, free |

---

## Architecture

```
nightly-alerts.yml (GH Actions, 11am UTC / 6am CT)
  └── scripts/nightly_alerts.py
        ├── query farmer_profiles (last_active > 30 days)
        └── AlertEngine.run_for_farmer() per farmer
              ├── gdd_calculator.compute_gdd_since_jan1()
              │     └── Open-Meteo archive API (single call)
              ├── check Redis key alert:{farmer_id}:{pest}
              └── insert alerts row + set Redis key (5-day TTL)

Chat load → GET /api/v1/alerts → AlertBanner.jsx (above chat pane)
Dismiss   → PATCH /api/v1/alerts/{id}/dismiss
CTA click → setQuery(message) [pre-fill only]
```

---

## Section 1: Database (Migration 005)

```sql
CREATE TABLE alerts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id    uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  pest         text NOT NULL,
  county_fips  text NOT NULL,
  gdd_value    float,
  message_en   text,
  message_es   text,
  fired_at     timestamptz DEFAULT now(),
  dismissed_at timestamptz
);
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "farmer sees own alerts" ON alerts
  FOR SELECT USING (farmer_id = auth.uid());
```

**Redis dedup:** `alert:{farmer_id}:{pest}` — 5-day TTL. Set after successful insert.  
`dismissed_at = NULL` means active; timestamp means dismissed.

---

## Section 2: Backend Services

### `backend/services/gdd_calculator.py`

```python
async def compute_gdd_since_jan1(county_fips: str, base_temp_c: float = 10.0) -> float
```

- County centroid lat/lon from `backend/utils/counties.py`
- Open-Meteo: `archive-api.open-meteo.com/v1/archive`
  - Params: `temperature_2m_max`, `temperature_2m_min`, `start_date=YYYY-01-01`, `end_date=today`
  - Returns °C — no conversion needed
- `GDD_i = max(0, (Tmax_i + Tmin_i) / 2 - base_temp_c)` summed over all days
- Returns `float`

### `backend/services/alert_engine.py`

```python
class AlertEngine:
    def __init__(self, rules_path: str = "backend/data/alert_rules.json")

    async def run_for_farmer(
        self,
        farmer_id: str,
        county_fips: str,
        primary_crops: list[str],
        language: str,
        supabase,
        redis,
    ) -> list[str]  # pest keys that fired
```

Logic:
1. Load rules from JSON at init
2. Call `compute_gdd_since_jan1(county_fips)`
3. For each rule where `rule.crop in primary_crops`:
   - Check `rule.gdd_lower <= gdd` and (`rule.gdd_upper is None` or `gdd <= rule.gdd_upper`)
   - Check Redis key — skip if exists
   - Insert row into `alerts`, set Redis key with 5-day TTL
4. Return list of fired pest keys

---

## Section 3: Data

### `backend/data/alert_rules.json`

```json
[
  {
    "crop": "rice",
    "pest": "rice_water_weevil",
    "gdd_lower": 150,
    "gdd_upper": null,
    "message_en": "Rice water weevil adult emergence likely. Apply insecticide within 5–7 days of flood. See UA Extension MP144.",
    "message_es": "Emergencia probable de gorgojo acuático del arroz. Aplique insecticida dentro de 5–7 días del riego. Ver MP144."
  },
  {
    "crop": "soybean",
    "pest": "palmer_amaranth",
    "gdd_lower": 200,
    "gdd_upper": 450,
    "message_en": "Palmer amaranth germination window open. Spray now — window closes at GDD 450. See UA Extension FSA2153.",
    "message_es": "Ventana de germinación de amaranto Palmer abierta. Aplique herbicida ahora — cierra a GDD 450. Ver FSA2153."
  }
]
```

F5 (AWD) will add its rule here — no structural changes needed.

---

## Section 4: CI Workflow

### `.github/workflows/nightly-alerts.yml`

- **Schedule:** `cron: '0 11 * * *'` (11am UTC = 6am CT)
- **Steps:** checkout → `pip install -r backend/requirements.txt` → `python scripts/nightly_alerts.py`
- **Env vars (from existing GH secrets):** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`

### `scripts/nightly_alerts.py`

Orchestrator only — no business logic:
1. Query `farmer_profiles` where `last_active > now() - interval '30 days'`
2. Instantiate `AlertEngine`
3. For each farmer: call `run_for_farmer()`
4. Log total count of fired alerts

---

## Section 5: API Routes

New router: `backend/routers/alerts.py` — mounted at `/api/v1/alerts`

| Method | Path | Auth | Behavior |
|--------|------|------|----------|
| `GET` | `/api/v1/alerts` | JWT required | Undismissed alerts for current user, `fired_at DESC` |
| `PATCH` | `/api/v1/alerts/{id}/dismiss` | JWT required | Sets `dismissed_at = now()`. 404 if not farmer's. |

GET response shape:
```json
[{
  "id": "uuid",
  "pest": "rice_water_weevil",
  "message": "...",
  "gdd_value": 187.3,
  "fired_at": "2026-05-27T11:00:00Z"
}]
```

`message` = `message_es` if farmer language is `es`, else `message_en`.

---

## Section 6: Frontend

### `frontend/src/components/AlertBanner.jsx`

- Fetched on `ChatPage` mount via `GET /api/v1/alerts`
- Renders one amber Tailwind banner per active alert, above chat pane
- Dismiss: `PATCH .../dismiss` → remove from local state (no re-fetch)
- CTA "Ask about [pest]": calls `setQuery(message)` prop — pre-fills input, does not submit
- No alerts → renders nothing

---

## New Files

| File | Purpose |
|------|---------|
| `backend/supabase/migrations/005_alerts.sql` | alerts table + RLS |
| `backend/data/alert_rules.json` | pest rules (F5 reuses) |
| `backend/services/gdd_calculator.py` | Open-Meteo GDD computation |
| `backend/services/alert_engine.py` | Rule eval + Redis dedup + insert |
| `backend/routers/alerts.py` | GET + PATCH API routes |
| `scripts/nightly_alerts.py` | CI orchestrator |
| `.github/workflows/nightly-alerts.yml` | Nightly cron job |
| `frontend/src/components/AlertBanner.jsx` | Dismissible alert UI |

**No new packages required.**

---

## NIW Evidence Angles

- **Prong 1 (food security):** Time-sensitive pest warnings reduce crop loss for AR rice/soybean farmers
- **Prong 3 (public benefit):** Automated GDD-triggered alerts = quantifiable intervention events (alert_fired count, dismiss rate, CTA click-through)

# W12 Security Sprint — Design Spec

**Date:** 2026-05-16  
**PRD reference:** Phase 4, Week 12 — Integration Testing & Security  
**Approach:** Sequential by risk (OWASP → E2E → WCAG → Locust)  
**NIW purpose:** Documented security review + test coverage = petition evidence of production-grade engineering

---

## Scope

Four sequential phases executed in one sprint:

1. OWASP Top 10 audit (document + fix criticals)
2. Playwright E2E suite (15 tests + CI integration)
3. WCAG full audit on auth-gated routes (fix all violations)
4. Locust load test (local baseline + prod post-deploy)

---

## Phase 1 — OWASP Top 10 Audit

### Approach
Manual code review + `pip-audit` (Python deps) + `npm audit` (frontend deps). No external scanners. Each category gets a finding level: ✓ Mitigated / ⚠ Medium / ✗ Critical.

### Categories

| # | Category | Files to check |
|---|---|---|
| A01 Broken Access Control | Admin route enforcement, RLS bypass, JWT sub validation | `services/auth.py`, `services/admin.py`, all `routers/` |
| A02 Cryptographic Failures | JWT algorithm, PII at rest, token storage in localStorage | `services/auth.py`, frontend `AuthContext` |
| A03 Injection | Supabase client SQL safety, prompt injection sanitizer coverage gaps | `services/sanitizer.py`, `routers/query.py` |
| A04 Insecure Design | Rate limit fail-open behavior, anti-enumeration on forgot-password | `routers/auth.py`, `services/session.py` |
| A05 Security Misconfiguration | CORS origins env var, debug/reload flags in prod, error detail leakage | `main.py`, `config.py` |
| A06 Vulnerable Components | Outdated Python packages, outdated npm packages | `requirements.txt`, `package.json` |
| A07 Authentication Failures | Token expiry enforcement, refresh handling, login brute-force | `routers/auth.py`, frontend `AuthContext` |
| A08 Software/Data Integrity | CI pipeline tampering, no unsigned deserialization | `.github/workflows/` |
| A09 Logging Failures | PII leaking into logs, error detail sent to client vs logged server-side | `main.py`, all routers |
| A10 SSRF | SSURGO + NOAA URLs — are they user-controllable? | `services/context.py` |

### Output
- `docs/security/owasp-audit.md` — findings table per category (severity + evidence + fix recommendation)
- Critical findings fixed in same branch before Phase 2 begins
- Medium/Low findings documented in `owasp-audit.md` backlog section, not fixed in sprint

### Tools
```bash
# Python dep audit
cd backend && pip install pip-audit && pip-audit -r requirements.txt

# Frontend dep audit
cd frontend && npm audit
```

---

## Phase 2 — Playwright E2E Suite

### Setup

```bash
cd frontend
npm install --save-dev @playwright/test axe-playwright
npx playwright install chromium
```

Config file: `frontend/playwright.config.js`
- Base URL: `http://localhost:5173`
- Browser: Chromium only (sufficient for CI)
- Timeout: 30s per test
- `webServer`: auto-starts Vite dev server; backend must already be running on `:8000`

Test files: `frontend/e2e/`

### Environment Variables

| Variable | Used by |
|---|---|
| `TEST_EMAIL` | All auth tests + WCAG audit |
| `TEST_PASSWORD` | All auth tests + WCAG audit |
| `ADMIN_EMAIL` | Admin route tests |
| `ADMIN_PASSWORD` | Admin route tests |

### Test Suite (15 tests)

**Note on WCAG overlap:** `e2e/a11y.spec.js` runs axe-core on `/`, `/profile`, `/admin` as a CI gate on every PR. The standalone `frontend/scripts/a11y-audit.js` (Phase 3) audits 4 routes including `/admin/queue` and produces the NIW evidence report. Both are needed — the spec covers different scopes.

#### Auth group (`e2e/auth.spec.js`)
| Test | Flow |
|---|---|
| register EN → login → logout | Full auth round-trip, token stored + cleared |
| invalid login → error shown, no token | Wrong password, error message visible |
| forgot-password form → success banner | Anti-enumeration: always shows success |

#### Chat group (`e2e/chat.spec.js`)
| Test | Flow |
|---|---|
| in-scope query → advisory card renders all 7 fields | problem_summary, causes, actions, products, warnings, citations, confidence all present |
| out-of-scope query → OOS card, no advisory fields | Classifier routing verified |
| session persists across reload (`?session=<id>`) | History restored from DB |
| prompt injection attempt → sanitizer 400 → UI error shown | Sanitizer E2E coverage |

#### Feedback group (`e2e/feedback.spec.js`)
| Test | Flow |
|---|---|
| thumbs-down → comment textarea appears → submit → widget disabled | Full feedback round-trip |
| 11th feedback in 1hr → 429 banner | Rate limit UX (Redis counter) |

#### Profile group (`e2e/profile.spec.js`)
| Test | Flow |
|---|---|
| update county + crops → save → reload → values match | PATCH /profile round-trip |
| rate limit — 21st query → 429 banner visible | Query rate limit UX |

#### Admin group (`e2e/admin.spec.js`)
| Test | Flow |
|---|---|
| admin user → `/admin` loads dashboard with charts | Admin route accessible |
| non-admin user → redirected away from `/admin` | AdminRoute guard enforced |
| admin → `/admin/queue` → score a message → card disappears | Eval queue dequeue flow |

#### Mobile group (`e2e/mobile.spec.js`)
| Test | Flow |
|---|---|
| chat flow at 375px viewport | Hamburger menu, sidebar overlay, query works |

#### Accessibility group (`e2e/a11y.spec.js`)
| Test | Flow |
|---|---|
| axe-core 0 violations on `/`, `/profile`, `/admin` (authenticated) | WCAG gate in E2E suite |

### CI Integration

Add to `.github/workflows/` — new file `playwright.yml`:
- Trigger: `push` + `pull_request` to `main`
- Steps: checkout → Node setup → `npm ci` → `npx playwright install chromium` → start backend → `npx playwright test`
- Backend start: `cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000 &`
- Env vars injected from GH secrets: `TEST_EMAIL`, `TEST_PASSWORD`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, plus all existing backend secrets

---

## Phase 3 — WCAG Full Audit (Auth-gated Routes)

### Setup
Deps shared with Phase 2 — no additional install needed.

Fix ESM issue in `frontend/scripts/a11y-audit.js` if `package.json` lacks `"type": "module"` (rename to `.mjs` or add the field).

Add `/admin/queue` to routes array in the script.

### Routes
```
/           (chat — main user flow)
/profile    (profile edit)
/admin      (dashboard with charts + choropleth)
/admin/queue (eval queue with score inputs)
```

### Known Likely Violations to Pre-check
- Recharts SVG elements missing `aria-label` / `role="img"`
- Choropleth `<svg>` missing `<title>` + `role="img"`
- Eval queue 1-5 score selector missing `<label>` association
- Any `text-gray-400` applied to non-decorative text

### Process
1. Run audit → capture violations
2. Fix each violation (axe names exact element + rule)
3. Re-run → repeat until 0 violations on all 4 routes
4. Save terminal output to `docs/security/wcag-audit-result.txt`

### Run command
```bash
cd frontend
TEST_EMAIL=... TEST_PASSWORD=... node scripts/a11y-audit.js
```

---

## Phase 4 — Locust Load Test

### Setup
```bash
# Isolated from production deps
echo "locust" > backend/tests/requirements-test.txt
pip install -r backend/tests/requirements-test.txt
```

Test file: `backend/tests/locustfile.py`

### Scenarios

| Scenario | Weight | Endpoint |
|---|---|---|
| Authenticated query | 60% | `POST /api/v1/query` |
| Session list | 20% | `GET /api/v1/sessions` |
| Profile fetch | 10% | `GET /api/v1/profile` |
| Feedback submit | 10% | `POST /api/v1/feedback` |

`on_start()` hooks login with `TEST_EMAIL`/`TEST_PASSWORD`, stores JWT, attaches Bearer token to all requests.

### Two Runs

**Run 1 — Local baseline**
```bash
cd backend
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 3m --headless \
  --html docs/security/locust-local.html
```

**Run 2 — Prod (post-deploy)**
```bash
locust -f tests/locustfile.py --host=https://<railway-url> \
  --users 50 --spawn-rate 5 --run-time 3m --headless \
  --html docs/security/locust-prod.html
```

### Success Criteria
- P95 latency on `/query` < 8s (PRD §6.1 target)
- Failure rate < 1% at 50 concurrent users
- Expected bottleneck: LLM API (Gemini/Groq), not backend infra — document if confirmed

### Output
- `docs/security/locust-local.html` — Locust HTML report, local run
- `docs/security/locust-prod.html` — Locust HTML report, prod run (post-deploy)
- `docs/security/load-test-summary.md` — P50/P95/P99 + failure rate comparison table, local vs prod

---

## File Structure After Sprint

```
backend/
  tests/
    test_review_fixes.py        (existing)
    locustfile.py               (new)
    requirements-test.txt       (new — locust only)

frontend/
  e2e/
    auth.spec.js                (new)
    chat.spec.js                (new)
    feedback.spec.js            (new)
    profile.spec.js             (new)
    admin.spec.js               (new)
    mobile.spec.js              (new)
    a11y.spec.js                (new)
  playwright.config.js          (new)
  scripts/
    a11y-audit.js               (existing — fix ESM + add /admin/queue)

docs/
  security/
    owasp-audit.md              (new)
    wcag-audit-result.txt       (new)
    locust-local.html           (new)
    locust-prod.html            (new — post-deploy)
    load-test-summary.md        (new)

.github/workflows/
  playwright.yml                (new)
  nightly-eval.yml              (existing — unchanged)
```

---

## Status Bar Impact

Completing this sprint unlocks:

| Item | Delta | Source |
|---|---|---|
| OWASP review + Playwright E2E | +5% | status-bar.md item 2 |
| WCAG audit on auth-gated routes | +1% | status-bar.md item 7 |
| Locust load test (local run) | +1% | status-bar.md item 9 |
| **Overall** | **+7% → 70%** | |

Locust prod run counted inside prod deployment item (+7%) — not double-counted here.

---

## Definition of Done

- [ ] `docs/security/owasp-audit.md` written, all Critical findings fixed
- [ ] `pip-audit` + `npm audit` run, findings documented
- [ ] 15 Playwright tests pass locally against dev server
- [ ] `playwright.yml` CI workflow added, green on push to main
- [ ] axe-core 0 violations on `/`, `/profile`, `/admin`, `/admin/queue`
- [ ] `docs/security/wcag-audit-result.txt` saved
- [ ] `backend/tests/locustfile.py` written
- [ ] Locust local run complete, `docs/security/locust-local.html` saved
- [ ] `docs/security/load-test-summary.md` written (local column filled; prod column TBD post-deploy)
- [ ] Status bar updated to 68%

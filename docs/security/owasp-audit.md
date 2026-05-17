# OWASP Top 10 Security Audit — AgroAdvisor AR

**Date:** 2026-05-16
**Auditor:** Taiwo Jegede
**Codebase commit:** d947ab5
**Scope:** `backend/` (FastAPI + Python 3.11) + `frontend/src/` (React 19)

Legend: ✓ Mitigated | ⚠ Medium | ✗ Critical

---

## Dependency Scan Results

### Python (pip-audit)

```
No known vulnerabilities found
```

All backend Python packages clean. ✓

### npm (npm audit)

```
d3-color  <3.1.0
Severity: high
d3-color vulnerable to ReDoS — GHSA-36jr-mh4h-2g58
Dependency chain: react-simple-maps → d3-zoom → d3-transition → d3-interpolate → d3-color
5 high severity vulnerabilities (all same root cause)
Fix: npm audit fix --force → installs react-simple-maps@1.0.0 (breaking change — breaks choropleth)
```

**Decision:** Backlog. The ReDoS occurs in client-side SVG path parsing inside the admin-only choropleth map. No server-side user input reaches `d3-color`. Risk is Low-Medium in this context. Fix blocked by `react-simple-maps` not yet releasing a version that pins `d3-color >= 3.1.0`.

---

## A01 — Broken Access Control

**Status:** ✓ Mitigated

**Evidence:**
- `require_admin` enforced on all `/admin/*` routes via FastAPI `Depends` in `services/admin.py`
- JWT `sub` claim (server-verified, not client-supplied) used for all user-scoped DB queries
- Service-role Supabase client bypasses RLS intentionally — only used server-side, never exposed to clients; documented in CLAUDE.md
- `services/session.py:get_messages` manually filters by `user_id` even though service role bypasses RLS (defence-in-depth)
- Message ownership verified in `/feedback` before accepting rating

**Recommendation:** None required for MVP.

---

## A02 — Cryptographic Failures

**Status:** ⚠ Medium

**Evidence:**
- JWT access/refresh tokens stored in `localStorage` — accessible to JavaScript, vulnerable to XSS (known SPA tradeoff; no httpOnly cookie alternative without a backend session store)
- JWT algorithm: ES256 via JWKS for new `sb_*` tokens; HS256 legacy fallback. `alg: none` rejected by `python-jose`
- `audience="authenticated"` enforced in `jwt.decode()` — tokens without correct audience rejected
- No sensitive data (PII, farm records) stored in Pinecone — only document chunks with crop metadata

**Recommendation (Medium — backlog):** In v1.1, migrate auth to Supabase SSR client with httpOnly cookies to eliminate localStorage XSS surface area.

---

## A03 — Injection

**Status:** ✓ Mitigated

**Evidence:**
- Prompt injection: `services/sanitizer.py` rejects 10 categories of override attempts (role-override, instruction-ignore, prompt-leak, literal role tokens); 16/16 unit-test cases pass with 0 false positives
- SQL injection: all DB access via Supabase Python SDK (parameterized queries); no raw SQL f-strings found via `grep -r "f\".*SELECT\|f\".*INSERT" backend/`
- LLM output injected into UI via structured JSON (Pydantic-validated `AdvisoryResponse`), never via `innerHTML`
- Message length capped at 800 chars before reaching LLM

**Recommendation:** None required for MVP.

---

## A04 — Insecure Design

**Status:** ✓ Mitigated

**Evidence:**
- `POST /auth/forgot` always returns HTTP 200 regardless of email existence — anti-enumeration design
- Rate limit fail-open (Redis unavailable → requests pass through) — documented acceptable tradeoff; free-tier Redis; not security-critical path
- Query input capped at 800 chars before classification and RAG chain
- OOS classifier (`OUT_OF_SCOPE` category) prevents system from being used as general-purpose chatbot
- Mandatory safety warning block prepended for pesticide/chemical queries regardless of retrieved context

**Recommendation:** None required for MVP.

---

## A05 — Security Misconfiguration

**Status:** ✓ Mitigated

**Evidence:**
- CORS: `allow_origins` driven by `CORS_ORIGINS` env var (defaults to `localhost:5173`); wildcard `*` removed in prior sprint
- `.env` in `.gitignore`; `.env.example` committed with placeholder values only
- `uvicorn --reload` only used in dev; production command must omit `--reload` flag
- Error details returned to client are generic (e.g., "Invalid token", "Invalid email or password") — full errors logged server-side only

**Recommendation (Low — backlog):** Confirm `--reload` not present in Railway production deploy config. Pin GitHub Actions to commit SHA in v1.1.

---

## A06 — Vulnerable Components

**Status:** ⚠ Medium

**Evidence:**
- Python backend: 0 vulnerabilities (pip-audit clean)
- Frontend npm: 5 high-severity vulnerabilities — all `d3-color < 3.1.0` ReDoS via `react-simple-maps` dependency chain
- Fix requires breaking downgrade of `react-simple-maps` (v3 → v1), which would break the AR county choropleth

**Recommendation (Medium — backlog):** Monitor `react-simple-maps` releases for a version that resolves the `d3-color` pinning. Evaluate replacing choropleth with an alternative mapping library if not patched by MVP launch.

---

## A07 — Authentication Failures

**Status:** ✗ Critical → **Fixed in this sprint**

**Finding:** `POST /auth/login` had no rate limiting — unlimited brute-force attempts possible against any account email.

**Fix applied:** Redis rate limit added — `login_throttle:{email_hash}`, 10 attempts per 15-minute window per email address. Email SHA-256 hashed before use as Redis key (no PII in Redis). Returns HTTP 429 + `Retry-After: 900` on limit exceeded. Fails open if Redis is unavailable (documented tradeoff consistent with existing rate limits).

**Evidence after fix:**
- `backend/routers/auth.py`: `rate_limit_hit(f"login_throttle:{email_key}", 10, 900)` added before Supabase call
- `backend/tests/test_review_fixes.py`: `test_login_rate_limit_returns_429_after_10_attempts` passes

---

## A08 — Software and Data Integrity

**Status:** ✓ Mitigated

**Evidence:**
- No `pickle.loads`, `eval()`, or `exec()` of user-supplied data found in backend (`grep -r "pickle\|eval(" backend/` — zero matches in application code)
- GitHub Actions CI uses official `actions/checkout@v4` and `actions/setup-python@v5`; no self-hosted runners
- LLM structured output validated by Pydantic `AdvisoryResponse` schema before any use
- Pinecone embeddings upserted from trusted local pipeline only — no user-triggered ingestion

**Recommendation (Low — backlog):** Pin GitHub Actions steps to commit SHA (e.g., `actions/checkout@abc1234`) for supply chain hardening in v1.1.

---

## A09 — Security Logging and Monitoring Failures

**Status:** ✓ Mitigated

**Evidence:**
- JWT errors return generic `"Invalid token"` to client; full `JWTError` detail logged server-side only — verified by `test_review_fixes.py::test_decode_token_returns_generic_client_error`
- Auth errors return `"Invalid email or password"` (no distinction between wrong email vs wrong password — prevents enumeration)
- All `logger.exception` calls write to server stdout/Sentry; not forwarded in HTTP response body
- Sentry DSN optional; `traces_sample_rate=0.1` (low PII risk in trace spans)

**Recommendation (Low — backlog):** Audit Sentry breadcrumb payloads in v1.1 to confirm no PII fields (email, county FIPS, query text) captured in error traces.

---

## A10 — Server-Side Request Forgery (SSRF)

**Status:** ✓ Mitigated

**Evidence:**
- SSURGO URL hardcoded: `https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest` — not constructed from user input
- NOAA URL constructed from lat/lon in `backend/utils/counties.py` lookup table (static, not user-supplied)
- `county_fips` sourced from JWT-authenticated farmer profile — not from request body; cannot be spoofed without account compromise
- No user-supplied URLs fetched anywhere in the backend

**Recommendation:** None required for MVP.

---

## Critical Findings Fixed This Sprint

| Category | Finding | Fix applied | Commit |
|---|---|---|---|
| A07 | `POST /auth/login` had no brute-force protection | Redis rate limit: 10 attempts/15 min per email hash (`login_throttle:{sha256[:24]}`) | 975cf97 |

---

## Backlog (Medium/Low — not fixed in sprint)

| Category | Finding | Severity | Recommendation |
|---|---|---|---|
| A02 | JWT tokens in localStorage (XSS risk) | Medium | Migrate to httpOnly cookie sessions via Supabase SSR in v1.1 |
| A06 | `d3-color < 3.1.0` ReDoS in `react-simple-maps` dep chain | Medium | Monitor for react-simple-maps patch; evaluate choropleth library swap |
| A05 | `--reload` flag must be absent in prod deploy | Low | Confirm in Railway config before launch |
| A08 | GitHub Actions steps not pinned to commit SHA | Low | Pin in v1.1 for supply chain hardening |
| A09 | Sentry breadcrumbs not audited for PII | Low | Audit in v1.1 |

# ERRORS.md

Log of bugs/failures that cost real debugging time, so they do not repeat.
One entry per issue: **Symptom → Root cause → Fix → Prevention**. Newest first.

---

## 2026-06-08 — Spray-record PDF download returns `{"detail":"Not authenticated"}` (401)

**Symptom:** During the S1 prod authed walk, saving a spray record worked
(`/record` 201, `/records` list rendered) but clicking **PDF** showed
`{"detail":"Not authenticated"}`. Backend `/dicamba/record/{id}/pdf` is fine;
records persisted in prod.

**Root cause:** Frontend downloaded the PDF via a plain `<a href="/api/v1/dicamba/record/{id}/pdf">`
navigation. A browser nav carries no `Authorization` header — the JWT lives in
localStorage and is only attached by the axios client — so the authed GET reached
the backend tokenless → `get_current_user` → 401. Two spots affected:
`SprayCheckWizard.jsx` Step 4 + `SprayRecordsPage.jsx`. The drift-report PDF
(`useDriftReports.downloadPdf`) never hit this because it already fetched a blob
through axios.

**Fix:** Added `fetchSprayPdfBlob` + `downloadSprayPdf` to `hooks/useSprayRecords.js`
(axios `responseType: 'blob'` → object URL → anchor click), mirroring the working
drift path. Replaced both `<a href>` with buttons calling `downloadSprayPdf`.
TDD: `useSprayRecords.test.js` asserts the blob GET. Needs frontend redeploy
(`git push origin main` → Vercel) to go live in prod.

**Prevention:** Any authed file download must go through the axios client (blob),
never a plain `<a href>`/`window.open` to an auth-gated endpoint — those send no
Bearer token.

---

## 2026-06-06 — E2E Playwright: injectAuth specs redirect to /login in CI (textarea/aside timeouts)

**Symptom:** ~10/22 Playwright e2e tests fail in CI only. `submitQuery` times out
waiting for `textarea` (30s); other tests time out on `aside`; `profile.spec`
never reaches `/profile`. Passes locally. Generic "add explicit waits" advice does
NOT fix it (the page has already navigated to `/login` — waiting longer never helps).

**Root cause:** Commit `c9a9c94` switched chat/profile/feedback/mobile from real
`loginAs` to `injectAuth`, which seeds a **fake** `access_token`. In CI, the
workflow starts a real uvicorn on :8000 and vite proxies `/api` there. Any on-load
authenticated GET a spec did not mock — Sidebar `GET /sessions` + `GET /profile`
(useProfile), ChatPage AlertBanner `GET /alerts` — hits the real backend and 401s
the fake token. `frontend/src/lib/api.js` response interceptor redirects ANY
non-`/auth` 401 via `window.location.href='/login'` (fires before the hook's local
`.catch`), so the page never renders. CI-only because locally there is no 401
backend (proxy ECONNREFUSED ≠ 401), so the interceptor's `status===401` branch
never fires — classic green-local / red-CI.

**Fix:** Added `mockAppShell(page)` in `frontend/e2e/helpers.js` stubbing the three
always-loaded authed GETs (`/sessions`, `/profile`, `/alerts`); called right after
`injectAuth` in every mocked spec. Switched `mockChatBackend`'s `/sessions`
non-POST guard from `route.continue()` (→network) to `route.fallback()` (→shell
stub). Commit `59fb365`.

**Prevention:**
- Any e2e spec using `injectAuth` MUST also call `mockAppShell(page)` immediately
  after. Fake token + real CI backend = 401 on every unmocked authed GET.
- When adding a new on-mount `api.get` to a component rendered inside the
  authenticated layout (Sidebar/ChatPage), add it to `mockAppShell`.
- Use `route.fallback()` (not `route.continue()`) in spec mocks when you want
  unhandled methods/paths to fall through to other registered handlers; Playwright
  runs route handlers LIFO, and `continue()` skips straight to the network.
- To reproduce CI 401 locally: run a 401-everything stub on a free port, point the
  vite proxy at it, and run specs on a clean vite port (5173/8000 may be squatted
  by another local project).

---

## 2026-06-06 — E2E Playwright: flaky chat/profile failures from Supabase auth rate-limit

**Symptom:** Intermittent CI failures where late tests stay on `/login` and
`waitForURL('/')` times out.

**Root cause:** Every `loginAs()` in `beforeEach` hit `POST /auth/login` →
Supabase `signInWithPassword`, ~15×/run (2 workers × retries). Supabase auth
rate-limits, so later logins failed.

**Fix (commit `c9a9c94`):** Reuse the `injectAuth` pattern (seed token in
localStorage; `ProtectedRoute` only checks token presence) for fully-mocked specs;
keep real logins only in `auth.spec` (login flow) and `admin.spec` (real backend).
~15 → ~6 logins/run, under the limit. (Note: this fix introduced the 401-redirect
issue above — see that entry.)

**Prevention:** Do not perform real Supabase logins per-test in mocked specs; seed
auth via `injectAuth` and mock the backend.

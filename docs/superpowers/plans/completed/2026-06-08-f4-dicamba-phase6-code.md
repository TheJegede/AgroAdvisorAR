# F4 Dicamba — Phase 6 (CODE): Disclaimer Surface + Gate Instrumentation

**Status:** Plan. Code-only slice of Phase 6 (split from `2026-06-08-f4-dicamba-phase6-legal-pilot.md`).
**Sibling:** `2026-06-08-f4-dicamba-phase6-nocode.md` (attorney engagement + pilot recruitment — no code).
**Ships:** Implementable now, no external blocker. Disclaimer wording uses an honest default that the
attorney can later revise (the no-code track); the *surface* (where/how it renders) is built here.

## Context

Phase 6 (`AgroAdvisor_F4_PRD_v3.md` §4/§8/§10) gates public use on legal review + a pilot. Most of that
is human work (no code). But three slices are pure code and have **no dependency on the attorney**:

1. The disclaimer *surface* — where a "Not legal advice / you, the licensed applicator, decide"
   disclaimer renders. Final wording comes from the attorney (no-code track), so author it as a single
   centralized string the attorney can swap without touching layout.
2. Per-gate instrumentation — capture which gates pass/fail/need-confirmation so the pilot can measure
   real-world usefulness (PRD §7, no-code Open Question 3).
3. In-app pilot feedback widget — collect applicator feedback in the wizard.

PRD §10: the tool's limits (inversion *estimate*, registry blind spot) are the asset. Disclaimer copy
must keep that honesty — "surface requirements, you decide," never "recommend application."

## Scope (code)

### 1. Disclaimer surface (centralized, attorney-swappable)
- Single source of truth string (EN + ES) — e.g. `frontend/src/lib/disclaimers.js` or i18n key
  `t.sprayDisclaimer`. Honest default text; one place for the attorney to revise wording later.
- Render persistent disclaimer banner in `SprayCheckWizard.jsx` (every step) + `SprayCheckPage`.
- Render disclaimer in the PDF record: `services/pdf_generator.generate_spray_record_pdf` — backend
  needs its own copy of the canonical wording (mirror constant, single source per stack).
- HC badge / `min-h-touch` consistency with rest of wizard.

### 2. Per-gate instrumentation
- Capture per-check + per-gate outcome (`pass`/`fail`/`needs_confirmation`, `tier`) at `/check` and
  `/record` time. Decide store: extend `spray_records` snapshot (already immutable) vs lightweight
  analytics event table. Prefer reusing the frozen record snapshot — no new mutate surface.
- Anonymized/aggregatable so pilot can answer "which gate blocks most often."

### 3. In-app pilot feedback widget
- Small feedback control on the result step (Step 4) — thumbs / short text → persisted.
- EN/ES, accessible.

## Verification (TDD)

- Disclaimer present on every wizard step + page + PDF; flips EN↔ES; single-string swap changes all
  surfaces (test the centralization).
- Instrumentation: `/check` + `/record` responses/records carry per-gate outcome; existing
  `test_spray_check.py` / `test_spray_record.py` extended, immutability preserved.
- Feedback widget: vitest for render + submit; e2e happy path.
- Full suites green (backend pytest, frontend vitest, playwright); `npm run lint`.

## Out of scope (-> no-code track)

- Final disclaimer wording (attorney-supplied).
- Attorney sign-off checklist; pilot recruitment / Extension outreach.
- Deciding *which* metrics matter (no-code Open Question 3) — code captures broadly; analysis is human.

## Dependencies

- None external. Honest-default wording lets this ship before the attorney engagement.
- Note (carried from Phase 4/5 deferred ops): live HF Space is pre-F4, so `/dicamba/*` 404 in prod
  until backend redeploy + migration 009. This code lands in repo regardless; prod visibility waits on
  that redeploy.

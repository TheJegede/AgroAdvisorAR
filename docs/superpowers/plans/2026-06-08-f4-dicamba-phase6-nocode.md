# F4 Dicamba — Phase 6 (NO-CODE): Legal Review + Pilot

**Status:** Outline. No-code slice of Phase 6 (split from `2026-06-08-f4-dicamba-phase6-legal-pilot.md`).
**Sibling:** `2026-06-08-f4-dicamba-phase6-code.md` (disclaimer surface + instrumentation — code).
**Ships:** Attorney sign-off + pilot. Blocked on external human engagement (no code).

## Context

PRD `AgroAdvisor_F4_PRD_v3.md` §4 + §8: before any public use, advisory framing + disclaimers must be
reviewed by an attorney familiar with **Arkansas pesticide law**. In some states, *recommending* a
pesticide application is itself a regulated activity — exactly why the tool surfaces rules rather than
recommending. PRD §10: keep every claim honest; the tool's limits (inversion estimate, registry blind
spot) are the asset, not a liability.

## Scope (no code)

### 1. Legal review
- Engage an AR pesticide-law attorney.
- Review every outcome banner, disclaimer, confirmation prompt, and the generated record's language.
- Confirm the tool never crosses from "surface requirements" into "recommend application."
- **Output -> code track:** final disclaimer wording, fed into the centralized string built in
  `2026-06-08-f4-dicamba-phase6-code.md` (one-string swap, no layout change).

### 2. Pilot
- Put the finished flow in front of real applicators (PRD §7 / Priorities #3: 20 users, 500 queries).
- Recruit via Extension outreach (CLAUDE.md "Not Built / Pending").
- Gather feedback (in-app widget built on the code track) + analyze gate instrumentation.

## Verification

Attorney sign-off checklist complete; final disclaimer wording delivered to code track; pilot
recruitment + feedback loop running.

## Open questions

- Attorney selection + scope of engagement.
- Pilot recruitment channel (Extension outreach).
- Which per-gate metrics evaluate real-world usefulness (code track captures broadly; this track
  decides what to analyze).

## Also-pending ops (carried, owner-blocked — not Phase 6 proper but gate prod pilot)

From PROGRESS.md "Deferred Ops": apply migration `009` to prod Supabase; HF backend redeploy (live
Space still pre-F4 -> `/dicamba/*` 404 in prod); verify station coords (**UNVERIFIED** at source);
external APIs (FieldWatch registry pull, EPA Bulletins layer, mesonet delta-T inversion).

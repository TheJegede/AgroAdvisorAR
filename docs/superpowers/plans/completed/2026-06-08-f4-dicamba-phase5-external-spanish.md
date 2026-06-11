# F4 Dicamba — Phase 5: External Data + Spanish Parity

**Status:** SCOPED 2026-06-08 (owner decision). Sixth phase of `AgroAdvisor_F4_PRD_v3.md`.

**Scope split (owner decision 2026-06-08): build the in-codebase SAFETY SLICE now; defer the
external-API integrations (need owner to obtain access) alongside the Phase-4 deferred ops.**

- **BUILD NOW (safety slice):**
  1. **Spanish parity** — every gate `title`/`label`/`reason` + outcome banner + disclaimer authored
     bilingual (EN+ES), not machine-translated at runtime. Closes the confirmed gap: backend gate
     strings rendered English even in ES mode (`CheckResult.label`/`.reason`, `GateResult.title`).
  2. **Soil-saturation Gate C check** — `weather_now` already returns `soil_moisture_0_1cm`; promote it
     from raw-value-only to a real Gate C check (rules-as-data threshold, `needs_confirmation` when
     unavailable — never a guessed pass).
  3. **Deep-link + human-attested fallbacks** for FieldWatch (FieldCheck) + EPA Bulletins Live! Two —
     no API needed; the applicator opens the official map and confirms. Bilingual.
- **DEFERRED (owner-blocked — contact providers; park with Phase-4 deferred ops):** FieldWatch registry
  *API* pull → `sensitive_sites` cache; EPA Bulletins geospatial *layer* integration; mesonet/delta-T
  inversion *measurement* source. Until obtained, the deep-link + `human_attested` confirmation stands.

**Ships:** full Spanish parity on every gate string + disclaimer; a real soil-saturation Gate C check;
bilingual deep-link fallbacks for the registries.

## Context

PRD §6 reliability tiers + §8 open questions. The registry data is **partial** by nature (voluntary);
honesty about the blind spot is the asset (PRD §10 NIW note). Spanish parity is **non-negotiable** for
the safety story — the audience includes Spanish-speaking applicators least able to second-guess a
false green light.

## Scope

- **FieldWatch:** investigate API vs manual lookup / FieldCheck alerts — **contact them directly**
  (PRD §8). If pullable → new `sensitive_sites` cache table (organic/specialty/non-tolerant registries)
  feeding Gate B's `verifiable`/`partial` checks. If not → keep deep-link + `human_attested` confirmation.
- **EPA Bulletins Live! Two:** integrate the geospatial layer, or deep-link the applicator to it
  (decide based on API availability).
- **Inversion upgrade:** check for an Arkansas mesonet / delta-T (two-height temp difference) source to
  move the inversion `estimate` toward a `measurement`. If found, feed `weather_now._estimate_inversion`
  a real delta-T; otherwise keep the heuristic, still labeled `is_estimate`.
- **Soil saturation:** pick Open-Meteo soil-moisture model vs recent-rainfall proxy; wire the chosen
  one into a real Gate C check (was raw-value-only in Phase 1).
- **Spanish parity:** full pass on every gate label, reason string, confirmation prompt, outcome banner,
  and disclaimer — EN + ES. Use the translate-bridge infra (`services/translation.py`) only where
  dynamic; gate copy should be authored bilingual, not machine-translated at runtime.

## Verification

Integration tests against any new data source (mocked); Spanish snapshot/visual review of every wizard
string; confirm `is_estimate` labeling survives any inversion-source upgrade.

## Open questions (PRD §8 — must resolve here)

- FieldWatch access model; EPA Bulletins integrate-vs-deeplink; mesonet delta-T availability;
  soil-saturation source choice. All flagged unverified until resolved.

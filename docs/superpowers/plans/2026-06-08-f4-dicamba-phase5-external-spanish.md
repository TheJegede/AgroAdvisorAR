# F4 Dicamba — Phase 5: External Data + Spanish Parity (OUTLINE)

**Status:** Outline. Detail when Phase 4 ships. Sixth phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** Real sensitive-site data (where available) + full Spanish parity on every gate string and
disclaimer.

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

# F4 Dicamba — Phase 6: Legal Review + Pilot (OUTLINE)

**Status:** Outline. Final phase of `AgroAdvisor_F4_PRD_v3.md`. Gates public use.
**Ships:** Attorney-reviewed advisory framing + disclaimers, then a pilot with real applicators.

## Context

PRD §4 + §8: before any public use, the advisory framing and disclaimers must be reviewed by an
attorney familiar with **Arkansas pesticide law** — in some states, *recommending* a pesticide
application is itself a regulated activity, which is exactly why the tool surfaces rules rather than
recommending. PRD §10: keep every claim honest; the tool's limits (inversion estimate, registry blind
spot) are the asset, not a liability.

## Scope

- **Legal review:** engage an AR pesticide-law attorney to review every outcome banner, disclaimer,
  confirmation prompt, and the generated record's language. Confirm the tool never crosses from
  "surface requirements" into "recommend application."
- **Disclaimer surface:** add a persistent "Not legal advice / you, the licensed applicator, decide"
  disclaimer to the wizard and the PDF record (per the attorney's wording).
- **Pilot:** put the finished flow in front of real applicators (PRD §7 / Priorities #3: 20 users,
  500 queries scale as the broader pilot target). Gather feedback; instrument the gate flow.

## Verification

Sign-off checklist from the attorney; disclaimer present on every surface (wizard + PDF); pilot
recruitment + feedback loop running.

## Open questions

- Attorney selection + scope of engagement.
- Pilot recruitment channel (Extension outreach per CLAUDE.md "Not Built / Pending").
- Metrics to capture per gate to evaluate real-world usefulness.

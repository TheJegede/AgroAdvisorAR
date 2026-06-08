# AgroAdvisor AR — F4 Product Requirements (v3)
## Dicamba spray-compliance decision support

**Status:** Draft for build. Supersedes the F4 "dicamba drift documentation" scope in PRD v2.0.
**Audience:** Solo builder (you). Written to be read top to bottom — the early sections explain, the later sections specify.
**One-line summary:** A *before-you-spray* checklist that tells an applicator what the dicamba rules require and what current conditions are, helps them decide whether to spray, and produces a defensible record of that decision.

> **How to read this:** Sections 1–4 explain *what* and *why* in plain English, no code. Sections 5–8 are the build plan. If you only read two things, read **Section 1** (what it is) and **Section 7** (what to do next).

---

## 1. What this feature is (plain English)

### A 30-second primer on the problem
Dicamba is a cheap, effective weedkiller that kills broadleaf weeds — including the pigweed (Palmer amaranth) that has become resistant to almost everything else. The catch is that it also kills broadleaf *crops*, and it moves. It can blow sideways during spraying, and worse, it can evaporate off the field hours after a correct application and drift — especially during a *temperature inversion*, a calm, cool layer of air near the ground at dawn or dusk that traps the vapor and carries it laterally. So one farmer's legal weed control can damage a neighbor's non-resistant soybeans, garden, or orchard. Arkansas has been the center of this fight for a decade. The rules are strict, specific to the state, change from season to season, and carry civil penalties up to **$25,000 per violation** plus possible loss of the applicator's license.

### Old F4 vs. new F4
The **old F4** was a *form that produced a PDF about a spray or drift event*. You opened it, it pulled in the weather, you filled in some fields, and it handed you a document for your records. The document was the point, and you used it *after* the fact.

The **new F4** is a *checklist you run before you spray*. It answers a different question: "Should I spray this field right now, and what has to be true for that to be legal and safe?" The decision is the point; the record is a byproduct that the tool generates as you go.

The difference is just *when* you use it and *what question it answers*:

- **Old** → "I sprayed, or I got hit by drift — make me a record." Backward-looking.
- **New** → "Should I spray this field right now, and what must be true for that to be okay?" Forward-looking.

**Analogy:** the old F4 is a *receipt* — printed after the fact as proof. The new F4 is a *pilot's pre-flight checklist* — run before takeoff to decide whether it's safe to fly, with the logbook entry created automatically just by running it.

---

## 2. Why we changed it

- The real pain — and the $25,000 risk — lives in the decision moment at 6 a.m., not in the paperwork afterward.
- Documenting drift after it happened doesn't prevent harm. Helping the decision does.
- It is the strongest version for the project's safety mission and the NIW story: a tool that helps a (often Spanish-speaking) applicator navigate complex compliance rules has clear, demonstrable public benefit.
- It is **not a rebuild.** It reuses roughly 70% of what F4 already has (see Section 5). The cost is reorganization plus some new logic and data, not starting over.

---

## 3. How it works — the four gates

The tool walks four checks in order. Think of them as four questions, each of which has to clear before the tool will say "this meets the requirements." This *is* the new F4 — the four gates are the feature.

**Gate A — Legal window** *(Can you legally spray at all, on paper?)*
Is today inside the season window (April 16–June 30 in Arkansas for the 2026 season)? Is the applicator licensed and current on the required annual dicamba training? Is the product one of the approved over-the-top products? → Mostly a rules lookup plus the applicator confirming their license.

**Gate B — Field & buffers** *(Is this field clear of protected neighbors?)*
Is the field far enough from the things the rules protect: one mile from university/USDA research stations, half a mile from certified organic and specialty crops, a quarter mile from non-dicamba-tolerant crops? → A map plus sensitive-site data, plus an applicator confirmation for the things we can't see.

**Gate C — Weather now** *(Are conditions safe this hour?)*
Is wind between 3 and 10 mph? Is there a temperature inversion? Is it the right time of day (not within an hour after sunrise or two hours before sunset)? Is rain forecast within 48 hours? Is the soil saturated? Is the temperature in range? → Mostly your existing weather feed. **Important:** inversion is a *risk estimate*, not a measurement (see callout below).

**Gate D — Equipment & target** *(Is the rig set up right, and is anything downwind?)*
Coarse-or-coarser droplets, boom height no more than 2 feet, required tank additives present (and no prohibited ones), no aerial application, and nothing sensitive in the *current* downwind direction. → An applicator checklist plus wind direction combined with the Gate B geography.

**Outcome:**
- All four clear → "Meets the requirements you confirmed" + generate the record.
- Any gate fails, or an unverifiable item isn't confirmed → "Not clear — here's why" + log the no-go decision.

> **The one principle that governs the whole feature:** the tool never invents certainty. Where it can verify something (dates, distance to a known site, wind speed), it states a fact. Where it can't (whether an inversion is actually happening, whether an unregistered neighbor planted non-tolerant beans), it asks the applicator to confirm and records their answer. It does **not** pretend to know. This is the same philosophy as the citation guard: surface what's grounded, flag what isn't, and abstain loudly rather than guess.

---

## 4. Advisory, not decision-maker (a design rule, not a detail)

The tool *surfaces requirements and conditions*; the human *decides*. It never says "Approved — spray now." It says "Here is what the rules require, here are the current conditions and the sensitive sites near you, and here is the record of what you confirmed — you, the licensed applicator, make the call."

Why this matters, in plain terms:

- The licensed applicator is the one who is legally responsible, not the software. Keeping them as the decision-maker matches reality.
- Two of the four gates depend on facts the tool genuinely cannot verify (the inversion, the unregistered neighbor). Claiming a confident "yes" on those would be dishonest *and* dangerous — most dangerous for the worker least able to second-guess a green light.
- This framing also lowers your own exposure and makes a cleaner public-benefit story.

The generated record therefore documents *the human's decision and what they confirmed* (e.g. "applicator confirmed no non-tolerant crop within ¼ mile"), not a boolean "the tool said go."

> **Not legal advice.** Before launch, have the advisory framing and disclaimers reviewed by an attorney familiar with Arkansas pesticide law. In some states, *recommending* a pesticide application can itself be a regulated activity — another reason the tool surfaces the rules rather than recommending a course of action.

---

## 5. What we reuse vs. what we build

You already have most of the parts. The work is repointing them.

**Reuse (already built):**

| Existing piece | New role |
|---|---|
| 3-step wizard UI | The gate flow — step 1 = eligibility (Gates A+B), step 2 = live conditions (Gate C), step 3 = attest + record (Gate D) |
| Open-Meteo auto-fill | Powers Gate C. Extend it to also pull wind *direction*, soil moisture, and compute sunrise/sunset locally |
| Arkansas county choropleth | Becomes the Gate B proximity map — draw the buffer rings, research stations, and sensitive sites around the field |
| ReportLab PDF generator | Becomes the record generator — same library, new template with attestation fields |
| Supabase | Stores the records. Row-level security is now critical (these are legally significant). Build on the IDOR-write fix already shipped |
| FastAPI backend | Hosts two new endpoints (see below) |

**New (to build):**

- A **versioned rules module** — the Arkansas + federal rules stored as *data with effective dates*, not hardcoded, so a record from June 2026 reflects the June 2026 rules even after they change.
- New tables: `spray_records`, `sensitive_sites` (cached), `rules_versions`.
- Two endpoints: `POST /api/v1/dicamba/check` (given field + product + datetime, return per-gate results) and `POST /api/v1/dicamba/record` (generate + persist the record).
- The gate-evaluation logic itself.

---

## 6. Data sources and reliability tiers

Each gate's data falls into one of three tiers. The tier tells you how the tool should *talk* about that check.

| Gate | What it needs | Source | Tier |
|---|---|---|---|
| A — legal window | cutoff dates, license/training, approved product | rules config + applicator attestation | Verifiable (config) + Human-attested (license) |
| B — field & buffers | distance to research stations / organic-specialty / non-tolerant crops | static station list · FieldWatch registries + EPA Bulletins Live! Two · unregistered neighbors | Verifiable (stations) + Partial (registries) + Human-attested (the rest) |
| C — weather now | wind speed + direction, inversion, time of day, 48h rain, soil moisture, temp | Open-Meteo + solar calculation | Verifiable (wind/timing/rain/temp) + Estimate only (inversion) |
| D — equipment & target | droplet size, boom height, additives, no aerial, downwind sensitive | applicator attestation + wind direction × Gate B | Human-attested + Verifiable (downwind geometry) |

- **Verifiable** → the tool states it as fact.
- **Partial** → the tool shows what it found and notes the data is incomplete (registries are voluntary; an unregistered neighbor is invisible).
- **Estimate / Human-attested** → the tool asks the applicator to confirm and records the answer; it never asserts it.

---

## 7. Build sequence — what to do next

This is the answer to "what's the overall plan." Each phase ships something testable, so you always have a working tool and never face the whole thing at once. Build smallest and most-verifiable first.

**Phase 0 — Write the rules as data (no UI, no code logic yet).**
Encode the current Arkansas + federal dicamba rules into a structured, effective-dated config file: the season window, buffer distances, approved products, weather thresholds. This is mostly transcription from the label and the Arkansas Department of Agriculture guidance. It is the foundation everything else reads from.

**Phase 1 — The `/check` endpoint, easy gates first.**
Given a field, product, and datetime, return structured per-gate results. Start with **Gate A** (rules lookup) and **Gate C** (your Open-Meteo feed). Skip the map and FieldWatch for now. Cover it with your existing pytest setup.

**Phase 2 — Reshape the wizard to the 3-step gate flow, wired to `/check`.**
Now it works end-to-end with the easy gates. A user can walk it and get a real answer.

**Phase 3 — Gate B map.**
Repoint the choropleth to a field-level proximity view: buffer rings plus the static research-station list. Add applicator-confirmation prompts for the parts the tool can't see (non-tolerant neighbors).

**Phase 4 — The record generator.**
Build `/record` and the new PDF template with attestation fields, and persist to Supabase with row-level security. This is where "the record is a byproduct" becomes real.

**Phase 5 — External data + Spanish parity.**
Investigate whether FieldWatch offers an API or only manual/alert access; integrate or deep-link EPA Bulletins Live! Two. Do a full Spanish pass on every piece of copy and every disclaimer — parity here is non-negotiable for the safety story.

**Phase 6 — Legal review, then pilot.**
Attorney review of the advisory framing and disclaimers, then put it in front of real applicators.

---

## 8. Open questions — verify before relying on these

- **Current-season Arkansas label specifics** (exact approved-product list, required adjuvants, any tank-mix prohibitions): re-confirm from the Arkansas Department of Agriculture and the product label *each season*.
- **FieldWatch access:** does it expose an API, or only manual lookup / FieldCheck alerts? Contact them directly.
- **EPA Bulletins Live! Two:** integrate the geospatial layer, or deep-link the applicator to it?
- **Inversion data:** is there an Arkansas mesonet or other source reporting a two-height temperature difference (delta-T) that could upgrade the risk *estimate* toward a measurement?
- **Soil saturation:** Open-Meteo soil-moisture model vs. a recent-rainfall proxy — pick one.
- **Legal:** advisory framing and disclaimers reviewed by an Arkansas pesticide-law attorney before any public use.

---

## 9. Scope for MVP

**In:** Arkansas rules; the four gates with the verifiable ones automated and the rest human-confirmed; record generation; advisory framing; English + Spanish.

**Out (later):** full automated FieldWatch integration; other states; herbicides other than dicamba; real on-farm inversion sensors.

---

## 10. NIW note (brief)

Reframed, F4 directly serves a documented national problem (dicamba drift) with an explicit safety dimension for Spanish-speaking applicators — strengthening the "substantial merit and national importance" argument. Keep every claim honest: the tool's limits (the inversion estimate, the registry blind spot) are documented in Sections 3 and 6 and should be presented as such, not papered over. That candor is the asset, not a liability.

---

*This document supersedes the F4 section of `AgroAdvisor_AR_PRD_v2.md`. Detailed project history lives in `PROGRESS.md`; bug forensics in `ERRORS.md`.*

# F4 Dicamba — Phase 4: Record Generator + Gate D (OUTLINE)

**Status:** Outline. Detail when Phase 3 ships. Fifth phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** `POST /api/v1/dicamba/record` — persist the decision + generate a PDF record; plus Gate D
(equipment & target). This is where "the record is a byproduct" becomes real.

## Context

PRD §4: the record documents **the human's decision and what they confirmed**, not a boolean "the tool
said go." PRD §5: reuse ReportLab + Supabase; RLS is now critical (legally significant records). Build
on the shipped IDOR-write fix pattern (`backend/services/session.py add_message`: service-role client +
manual `farmer_id` filter + ownership gate before write).

## Scope

- **Migration (new, next NNN):** table `spray_records` — `id`, `farmer_id` (FK `farmer_profiles`,
  cascade), `created_at`, field lat/lon, product, `applied_at`, `overall_status`, `rule_version`, JSONB
  `gates` (per-gate results), JSONB `attestation`. RLS: `farmer_id = auth.uid()` (mirror migration 006
  `drift_reports`). Immutable (no `updated_at`).
- **Service:** `services/spray_record.py` — `create_record(farmer_id, payload)` via `_get_service_client()`
  with manual `farmer_id` (never client-supplied) + ownership-gate idiom; `get_record(id, farmer_id)`
  filtered by both.
- **Gate D:** `evaluate_gate_d(rules, req)` appended to `services/spray_check.py` — droplet size, boom
  height ≤ 2 ft, required additives present, prohibited absent, no aerial = mostly `human_attested`
  (→ `needs_confirmation` unless attested); downwind-sensitive = `verifiable_fact` (wind direction ×
  Gate B geometry). Attestation fields already reserved in `ApplicatorAttestation` (Phase 1).
- **PDF:** `generate_spray_record_pdf(record, farmer_profile)` in `services/pdf_generator.py` idiom —
  new template with attestation fields, per-gate outcomes, rule_version + timestamp, advisory/"not
  legal advice" framing.
- **Endpoint:** `POST /api/v1/dicamba/record` (auth, `user["sub"]`) → run check, persist, return record
  + PDF link; `GET /api/v1/dicamba/record/{id}/pdf` to stream.

## TDD (sketch)

- Service: fake Supabase client; create stamps `farmer_id` from JWT; IDOR ownership gate rejects
  foreign read/write; immutability.
- Gate D: each attested item pass vs `needs_confirmation`; downwind-sensitive geometry pass/fail.
- PDF: valid `%PDF` bytes; handles missing weather/empty profile (mirror `test_pdf_generator.py`).
- Router: auth required; uses authenticated owner.

## Verification

Apply migration to a Supabase branch; pytest service + PDF + router; manual: complete a check, save,
download the PDF; confirm a second user cannot read the first's record (RLS + app gate).

## Open questions

- Exactly which gate snapshot to freeze in the record (resolved rules already versioned via
  `rule_version`). Retention/export needs for legal defensibility.

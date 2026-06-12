# Lever (a): Token-Streaming the Advisory (perceived-latency)

## Context

Guard-trim (lever c) shipped — prod guard now ~1s (was 14–26s). The remaining
wall-clock is **generation: 18s Groq 70B / 45–50s DeepInfra** (`RunnableSequence`
in LangSmith). It cannot be made shorter without a model swap (deferred, cost).
The win left is **perceived** latency: show the advisory as it generates instead
of one blob after 18s.

**Decisions (brainstorm 2026-06-10):**
- **Show provisional content during generation**, badged "verifying…", then
  reconcile with the guard result (confirm, or replace with suppression notice).
- **Mechanism = partial-JSON field streaming.**

**Enabling tech (verified):** langchain-core 1.4 `JsonOutputParser` yields
progressively-complete partial dicts under `.astream()`. Path is
`(llm | JsonOutputParser()).astream(messages)` — NOT
`with_structured_output(...).astream()` (emits one final object). Final dict is
validated to `AdvisoryDraft` at stream end, preserving the schema contract.

## Architecture

```
generate (astream)  →  partial dicts  →  SSE {"partial": {...}}  →  card fills live (badge: verifying)
   (18s)                                                              ↑ provisional
   ↓ stream ends, validate AdvisoryDraft
guard (_postprocess_async, ~1s)         →  SSE {"advisory": {...}}  →  card reconciles (verified / suppressed)
                                                                       ↑ authoritative
```

The existing post-gen guard + final `advisory` frame are UNCHANGED — they remain
the single source of truth. Partial frames are additive and always superseded by
the final frame. Suppression still blanks the body in the final frame; the
frontend clears any provisional content when the final frame says `suppressed`.

### Scope guards
- **EN only.** Spanish translation is post-gen (`translate_advisory_to_es`);
  streaming EN partials then swapping to an ES final is confusing. ES keeps the
  current non-streaming path (progress text only). Gate streaming on `language=="en"`.
- **Streaming provider only.** Partial streaming runs for the Groq/DeepInfra/Gemini
  chain. If `astream`/partial-parse fails for any reason, fall back to the current
  `ainvoke` non-streaming path (no partial frames, same final frame). Streaming is
  a pure enhancement — never a new failure mode.
- **Cache hits** (L3) and **suggested/cached** answers skip streaming (already instant).

## Backend changes

`backend/services/rag.py`
- New helper `_astream_draft(llm, messages, run_config, on_partial)` — pipes the
  raw model through `JsonOutputParser`, `async for` over partials, calls
  `on_partial(partial_dict)` for each, accumulates the last full dict, returns it.
  DeepInfra branch keeps the json_mode format-instructions prepend; Gemini/Groq use
  the plain prompt (already instructed for JSON by the structured schema).
- Generation loop: when `stream=True` and provider supports it, use
  `_astream_draft` with an `on_partial` that pushes `{"partial": <draft>}` onto the
  progress queue; else current `ainvoke`. Validate the final dict to `AdvisoryDraft`
  (raise → provider fallback, same as today). Guard + return unchanged.
- `run_rag_query(..., stream: bool = False)` — caller sets it.

`backend/routers/query.py`
- Pass `stream = (language == "en" and cache_key-miss and not suggested)` into
  `run_rag_query`.
- The `event_stream` queue drain already forwards queue items; add a branch so a
  queue item tagged `partial` is emitted as `data: {"partial": {...}}` while
  `progress` items stay `data: {"progress": {...}}`. Final `advisory` + `[DONE]`
  frames unchanged. (Decide queue item shape: wrap as `{"kind":"partial"|"progress", ...}`.)

## Frontend changes

`frontend/src/hooks/useSSEQuery.js`
- `consumeSSEStream`: route `parsed.partial` → `onPartial(draft)`; keep `parsed.progress`
  → `onProgress`, `parsed.advisory` → `onResult`. `isAdvisoryFrame()` must treat a
  partial as NOT a final advisory.
- Expose `onPartial` through `sendQuery`. Track a `provisional` draft in state,
  cleared/replaced when the final `onResult` arrives.

`frontend/src/components/...AdvisoryCard.jsx` (+ ChatPage wiring)
- Render a provisional card from the partial draft: fields appear as they arrive,
  a "Verifying…" badge replaces the confidence/NLI badges, sources hidden.
- On final advisory: swap to verified card (confidence, NLI, sources) or, if
  `suppressed`, the suppression notice — provisional body cleared.
- `hasRenderableContent()` updated so a partial with any field renders, an empty
  partial does not (deploy-skew safety, consistent with existing hardening).

## TDD task breakdown

0. **Spike (throwaway):** local script — `(groq_llm | JsonOutputParser()).astream(advisory_messages)`
   prints partial dicts growing field-by-field. Confirms granularity before building.
   Delete after.
1. **Backend `_astream_draft`** — test: a fake astreaming LLM emitting JSON token
   chunks yields ≥2 partial callbacks then a final dict equal to the parsed whole;
   final validates to `AdvisoryDraft`.
2. **Backend gen loop streaming + fallback** — test: `stream=True` pushes ≥1 `partial`
   queue item then returns the same advisory as `stream=False`; a provider that
   can't astream falls back to `ainvoke` with zero partial items, same final result.
3. **Router EN-gate + frame forwarding** — test: EN query emits `partial` SSE frames
   before the `advisory` frame; ES query emits NONE (progress only); final `advisory`
   + `[DONE]` always present.
4. **Frontend `consumeSSEStream` partial routing** — test: a stream of partial frames
   then a final advisory calls `onPartial` n times then `onResult` once; a partial
   never reaches `onResult`; empty stream still guarded (existing resilience).
5. **Frontend provisional→reconcile UI** — test: provisional card shows "Verifying…"
   + partial fields; final verified frame replaces it; a final `suppressed` frame
   clears the provisional body and shows the suppression notice.
6. **E2E** (`frontend/e2e/`): mocked SSE emitting partials → final renders progressive
   fill then verified card; a suppressed final replaces provisional with the stub.

## Verification

- `cd backend && pytest -q` (263 baseline + new) green.
- `cd frontend && npm run test` + `npm run lint` green; `npx playwright test` new spec.
- Local: run the dev server, ask an EN poultry/rice query, watch the card fill live
  then reconcile; ask an ES query, confirm progress-only (no partials).
- Cost: zero paid tokens — Groq/Gemini free tier + mocked tests. No eval run (guard
  quality unchanged; gen content unchanged — only delivery changes).
- Deploy: push `main` → Vercel (frontend) + HF (backend) auto. Post-deploy LangSmith:
  gen still ~18s but first partial byte lands within ~1–2s; confirm `partial` frames
  in the trace and a clean final reconcile.

## Out of scope
- Generation model/provider swap (lever b — deferred, cost).
- Streaming the ES path (translation is post-gen).
- Any retrieval/guard logic change.

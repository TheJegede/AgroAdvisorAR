# Response Rendering Defects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four proven defects in how generated advisories render — confidence badge lying ("High" + NLI 0.00), `[RETRIEVED DOCUMENT CONTEXT]` placeholder leaking into prose/citations, escalation shown twice, and blank cards rendered as normal advisories — plus scope the structural re-ingest and one quality investigation.

**Architecture:** The citation guard (`backend/services/rag.py`) computes a `confidence_score` but never reconciles it with the LLM-authored `confidence` label, so the frontend renders two contradictory badges. A bracketed prompt header in `backend/utils/prompt.py` is mistaken by the model for a citable title (made worse by the titleless gte index). Fixes are split into 5 disjoint-file modules so they run in parallel via subagents in isolated git worktrees.

**Tech Stack:** FastAPI + Pydantic backend, pytest; React 19 + Vite frontend, vitest; Pinecone (`agroar-prod-gte`); langchain provider chain (Groq→Gemini).

---

## Module map & parallelization

| Module | Area | Owns (disjoint files) | Depends on | Parallel via subagent? |
|--------|------|-----------------------|-----------|------------------------|
| **M1** Backend guard/display semantics | `rag.py`, `advisory.py`, backend tests | `backend/services/rag.py`, `backend/models/advisory.py`, `backend/tests/test_rag_retrieval.py` | — | **Yes — Wave 1** |
| **M2** Prompt hygiene | prompt builder | `backend/utils/prompt.py`, `backend/tests/test_prompt.py` | — | **Yes — Wave 1** |
| **M3** Frontend suppression UX | advisory card | `frontend/src/components/advisory/*`, `frontend/src/constants/i18n.js` | M1 `suppressed` contract (build against it; integrate after M1 merges) | **Yes — Wave 1** |
| **M4** gte re-ingest w/ title metadata (1B) | ingestion + Pinecone | `ingestion/ingest_en_gte.py`, corpus jsonl, `ingestion/tests/test_ingest_gte_metadata.py` | owner infra creds | **Yes — owner-run, any time** |
| **M5** Quality investigation (Defect 5) | evals (read-only) | `evals/trace_*.py` (run only), `PROGRESS.md` findings | — | **Yes — any time** |

**Dispatch:** Wave 1 = M1, M2, M3, M5 concurrently (superpowers `using-git-worktrees` + `dispatching-parallel-agents`), one subagent per module in its own worktree. M4 runs in parallel but is owner-executed (needs `PINECONE_API_KEY` + gte embedder). **No two modules touch the same file** except `PROGRESS.md` — update that last, sequentially, after merges. **Integration order:** merge M1 → M2 → M3 (M3 integration tests need M1's `suppressed` field).

**Why M1 still matters after M4:** M4 re-enables the title guard (which can set `confidence="Low"`), but M1's score↔label reconciliation must stay as belt-and-suspenders for any future titleless state and for the `[0.2,0.4)` Medium band the title guard does not cover.

---

## Module 1 — Backend guard/display semantics

**Files:**
- Modify: `backend/models/advisory.py` (add `suppressed` field, ~57-62)
- Modify: `backend/services/rag.py` (`_strip_scaffolding` near 27-32; suppression block 243-263; scrub calls 153 + 209-223)
- Test: `backend/tests/test_rag_retrieval.py`

Run all backend tests from `backend/`: `cd backend && pytest`.

### Task 1.1: `suppressed` field on AdvisoryResponse

> **Reuse existing helpers in this test file:** `_make_advisory(citations_titles)` (builds an `AdvisoryResponse` with `confidence="High"`), `_MetaDoc(metadata, page_content="")`, and `_run_postprocess(rag, result, docs)` (calls `_postprocess_async` with `county_fips="05001"`). Vary confidence with `result.model_copy(update={"confidence": ...})`. Patch the guard with monkeypatch + an async stub (no `AsyncMock` import needed).

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_rag_retrieval.py`:
```python
def test_advisory_response_has_suppressed_default_false():
    a = _make_advisory([])
    assert a.suppressed is False
```
- [ ] **Step 2: Run, verify it fails**
Run: `cd backend && pytest tests/test_rag_retrieval.py::test_advisory_response_has_suppressed_default_false -v`
Expected: FAIL — `AdvisoryResponse` has no attribute/field `suppressed`.
- [ ] **Step 3: Implement** — in `backend/models/advisory.py`, add to `AdvisoryResponse`:
```python
class AdvisoryResponse(AdvisoryDraft):
    # F2 guard-computed fields — filled by the citation guard, NOT the LLM.
    confidence_score: Optional[float] = None
    claim_verification: Optional[List[ClaimResult]] = None
    escalation: Optional[str] = None
    suppressed: bool = False  # True when the guard blanked the body (score < SUPPRESSION)
```
- [ ] **Step 4: Run, verify it passes**
Run: `cd backend && pytest tests/test_rag_retrieval.py::test_advisory_response_has_suppressed_default_false -v`
Expected: PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/models/advisory.py backend/tests/test_rag_retrieval.py
git commit -m "feat(model): add suppressed flag to AdvisoryResponse"
```

### Task 1.2: Reconcile confidence label with guard score + set suppressed

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_rag_retrieval.py` (add `import importlib` is already at top; reuse `_make_advisory`/`_MetaDoc`/`_run_postprocess`):
```python
def _patch_guard(rag, monkeypatch, score):
    """Force the NLI guard on and stub verify_answer to a fixed score."""
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", True)
    async def _fake(answer, chunks):
        return {"confidence_score": score, "claim_verification": [], "escalation": None}
    monkeypatch.setattr(rag.citation_guard_v2, "verify_answer", _fake)


def test_suppression_forces_low_and_suppressed_flag(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.0)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "Low"
    assert out.suppressed is True
    assert out.problem_summary == ""
    assert out.warnings == []              # escalation NOT duplicated as a warning
    assert out.recommended_actions == []


def test_escalation_band_downgrades_high_to_medium(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.3)    # in [SUPPRESSION=0.2, ESCALATION=0.4)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "Medium"
    assert out.suppressed is False


def test_high_score_keeps_llm_confidence(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.9)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "High"
    assert out.suppressed is False
```
- [ ] **Step 2: Run, verify they fail**
Run: `cd backend && pytest tests/test_rag_retrieval.py -k "suppression_forces_low or escalation_band or high_score_keeps" -v`
Expected: FAIL — `suppression_forces_low` gets `confidence=="High"` and no `suppressed`; `escalation_band` gets `"High"`; `warnings` non-empty.
- [ ] **Step 3: Implement** — in `backend/services/rag.py`, replace the Step-3 tail (currently ~247-263) with:
```python
    update: dict = {
        "confidence_score": confidence_score,
        "claim_verification": claim_verification,
        "escalation": escalation,
    }

    # Reconcile the user-facing confidence label with the guard score. The
    # LLM-authored `confidence` is advisory; the guard score is authoritative.
    # Downgrade only — never upgrade an LLM "Low".
    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        update["confidence"] = "Low"
    elif confidence_score < citation_guard_v2.ESCALATION_THRESHOLD:
        if result.confidence == "High":
            update["confidence"] = "Medium"

    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        # Blank the unverified body. The escalation is carried by `escalation`
        # (rendered as its own card) — do NOT also duplicate it into warnings.
        update.update({
            "suppressed": True,
            "problem_summary": "",
            "likely_causes": [],
            "recommended_actions": [],
            "products_rates": [],
            "warnings": [],
        })

    return result.model_copy(update=update)
```
- [ ] **Step 4: Run, verify they pass**
Run: `cd backend && pytest tests/test_rag_retrieval.py -k "suppression_forces_low or escalation_band or high_score_keeps" -v`
Expected: PASS (3 tests).
- [ ] **Step 5: Commit**
```bash
git add backend/services/rag.py backend/tests/test_rag_retrieval.py
git commit -m "fix(guard): reconcile confidence label with score; stop duplicating escalation"
```

### Task 1.3: Scrub the `[RETRIEVED DOCUMENT CONTEXT]` placeholder (defense in depth)

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_rag_retrieval.py`:
```python
import importlib  # already present at module top; rag = importlib.import_module("services.rag")


def test_strip_scaffolding_removes_context_header():
    rag = importlib.import_module("services.rag")
    assert rag._strip_scaffolding("Read the report, see [RETRIEVED DOCUMENT CONTEXT]") == "Read the report, see"
    assert rag._strip_scaffolding("RETRIEVED DOCUMENT CONTEXT") == ""
    assert rag._strip_scaffolding("Document 3: rice guide") == "rice guide"   # still strips Document N:
```
- [ ] **Step 2: Run, verify it fails**
Run: `cd backend && pytest tests/test_rag_retrieval.py::test_strip_scaffolding_removes_context_header -v`
Expected: FAIL — `rag` has no attribute `_strip_scaffolding`.
- [ ] **Step 3: Implement** — in `backend/services/rag.py`, after `_strip_doc_prefix` (~32) add:
```python
_PLACEHOLDER_RE = re.compile(r"\[?\s*RETRIEVED DOCUMENT CONTEXT\s*\]?", re.IGNORECASE)


def _strip_scaffolding(text: str) -> str:
    """Remove prompt scaffolding the LLM copies verbatim: 'Document N:' prefixes and
    the '[RETRIEVED DOCUMENT CONTEXT]' context header."""
    return _PLACEHOLDER_RE.sub("", _DOC_PREFIX_RE.sub("", text or "")).strip()
```
Then replace `_strip_doc_prefix(` with `_strip_scaffolding(` in `_advisory_to_verifiable_text` (~153) and in the Step-2b scrub block (~210-221: `problem_summary`, `recommended_actions`, `likely_causes` cause/explanation, `citations` document_title).
- [ ] **Step 4: Run, verify it passes + no regressions**
Run: `cd backend && pytest tests/test_rag_retrieval.py -v`
Expected: PASS including the existing title-guard tests (which still call `_strip_doc_prefix` — keep that function defined as-is).
- [ ] **Step 5: Commit**
```bash
git add backend/services/rag.py backend/tests/test_rag_retrieval.py
git commit -m "fix(guard): scrub leaked [RETRIEVED DOCUMENT CONTEXT] header from prose and citations"
```

### Task 1.4: Full backend suite gate

- [ ] **Step 1: Run the full suite**
Run: `cd backend && pytest`
Expected: all green EXCEPT the one documented stale fail `test_citation_guard_v2.py::test_verifiable_text_includes_all_advisory_fields`. If any OTHER test fails, fix before handoff.

---

## Module 2 — Prompt hygiene (stops the leak at the source)

**Files:**
- Modify: `backend/utils/prompt.py` (retrieved-context block, 67-76)
- Test: `backend/tests/test_prompt.py`

### Task 2.1: Non-bracketed header + stable titleless handle

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_prompt.py`. `test_prompt.py` does NOT have a `_build` helper, so define one here (reuses the existing `Document` + `build_system_prompt` imports at the top of the file):
```python
def _build(retrieved_docs=None):
    return build_system_prompt(
        soil_context={"available": False}, weather_context={"available": False},
        retrieved_docs=retrieved_docs if retrieved_docs is not None
            else [_doc("Rice Irrigation Guide", "Flow Rate", "GPM = D x D x L.")],
        session_history=[], language="English", is_safety_critical=False,
        county_name="Arkansas",
    )


def test_prompt_header_is_not_bracketed():
    # The context header must NOT be wrapped in [brackets] — the model echoes any
    # bracketed token as if it were a citable document title.
    out = _build()
    assert "[RETRIEVED DOCUMENT CONTEXT]" not in out


def test_titleless_docs_get_stable_handle_not_unknown():
    titleless = [Document(page_content="Rice blast control info.", metadata={})]
    out = _build(retrieved_docs=titleless)
    assert "[Unknown]" not in out
    assert "Arkansas Extension source 1" in out
```
- [ ] **Step 2: Run, verify they fail**
Run: `cd backend && pytest tests/test_prompt.py -k "header_is_not_bracketed or stable_handle" -v`
Expected: FAIL — bracketed header present; titleless doc renders `[Unknown]`.
- [ ] **Step 3: Implement** — in `backend/utils/prompt.py` replace the `if retrieved_docs:` block (~67-76):
```python
    # Retrieved document context. The header is intentionally NOT wrapped in [brackets]
    # so the model can't mistake it for a citable title.
    if retrieved_docs:
        parts.append("=== RETRIEVED CONTEXT (cite each passage by its [bracketed] title) ===")
        for i, doc in enumerate(retrieved_docs, 1):
            meta = doc.metadata
            title = meta.get("document_title") or ""
            section = meta.get("section_heading", "")
            label = f"{title} — {section}".strip(" —")
            if not label:
                # Titleless gte index stores only {text, namespace}. Give a stable,
                # citable handle rather than "[Unknown]", which the model echoes verbatim.
                label = f"Arkansas Extension source {i}"
            parts.append(f"[{label}] {doc.page_content}")
        parts.append("")
```
- [ ] **Step 4: Run, verify all prompt tests pass**
Run: `cd backend && pytest tests/test_prompt.py -v`
Expected: PASS including `test_prompt_does_not_label_documents_numerically` and `test_prompt_includes_output_instructions`.
- [ ] **Step 5: Commit**
```bash
git add backend/utils/prompt.py backend/tests/test_prompt.py
git commit -m "fix(prompt): unbracket context header; give titleless docs a citable handle"
```

---

## Module 3 — Frontend suppression UX

**Files:**
- Create: `frontend/src/components/advisory/SuppressedNotice.jsx`
- Create: `frontend/src/components/advisory/SuppressedNotice.test.js`
- Modify: `frontend/src/components/advisory/AdvisoryCard.jsx` (body render block 64-70)
- Modify: `frontend/src/constants/i18n.js` (add `suppressedTitle`, `suppressedBody` to `en` and `es`)

Run from `frontend/`: `npm run lint && npx vitest run`.
**Contract from M1:** `response.suppressed: boolean`. Build against it now; integration-verify after M1 merges.

### Task 3.1: SuppressedNotice component

- [ ] **Step 1: Write the failing test** — `frontend/src/components/advisory/SuppressedNotice.test.js`:
```jsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SuppressedNotice from './SuppressedNotice'
import { LangProvider } from '../../contexts/LangContext'

const wrap = (ui) => render(<LangProvider>{ui}</LangProvider>)

describe('SuppressedNotice', () => {
  it('shows the withheld-answer message', () => {
    wrap(<SuppressedNotice escalation={null} />)
    expect(screen.getByText(/could.?n.?t verify/i)).toBeInTheDocument()
  })
  it('shows the escalation contact exactly once when provided', () => {
    wrap(<SuppressedNotice escalation="Contact your Pulaski County Extension Agent" />)
    expect(screen.getAllByText(/Pulaski County Extension Agent/i)).toHaveLength(1)
  })
})
```
- [ ] **Step 2: Run, verify it fails**
Run: `cd frontend && npx vitest run src/components/advisory/SuppressedNotice.test.js`
Expected: FAIL — module `./SuppressedNotice` not found.
- [ ] **Step 3a: Add i18n keys** — in `frontend/src/constants/i18n.js`, add to BOTH the `en` and `es` objects:
```js
// en
suppressedTitle: "We couldn't verify a confident answer",
suppressedBody: "This response was withheld because it could not be verified against our Arkansas Extension sources. Please reach out for direct guidance:",
// es
suppressedTitle: 'No pudimos verificar una respuesta confiable',
suppressedBody: 'Esta respuesta se retuvo porque no pudo verificarse con nuestras fuentes de Extensión de Arkansas. Comuníquese para obtener orientación directa:',
```
- [ ] **Step 3b: Implement component** — `frontend/src/components/advisory/SuppressedNotice.jsx`:
```jsx
import { useLang } from '../../contexts/LangContext'

export default function SuppressedNotice({ escalation }) {
  const { t } = useLang()
  return (
    <div className="bg-arred/10 dark:bg-hc-surface border border-arred dark:border-2 dark:border-hc-danger rounded-card p-4 my-2">
      <p className="text-sm font-semibold text-arred-dark dark:text-hc-danger">{t.suppressedTitle}</p>
      <p className="text-sm text-charcoal dark:text-hc-fg mt-1 leading-relaxed">{t.suppressedBody}</p>
      {escalation && <p className="text-sm font-medium text-charcoal dark:text-hc-fg mt-2">{escalation}</p>}
    </div>
  )
}
```
- [ ] **Step 4: Run, verify it passes**
Run: `cd frontend && npx vitest run src/components/advisory/SuppressedNotice.test.js`
Expected: PASS (2 tests).
- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/advisory/SuppressedNotice.jsx frontend/src/components/advisory/SuppressedNotice.test.js frontend/src/constants/i18n.js
git commit -m "feat(ui): add SuppressedNotice for withheld answers"
```

### Task 3.2: Branch AdvisoryCard on `suppressed`

- [ ] **Step 1: Write the failing test** — `frontend/src/components/advisory/AdvisoryCard.test.js` (create or extend):
```jsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AdvisoryCard from './AdvisoryCard'
import { LangProvider } from '../../contexts/LangContext'

const base = {
  confidence: 'Low', confidence_score: 0.0, suppressed: true,
  escalation: 'Contact your Pulaski County Extension Agent',
  problem_summary: '', likely_causes: [], recommended_actions: [],
  products_rates: [], warnings: [], citations: [],
  confidence_explanation: '', context_meta: { soil_data_available: false, weather_data_available: false, county_fips: '05055' },
}
const wrap = (resp) => render(<LangProvider><AdvisoryCard response={resp} messageId="m1" category="IN_SCOPE_RICE" /></LangProvider>)

describe('AdvisoryCard suppression', () => {
  it('renders SuppressedNotice and hides body when suppressed', () => {
    wrap(base)
    expect(screen.getByText(/could.?n.?t verify/i)).toBeInTheDocument()
    // escalation appears once (SuppressedNotice), not also via EscalationCard duplicate text
    expect(screen.getAllByText(/Pulaski County Extension Agent/i).length).toBeLessThanOrEqual(2)
  })
  it('renders normal body when not suppressed', () => {
    wrap({ ...base, suppressed: false, problem_summary: 'Rice blast detected.', confidence: 'High', confidence_score: 0.9 })
    expect(screen.getByText(/Rice blast detected/i)).toBeInTheDocument()
  })
})
```
- [ ] **Step 2: Run, verify it fails**
Run: `cd frontend && npx vitest run src/components/advisory/AdvisoryCard.test.js`
Expected: FAIL — suppressed branch not implemented; body sections render empty instead of the notice.
- [ ] **Step 3: Implement** — in `frontend/src/components/advisory/AdvisoryCard.jsx`, import `SuppressedNotice` and replace the body block (currently lines ~65-69, the `WarningsBanner` through `ProductsRates`) with:
```jsx
      {response.suppressed ? (
        <SuppressedNotice escalation={response.escalation} />
      ) : (
        <>
          <WarningsBanner warnings={response.warnings} />
          <ProblemSummary summary={response.problem_summary} />
          <LikelyCauses causes={response.likely_causes} />
          <RecommendedActions actions={response.recommended_actions} />
          <ProductsRates products={response.products_rates} />
        </>
      )}
```
Keep `EscalationCard` and `LowConfidenceBanner` as-is above. Note: when suppressed, `EscalationCard` (driven by `response.escalation`) and `SuppressedNotice` may both show the contact — acceptable, but to show it ONCE, gate `EscalationCard` with `{!response.suppressed && <EscalationCard ... />}`. Implement the gated version.
- [ ] **Step 4: Run, verify it passes + lint**
Run: `cd frontend && npx vitest run src/components/advisory/AdvisoryCard.test.js && npm run lint`
Expected: PASS, lint clean.
- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/advisory/AdvisoryCard.jsx frontend/src/components/advisory/AdvisoryCard.test.js
git commit -m "fix(ui): render suppressed answers as a withheld-answer notice"
```

---

## Module 4 — Re-ingest gte WITH title/section metadata (structural, 1B) [OWNER-RUN]

**Files:**
- Modify: `ingestion/ingest_en_gte.py`
- Regenerate: `ingestion/en_chunks/corpus_en.jsonl` (currently `{chunk_id, namespace, text}` → add `{document_title, section_heading}`, preserving the winning 512-char chunking)
- Test: `ingestion/tests/test_ingest_gte_metadata.py`

**Constraint:** needs `PINECONE_API_KEY` + gte embedder + long-running re-embed. A code subagent cannot run this without infra creds — assign to the owner. Keep M1's reconciliation even after this lands.

### Task 4.1: Upsert carries title + section (testable without network)

- [ ] **Step 1: Write the failing test** — `ingestion/tests/test_ingest_gte_metadata.py`: assert the function that builds the upsert payload includes `document_title` and `section_heading` in each vector's metadata (mock the Pinecone client; assert on the payload passed to `upsert`).
- [ ] **Step 2: Run, verify it fails** — Run: `cd ingestion && pytest tests/test_ingest_gte_metadata.py -v` → FAIL (metadata missing title/section).
- [ ] **Step 3: Implement** — in `ingestion/ingest_en_gte.py`, read `document_title`/`section_heading` from the regenerated corpus jsonl and include them in each upsert vector's `metadata`.
- [ ] **Step 4: Run, verify it passes** — Run: `cd ingestion && pytest tests/test_ingest_gte_metadata.py -v` → PASS.
- [ ] **Step 5: Commit** — `git add ingestion/ && git commit -m "feat(ingest): carry document_title + section_heading into gte upsert"`

### Task 4.2: Regenerate corpus + re-embed [OWNER, manual]

- [ ] Regenerate `corpus_en.jsonl` from source with title + section, preserving 512-char chunking.
- [ ] Run `cd ingestion && python ingest_en_gte.py` to re-upsert `agroar-prod-gte`.
- [ ] **Manual verify:** prod retrieval returns docs with non-empty `document_title`; citations show real titles; `rag._postprocess_async` `titles_present` becomes True (title guard validates ≥1 citation).

---

## Module 5 — Quality investigation (Defect 5) [read-only / research]

**Files:** run `evals/trace_retrieval.py`, `evals/trace_generation.py`; write findings into `PROGRESS.md`.

- [ ] **Step 1:** Trace both failing queries through retrieval:
  - "How do I read a soil test report and what amendments should I apply?"
  - "What are the most common nutrient deficiencies in Arkansas soils?"
  Run: `cd evals && python trace_retrieval.py` (adapt the script's query input). Record whether gold/on-topic chunks appear in top-5.
- [ ] **Step 2: Decide** based on the trace:
  - Retrieval fine but answer generic → propose an informational-answer shape (a prompt branch or a non-diagnosis schema variant) so "Likely Causes" isn't forced onto informational questions. Write the proposal as a follow-up plan.
  - Retrieval thin → corpus-coverage audit (see memory `project-eval-contamination`).
- [ ] **Step 3:** Append findings (the retrieval trace for both queries + the go/no-go decision) to `PROGRESS.md`.

---

## Testing Strategy

- Every code module is TDD (superpowers `test-driven-development`): failing test first, minimal impl, green, commit.
- Backend gate after M1 + M2 merge: `cd backend && pytest` (green except the documented stale fail).
- Frontend gate: `cd frontend && npm run lint && npx vitest run`.
- **End-to-end smoke after deploy:** re-run the two screenshot queries and verify: (a) no green "High" badge on a low-score answer, (b) no `[RETRIEVED DOCUMENT CONTEXT]` / `Unknown` text, (c) escalation shown once, (d) suppressed answers show the withheld-answer card.

## Rollback Plan

- Each module is isolated commits on its own branch/worktree — `git revert <sha>` restores prior behavior. No DB migrations.
- M4 (re-ingest) is additive metadata on `agroar-prod-gte`; on problems, `titles_present` simply returns to False (current behavior). Keep the old corpus jsonl until verified.

## Open Questions

- **Confidence mapping rule:** this plan keeps the LLM label above 0.4, downgrades High→Medium in `[0.2,0.4)`, forces Low below 0.2. Alternative: derive the label entirely from the score band (ignore the LLM label). Confirm before M1 merge.
- **Suppressed-answer copy:** confirm exact EN + ES wording for `SuppressedNotice` (draft provided in Task 3.1).

## Self-Review notes

- Spec coverage: Defects 1/3/4 → M1 (+M3 render); Defect 2 → M1 scrub + M2 source fix; titleless root enabler → M4; Defect 5 → M5. All covered.
- Type consistency: `suppressed` (bool) defined in M1 Task 1.1, consumed by M3 Tasks 3.1/3.2; `_strip_scaffolding` defined and used within M1 Task 1.3.
- Placeholder scan: none — all code steps show concrete code; M4 Task 4.1 and M5 are deliberately description-level because they require infra creds / are exploratory research, not deterministic code edits.

# F2 — Citation Guard v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add NLI-based claim verification to every RAG response, producing a `confidence_score` float, per-claim verdicts, and county Extension escalation for low-confidence answers.

**Architecture:** After the existing title-match citation guard in `_postprocess`, call `citation_guard_v2.verify_answer()` which decomposes the answer into atomic claims via Gemini Flash Lite, scores each claim against the top-3 retrieved chunks with a cross-encoder NLI model, and stamps `confidence_score` + `escalation` onto `AdvisoryResponse`. Frontend shows a new NLI score badge and escalation card.

**Tech Stack:** `sentence-transformers` CrossEncoder (`cross-encoder/nli-MiniLM2-L6-H768`), Gemini Flash Lite (claim decomposition), FastAPI/Pydantic (model extension), React 19 + Tailwind (badge + escalation card).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/supabase/migrations/008_confidence_scores.sql` | Create | Add `confidence_score`, `escalated` to `chat_messages`; `answer_confidence_mean` to `eval_runs` |
| `backend/models/advisory.py` | Modify | Add `ClaimResult`; add 3 Optional fields to `AdvisoryResponse` |
| `backend/services/citation_guard_v2.py` | Create | NLI engine: decompose → verify → score → escalate |
| `backend/data/county_agents.json` | Create (scraper output) | 75 AR county Extension contacts keyed by FIPS |
| `ingestion/scrape_county_agents.py` | Create | One-shot Playwright scraper for uaex.uada.edu |
| `backend/services/rag.py` | Modify | `_postprocess` calls `verify_answer`, stamps fields, applies thresholds |
| `backend/tests/test_citation_guard_v2.py` | Create | Unit tests for NLI service (mocked CrossEncoder + Gemini) |
| `frontend/src/components/advisory/NLIConfidenceBadge.jsx` | Create | Green/amber/red badge for float `confidence_score` |
| `frontend/src/components/advisory/EscalationCard.jsx` | Create | Amber card showing county agent contact string |
| `frontend/src/components/advisory/AdvisoryCard.jsx` | Modify | Add `NLIConfidenceBadge` + `EscalationCard` |
| `frontend/src/constants/i18n.js` | Modify | Add `nliScore`, `escalationContact` keys (EN + ES) |
| `backend/services/nightly_alerts.py` | Modify | Aggregate `answer_confidence_mean` into eval run |

---

## Task 1: DB Migration 008

**Files:**
- Create: `backend/supabase/migrations/008_confidence_scores.sql`

- [ ] **Step 1: Create migration file**

```sql
-- backend/supabase/migrations/008_confidence_scores.sql
ALTER TABLE public.chat_messages
  ADD COLUMN IF NOT EXISTS confidence_score float,
  ADD COLUMN IF NOT EXISTS escalated bool;

ALTER TABLE public.eval_runs
  ADD COLUMN IF NOT EXISTS answer_confidence_mean float;
```

- [ ] **Step 2: Commit**

```bash
git add backend/supabase/migrations/008_confidence_scores.sql
git commit -m "feat(f2): add migration 008 — confidence_score + escalated columns"
```

---

## Task 2: Extend AdvisoryResponse Model

**Files:**
- Modify: `backend/models/advisory.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_citation_guard_v2.py` with model serialization test:

```python
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.advisory import AdvisoryResponse, ClaimResult, ContextMeta


def test_advisory_response_has_optional_nli_fields():
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Test",
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="Test",
        language="en",
        context_meta=ctx,
    )
    assert resp.confidence_score is None
    assert resp.claim_verification is None
    assert resp.escalation is None


def test_claim_result_labels():
    cr = ClaimResult(claim="Rice needs water.", label="ENTAILED", score=0.85)
    assert cr.label == "ENTAILED"
    assert cr.score == 0.85


def test_advisory_response_with_nli_fields():
    ctx = ContextMeta(soil_data_available=True, weather_data_available=True, county_fips="05001")
    cr = ClaimResult(claim="Apply herbicide at V3.", label="ENTAILED", score=0.9)
    resp = AdvisoryResponse(
        problem_summary="Palmer amaranth detected.",
        likely_causes=[],
        recommended_actions=["Apply herbicide"],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Medium",
        confidence_explanation="Two sources support.",
        language="en",
        context_meta=ctx,
        confidence_score=0.78,
        claim_verification=[cr],
        escalation=None,
    )
    assert resp.confidence_score == 0.78
    assert len(resp.claim_verification) == 1
```

- [ ] **Step 2: Run test — expect failure (ClaimResult not defined)**

```bash
cd backend && pytest tests/test_citation_guard_v2.py::test_advisory_response_has_optional_nli_fields -v
```

Expected: `ImportError` or `AttributeError` — `ClaimResult` does not exist yet.

- [ ] **Step 3: Extend `backend/models/advisory.py`**

Add `ClaimResult` and three Optional fields. The file currently ends at line 40. Replace the full file:

```python
from pydantic import BaseModel
from typing import List, Optional, Literal


class Cause(BaseModel):
    cause: str
    explanation: str


class Product(BaseModel):
    product: str
    rate: str
    application_method: str
    pre_harvest_interval: Optional[str] = None


class Citation(BaseModel):
    document_title: str
    section: str
    url: Optional[str] = None


class ContextMeta(BaseModel):
    soil_data_available: bool
    weather_data_available: bool
    county_fips: str


class ClaimResult(BaseModel):
    claim: str
    label: Literal['ENTAILED', 'NEUTRAL', 'CONTRADICTED']
    score: float


class AdvisoryResponse(BaseModel):
    problem_summary: str
    likely_causes: List[Cause]
    recommended_actions: List[str]
    products_rates: List[Product]
    warnings: List[str]
    citations: List[Citation]
    confidence: Literal["High", "Medium", "Low"]
    confidence_explanation: str
    language: Literal["en", "es"]
    context_meta: ContextMeta
    # F2 fields — Optional for backwards compat with stored messages
    confidence_score: Optional[float] = None
    claim_verification: Optional[List[ClaimResult]] = None
    escalation: Optional[str] = None
```

- [ ] **Step 4: Run tests — expect all 3 pass**

```bash
cd backend && pytest tests/test_citation_guard_v2.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/models/advisory.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(f2): add ClaimResult model and Optional NLI fields to AdvisoryResponse"
```

---

## Task 3: County Agents Scraper

**Files:**
- Create: `ingestion/scrape_county_agents.py`
- Creates: `backend/data/county_agents.json`

- [ ] **Step 1: Create AR FIPS lookup and scraper**

Create `ingestion/scrape_county_agents.py`:

```python
"""
One-shot scraper: uaex.uada.edu/about/county-extension-offices/
Outputs: backend/data/county_agents.json

Run: python ingestion/scrape_county_agents.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# AR county name → FIPS (05XXX)
AR_COUNTY_FIPS = {
    "Arkansas": "05001", "Ashley": "05003", "Baxter": "05005", "Benton": "05007",
    "Boone": "05009", "Bradley": "05011", "Calhoun": "05013", "Carroll": "05015",
    "Chicot": "05017", "Clark": "05019", "Clay": "05021", "Cleburne": "05023",
    "Cleveland": "05025", "Columbia": "05027", "Conway": "05029", "Craighead": "05031",
    "Crawford": "05033", "Crittenden": "05035", "Cross": "05037", "Dallas": "05039",
    "Desha": "05041", "Drew": "05043", "Faulkner": "05045", "Franklin": "05047",
    "Fulton": "05049", "Garland": "05051", "Grant": "05053", "Greene": "05055",
    "Hempstead": "05057", "Hot Spring": "05059", "Howard": "05061",
    "Independence": "05063", "Izard": "05065", "Jackson": "05067",
    "Jefferson": "05069", "Johnson": "05071", "Lafayette": "05073",
    "Lawrence": "05075", "Lee": "05077", "Lincoln": "05079",
    "Little River": "05081", "Logan": "05083", "Lonoke": "05085",
    "Madison": "05087", "Marion": "05089", "Miller": "05091",
    "Mississippi": "05093", "Monroe": "05095", "Montgomery": "05097",
    "Nevada": "05099", "Newton": "05101", "Ouachita": "05103",
    "Perry": "05105", "Phillips": "05107", "Pike": "05109",
    "Poinsett": "05111", "Polk": "05113", "Pope": "05115",
    "Prairie": "05117", "Pulaski": "05119", "Randolph": "05121",
    "St. Francis": "05123", "Saline": "05125", "Scott": "05127",
    "Searcy": "05129", "Sebastian": "05131", "Sevier": "05133",
    "Sharp": "05135", "Stone": "05137", "Union": "05139",
    "Van Buren": "05141", "Washington": "05143", "White": "05145",
    "Woodruff": "05147", "Yell": "05149",
}

BASE_URL = "https://uaex.uada.edu/about/county-extension-offices/"


def _normalize_county(name: str) -> str:
    """Strip 'County' suffix and extra whitespace for dict lookup."""
    return re.sub(r"\s+County\s*$", "", name.strip(), flags=re.IGNORECASE).strip()


async def scrape() -> dict:
    result = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)

        # Collect county page links — adjust selector if site structure differs
        links = await page.eval_on_selector_all(
            "a[href*='county']",
            "els => els.map(el => ({text: el.innerText.trim(), href: el.href}))"
        )

        county_links = [
            lnk for lnk in links
            if lnk["text"] and "county" in lnk["href"].lower()
            and lnk["href"].startswith("https://uaex")
        ]

        seen = set()
        for lnk in county_links:
            county_name = _normalize_county(lnk["text"])
            fips = AR_COUNTY_FIPS.get(county_name)
            if not fips or fips in seen:
                continue
            seen.add(fips)

            try:
                cpage = await browser.new_page()
                await cpage.goto(lnk["href"], wait_until="domcontentloaded", timeout=20000)
                text = await cpage.inner_text("body")
                await cpage.close()

                # Extract phone (xxx-xxx-xxxx or (xxx) xxx-xxxx)
                phone_match = re.search(r"(\(?\d{3}\)?[\s\-]\d{3}[\-]\d{4})", text)
                # Extract email
                email_match = re.search(r"[\w.+-]+@uada\.edu", text)
                # Extract agent name — look for "County Agent" or "Extension Agent" heading
                name_match = re.search(
                    r"([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*\n.*(?:Agent|Director)",
                    text
                )

                result[fips] = {
                    "county": county_name,
                    "agent_name": name_match.group(1).strip() if name_match else "",
                    "phone": phone_match.group(1).strip() if phone_match else "",
                    "email": email_match.group(0).strip() if email_match else "",
                }
                print(f"  ✓ {county_name} ({fips})")
            except Exception as e:
                print(f"  ✗ {county_name} ({fips}): {e}", file=sys.stderr)
                result[fips] = {"county": county_name, "agent_name": "", "phone": "", "email": ""}

        await browser.close()
    return result


if __name__ == "__main__":
    print("Scraping county extension offices...")
    data = asyncio.run(scrape())
    out_path = Path(__file__).parent.parent / "backend" / "data" / "county_agents.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2))
    print(f"\nWrote {len(data)} counties → {out_path}")
```

- [ ] **Step 2: Run scraper**

```bash
python ingestion/scrape_county_agents.py
```

Expected: `Wrote N counties → backend/data/county_agents.json` (N ≥ 50; some may fail gracefully).

- [ ] **Step 3: Verify output structure**

```bash
python -c "import json; d=json.load(open('backend/data/county_agents.json')); print(list(d.items())[:2])"
```

Expected: `[('05001', {'county': 'Arkansas', 'agent_name': '...', 'phone': '...', 'email': '...'}), ...]`

If many entries have empty `agent_name`/`phone`/`email`, the page structure may differ — open one county URL in a browser and adjust the selectors/regex in the scraper, then re-run.

- [ ] **Step 4: Commit**

```bash
git add ingestion/scrape_county_agents.py backend/data/county_agents.json
git commit -m "feat(f2): add county agents scraper and county_agents.json"
```

---

## Task 4: `citation_guard_v2.py` Core Service

**Files:**
- Create: `backend/services/citation_guard_v2.py`
- Modify: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Add tests for citation_guard_v2 (append to existing test file)**

Append to `backend/tests/test_citation_guard_v2.py`:

```python
import importlib
import json
import os
import tempfile
import numpy as np
from unittest.mock import MagicMock, patch


def _make_county_agents_file(data: dict) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def test_score_answer_mean_of_entailed():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="ENTAILED", score=0.9),
        ClaimResult(claim="B", label="NEUTRAL", score=0.4),
        ClaimResult(claim="C", label="ENTAILED", score=0.7),
    ]
    score = mod.score_answer(claims)
    assert abs(score - 0.8) < 0.001


def test_score_answer_empty_returns_one():
    mod = importlib.import_module("services.citation_guard_v2")
    assert mod.score_answer([]) == 1.0


def test_score_answer_no_entailed_returns_zero():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="CONTRADICTED", score=0.1),
        ClaimResult(claim="B", label="NEUTRAL", score=0.5),
    ]
    assert mod.score_answer(claims) == 0.0


def test_escalation_cue_found(monkeypatch, tmp_path):
    mod = importlib.import_module("services.citation_guard_v2")
    agents = {"05001": {"county": "Arkansas", "agent_name": "Jane Smith", "phone": "870-555-0100", "email": "jsmith@uada.edu"}}
    agents_file = _make_county_agents_file(agents)
    monkeypatch.setattr(mod, "_AGENTS_PATH", agents_file)
    monkeypatch.setattr(mod, "_agents_cache", None)
    try:
        result = mod.escalation_cue("05001")
        assert "Jane Smith" in result
        assert "870-555-0100" in result
    finally:
        os.unlink(agents_file)


def test_escalation_cue_missing_fips(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    agents = {"05001": {"county": "Arkansas", "agent_name": "Jane Smith", "phone": "870-555-0100", "email": "jsmith@uada.edu"}}
    agents_file = _make_county_agents_file(agents)
    monkeypatch.setattr(mod, "_AGENTS_PATH", agents_file)
    monkeypatch.setattr(mod, "_agents_cache", None)
    try:
        result = mod.escalation_cue("99999")
        assert result is None
    finally:
        os.unlink(agents_file)


def test_verify_claim_entailed(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    # CrossEncoder labels: index 0=contradiction, 1=entailment, 2=neutral
    fake_scores = np.array([[0.05, 0.90, 0.05], [0.10, 0.80, 0.10]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim("Rice needs flooding.", ["Rice requires standing water.", "Apply fertilizer at planting."])
    assert result.label == "ENTAILED"
    assert result.score > 0.8


def test_verify_claim_contradicted(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    fake_scores = np.array([[0.88, 0.05, 0.07]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim("Do not irrigate.", ["Irrigation is required in dry spells."])
    assert result.label == "CONTRADICTED"
```

- [ ] **Step 2: Run tests — expect failure (module not found)**

```bash
cd backend && pytest tests/test_citation_guard_v2.py -k "score_answer or escalation or verify_claim" -v
```

Expected: `ModuleNotFoundError: No module named 'services.citation_guard_v2'`

- [ ] **Step 3: Create `backend/services/citation_guard_v2.py`**

```python
"""NLI-based claim verification for F2 citation guard."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import numpy as np
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from models.advisory import ClaimResult

# Thresholds (tune during eval)
ESCALATION_THRESHOLD = 0.4
SUPPRESSION_THRESHOLD = 0.2

_AGENTS_PATH = str(Path(__file__).parent.parent / "data" / "county_agents.json")
_agents_cache: Optional[dict] = None

_nli_model = None
_gemini_llm = None


def _get_nli_model():
    global _nli_model
    if _nli_model is None:
        from sentence_transformers import CrossEncoder
        _nli_model = CrossEncoder("cross-encoder/nli-MiniLM2-L6-H768")
    return _nli_model


def _get_gemini():
    global _gemini_llm
    if _gemini_llm is None:
        _gemini_llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_CLASSIFIER_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0,
        )
    return _gemini_llm


def _load_agents() -> dict:
    global _agents_cache
    if _agents_cache is None:
        try:
            _agents_cache = json.loads(Path(_AGENTS_PATH).read_text())
        except Exception:
            _agents_cache = {}
    return _agents_cache


_DECOMPOSE_PROMPT = """Extract all distinct factual claims from the following agricultural advisory text.
Return a JSON array of strings. Each string is one atomic, standalone factual claim.
Maximum 8 claims. Only include claims that could be verified against a knowledge source.

Text:
{text}

Return ONLY a JSON array, e.g. ["Claim one.", "Claim two."]"""


async def decompose_claims(answer: str) -> list[str]:
    """Break answer prose into atomic factual claims via Gemini Flash Lite."""
    prompt = _DECOMPOSE_PROMPT.format(text=answer[:2000])
    try:
        llm = _get_gemini()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        claims = json.loads(raw)
        if isinstance(claims, list):
            return [str(c) for c in claims[:8] if c]
    except Exception:
        pass
    # Fallback: sentence split
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 10]
    return sentences[:8]


def verify_claim(claim: str, chunks: list[str]) -> ClaimResult:
    """Score a single claim against retrieved chunks using NLI cross-encoder.

    CrossEncoder nli-MiniLM2-L6-H768 label order: [contradiction, entailment, neutral]
    """
    if not chunks:
        return ClaimResult(claim=claim, label="NEUTRAL", score=0.5)

    model = _get_nli_model()
    pairs = [(claim, chunk) for chunk in chunks[:3]]
    # scores shape: (n_pairs, 3) — softmax not applied, raw logits
    scores = np.array(model.predict(pairs))
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)

    # For each chunk, find the label with highest logit
    # Pick the chunk with the highest entailment logit (index 1)
    entailment_logits = scores[:, 1]
    best_chunk_idx = int(entailment_logits.argmax())
    best_scores = scores[best_chunk_idx]

    label_idx = int(best_scores.argmax())
    _LABELS = ["CONTRADICTED", "ENTAILED", "NEUTRAL"]
    label = _LABELS[label_idx]

    # Score = entailment logit of best chunk (used in score_answer mean)
    # Apply sigmoid to map logit to [0, 1]
    entailment_logit = float(best_scores[1])
    score = float(1 / (1 + np.exp(-entailment_logit)))

    return ClaimResult(claim=claim, label=label, score=score)


def score_answer(results: list[ClaimResult]) -> float:
    """Mean entailment score across all claims. Empty list → 1.0."""
    if not results:
        return 1.0
    entailed = [r.score for r in results if r.label == "ENTAILED"]
    if not entailed:
        return 0.0
    return float(sum(entailed) / len(entailed))


def escalation_cue(county_fips: str) -> Optional[str]:
    """Return formatted UA Extension contact string for county, or None."""
    agents = _load_agents()
    agent = agents.get(county_fips)
    if not agent:
        return None
    parts = [f"Contact your {agent.get('county', '')} County Extension Agent"]
    if agent.get("agent_name"):
        parts.append(agent["agent_name"])
    if agent.get("phone"):
        parts.append(agent["phone"])
    if agent.get("email"):
        parts.append(agent["email"])
    return " — ".join(parts)


async def verify_answer(answer: str, chunks: list[dict]) -> dict:
    """Orchestrate claim decomposition, NLI scoring, and escalation lookup.

    Args:
        answer: Farmer-facing prose (problem_summary + recommended_actions joined).
        chunks: Retrieved chunks as dicts with 'snippet' key.

    Returns:
        {confidence_score: float, claim_verification: list[ClaimResult], escalation: str|None}
    """
    chunk_texts = [c.get("snippet", "") for c in chunks if c.get("snippet")]

    claims_text = await decompose_claims(answer)

    if not claims_text:
        return {"confidence_score": 1.0, "claim_verification": [], "escalation": None}

    results = await asyncio.to_thread(
        lambda: [verify_claim(c, chunk_texts) for c in claims_text]
    )

    confidence_score = score_answer(results)
    return {
        "confidence_score": confidence_score,
        "claim_verification": results,
        "escalation": None,  # caller stamps escalation after checking fips
    }
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && pytest tests/test_citation_guard_v2.py -k "score_answer or escalation or verify_claim" -v
```

Expected: 7 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(f2): add citation_guard_v2 NLI service with tests"
```

---

## Task 5: Wire NLI Guard into `rag.py`

**Files:**
- Modify: `backend/services/rag.py`
- Modify: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Add integration test for `_postprocess` with NLI fields**

Append to `backend/tests/test_citation_guard_v2.py`:

```python
def test_postprocess_stamps_confidence_score(monkeypatch):
    import asyncio
    rag = importlib.import_module("services.rag")
    guard = importlib.import_module("services.citation_guard_v2")

    async def fake_verify_answer(answer, chunks):
        return {
            "confidence_score": 0.82,
            "claim_verification": [],
            "escalation": None,
        }

    monkeypatch.setattr(guard, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(guard, "escalation_cue", lambda fips: None)

    from models.advisory import AdvisoryResponse, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Palmer amaranth detected.",
        likely_causes=[],
        recommended_actions=["Apply herbicide at V3."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Medium",
        confidence_explanation="Two sources.",
        language="en",
        context_meta=ctx,
    )

    result = asyncio.run(rag._postprocess_async(resp, [], {}, {}, "05001"))
    assert result.confidence_score == 0.82


def test_postprocess_suppresses_body_below_threshold(monkeypatch):
    import asyncio
    rag = importlib.import_module("services.rag")
    guard = importlib.import_module("services.citation_guard_v2")

    async def fake_verify_low(answer, chunks):
        return {"confidence_score": 0.10, "claim_verification": [], "escalation": None}

    monkeypatch.setattr(guard, "verify_answer", fake_verify_low)
    monkeypatch.setattr(guard, "escalation_cue", lambda fips: "Contact: Jane Smith — 870-555-0100")

    from models.advisory import AdvisoryResponse, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Some advice.",
        likely_causes=[],
        recommended_actions=["Do something."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Low",
        confidence_explanation="Weak.",
        language="en",
        context_meta=ctx,
    )

    result = asyncio.run(rag._postprocess_async(resp, [], {}, {}, "05001"))
    assert result.problem_summary == ""
    assert result.recommended_actions == []
    assert len(result.warnings) == 1
    assert "Contact" in result.warnings[0]
```

- [ ] **Step 2: Run tests — expect failure (`_postprocess_async` not defined)**

```bash
cd backend && pytest tests/test_citation_guard_v2.py -k "postprocess" -v
```

Expected: `AttributeError: module 'services.rag' has no attribute '_postprocess_async'`

- [ ] **Step 3: Modify `backend/services/rag.py`**

Replace the existing `_postprocess` sync function and update `run_rag_query` to call the new async version:

```python
"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryResponse
from services.embedding import MiniLMEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
from services import citation_guard_v2
from utils.prompt import build_system_prompt
from utils.counties import get_county_info
import config

_vectorstore: PineconeVectorStore | None = None
_llm: ChatGoogleGenerativeAI | None = None
_groq_llm = None


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(
            model=config.GROQ_CLASSIFIER_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_llm


def _get_vectorstore() -> PineconeVectorStore:
    global _vectorstore
    if _vectorstore is None:
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        index = pc.Index(config.PINECONE_INDEX_NAME)
        _vectorstore = PineconeVectorStore(
            index=index,
            embedding=MiniLMEmbeddings(),
            text_key="text",
        )
    return _vectorstore


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_PRIMARY_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0.1,
        )
    return _llm


async def _postprocess_async(
    result: AdvisoryResponse,
    docs: list,
    soil: dict,
    weather: dict,
    county_fips: str,
) -> AdvisoryResponse:
    """Apply citation guard (title-match + NLI) and stamp context_meta."""
    # Step 1: existing title-match citation guard
    retrieved_titles = {
        doc.metadata.get("document_title", "").lower() for doc in docs
    }
    valid_citations = [
        c for c in result.citations
        if c.document_title.lower() in retrieved_titles
    ]
    if not valid_citations:
        result = result.model_copy(update={"confidence": "Low"})
    else:
        result = result.model_copy(update={"citations": valid_citations})

    # Step 2: stamp context_meta
    result = result.model_copy(update={
        "context_meta": result.context_meta.model_copy(update={
            "soil_data_available": soil.get("available", False),
            "weather_data_available": weather.get("available", False),
            "county_fips": county_fips,
        })
    })

    # Step 3: NLI claim verification
    answer_prose = " ".join(filter(None, [
        result.problem_summary,
        " ".join(result.recommended_actions),
    ]))
    retrieved_chunks = [
        {
            "snippet": (doc.page_content or "")[:500] if hasattr(doc, "page_content")
                       else doc.get("snippet", ""),
        }
        for doc in docs
    ]

    nli_result = await citation_guard_v2.verify_answer(answer_prose, retrieved_chunks)
    confidence_score: float = nli_result["confidence_score"]
    claim_verification = nli_result["claim_verification"]

    escalation = None
    if confidence_score < citation_guard_v2.ESCALATION_THRESHOLD:
        escalation = citation_guard_v2.escalation_cue(county_fips)

    update: dict = {
        "confidence_score": confidence_score,
        "claim_verification": claim_verification,
        "escalation": escalation,
    }

    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        escalation_msg = escalation or "Please contact your local UA Extension office."
        update.update({
            "problem_summary": "",
            "likely_causes": [],
            "recommended_actions": [],
            "products_rates": [],
            "warnings": [escalation_msg],
        })

    return result.model_copy(update=update)


async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
) -> tuple[AdvisoryResponse, list[dict]]:
    """Returns (advisory, retrieved_chunks)."""
    context_task = asyncio.create_task(get_context(county_fips))

    namespace = CATEGORY_TO_NAMESPACE.get(category)
    vectorstore = _get_vectorstore()

    retriever_kwargs = {"k": config.TOP_K_RETRIEVAL}
    if namespace:
        retriever_kwargs["namespace"] = namespace

    docs = await asyncio.to_thread(
        vectorstore.similarity_search,
        message,
        **retriever_kwargs,
    )

    ctx = await context_task
    soil = ctx["soil"]
    weather = ctx["weather"]

    county_info = get_county_info(county_fips)
    county_name = county_info["county_name"] if county_info else county_fips

    system_prompt = build_system_prompt(
        soil_context=soil,
        weather_context=weather,
        retrieved_docs=docs,
        session_history=session_history,
        language=language,
        is_safety_critical=(category == "SAFETY_CRITICAL"),
        county_name=county_name,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message),
    ]

    structured_llm = _get_llm().with_structured_output(AdvisoryResponse)

    result = None
    last_err = None
    for attempt in range(2):
        try:
            result = await structured_llm.ainvoke(messages)
            break
        except Exception as e:
            last_err = e
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                try:
                    groq = _get_groq_llm()
                    if groq:
                        result = await groq.with_structured_output(AdvisoryResponse).ainvoke(messages)
                        break
                except Exception as groq_err:
                    last_err = groq_err
                break
            if attempt == 1:
                raise RuntimeError(f"Structured output failed after 2 attempts: {e}") from e

    if result is None:
        raise RuntimeError(f"RAG generation failed: {last_err}") from last_err

    advisory = await _postprocess_async(result, docs, soil, weather, county_fips)
    retrieved_chunks = [
        {
            "document_title": d.metadata.get("document_title", ""),
            "section_heading": d.metadata.get("section_heading", ""),
            "snippet": (d.page_content or "")[:500],
        }
        for d in docs
    ]
    return advisory, retrieved_chunks
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && pytest tests/test_citation_guard_v2.py -k "postprocess" -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && pytest tests/ -v
```

Expected: all existing tests still pass + new tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/rag.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(f2): wire NLI citation guard into rag._postprocess_async"
```

---

## Task 6: `NLIConfidenceBadge.jsx` + i18n

**Files:**
- Create: `frontend/src/components/advisory/NLIConfidenceBadge.jsx`
- Modify: `frontend/src/constants/i18n.js`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/constants/i18n.js`, find the EN block (around line 26 where `confidence` key is) and add after `confidenceLow`:

```js
nliScore: 'NLI Score',
escalationContact: 'Contact your county Extension agent:',
```

Find the ES block (around line 233) and add after `confidenceLow`:

```js
nliScore: 'Puntuación NLI',
escalationContact: 'Contacta a tu agente de extensión del condado:',
```

- [ ] **Step 2: Create `NLIConfidenceBadge.jsx`**

```jsx
import { useLang } from '../../contexts/LangContext'

const STYLES = {
  green: 'bg-field text-white dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border',
  amber: 'bg-harvest text-charcoal dark:bg-hc-bg dark:text-hc-fg dark:border-2 dark:border-hc-border',
  red:   'bg-arred text-white dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border',
}

function scoreColor(score) {
  if (score >= 0.7) return 'green'
  if (score >= 0.4) return 'amber'
  return 'red'
}

export default function NLIConfidenceBadge({ confidence_score }) {
  const { t } = useLang()
  if (confidence_score == null) return null
  const color = scoreColor(confidence_score)
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${STYLES[color]}`}>
      {t.nliScore}: {confidence_score.toFixed(2)}
    </span>
  )
}
```

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/advisory/NLIConfidenceBadge.jsx frontend/src/constants/i18n.js
git commit -m "feat(f2): add NLIConfidenceBadge component and i18n keys"
```

---

## Task 7: `EscalationCard.jsx` + Wire into `AdvisoryCard`

**Files:**
- Create: `frontend/src/components/advisory/EscalationCard.jsx`
- Modify: `frontend/src/components/advisory/AdvisoryCard.jsx`

- [ ] **Step 1: Create `EscalationCard.jsx`**

```jsx
import { useLang } from '../../contexts/LangContext'

export default function EscalationCard({ escalation }) {
  const { t } = useLang()
  if (!escalation) return null
  return (
    <div className="bg-harvest/20 dark:bg-hc-bg border border-harvest dark:border-2 dark:border-hc-border rounded-lg px-4 py-3 flex items-start gap-3 my-2">
      <span className="text-xl" role="img" aria-label="phone">📞</span>
      <div>
        <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">{t.escalationContact}</p>
        <p className="text-sm text-charcoal dark:text-hc-fg mt-1">{escalation}</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Modify `AdvisoryCard.jsx`**

Add two imports at the top of the import block:

```jsx
import NLIConfidenceBadge from './NLIConfidenceBadge'
import EscalationCard from './EscalationCard'
```

In `AdvisoryCardInner`, update the header section and add `EscalationCard` after `ConfidenceExplainer`:

```jsx
function AdvisoryCardInner({ response, messageId, category }) {
  return (
    <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-4 my-2 w-full max-w-2xl">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <ConfidenceBadge confidence={response.confidence} />
          <NLIConfidenceBadge confidence_score={response.confidence_score} />
          <CropChip category={category} />
        </div>
        <ContextMetaBar meta={response.context_meta} />
      </div>
      <ConfidenceExplainer explanation={response.confidence_explanation} />
      <EscalationCard escalation={response.escalation} />

      {response.confidence === 'Low' && <LowConfidenceBanner />}
      <WarningsBanner warnings={response.warnings} />
      <ProblemSummary summary={response.problem_summary} />
      <LikelyCauses causes={response.likely_causes} />
      <RecommendedActions actions={response.recommended_actions} />
      <ProductsRates products={response.products_rates} />
      <CitationsSection citations={response.citations} />
      <FeedbackWidget messageId={messageId} />
    </div>
  )
}
```

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: 0 errors.

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npm run test
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/advisory/EscalationCard.jsx frontend/src/components/advisory/AdvisoryCard.jsx
git commit -m "feat(f2): add EscalationCard and wire NLI badge into AdvisoryCard"
```

---

## Task 8: Nightly Eval — Confidence Mean Aggregation

**Files:**
- Modify: `backend/services/nightly_alerts.py`

- [ ] **Step 1: Find where eval_runs is written**

```bash
grep -n "eval_runs\|answer_correct" backend/services/nightly_alerts.py | head -20
```

Note the line numbers where `eval_runs` is upserted/inserted.

- [ ] **Step 2: Add `answer_confidence_mean` to the eval_runs upsert**

In `backend/services/nightly_alerts.py`, find the block that writes to `eval_runs`. Add `answer_confidence_mean` computation:

```python
# After gathering eval results, compute confidence mean
# Query recent chat_messages with confidence_score set
confidence_rows = (
    supabase.table("chat_messages")
    .select("confidence_score")
    .not_.is_("confidence_score", "null")
    .order("created_at", desc=True)
    .limit(100)
    .execute()
)
conf_scores = [r["confidence_score"] for r in (confidence_rows.data or []) if r.get("confidence_score") is not None]
answer_confidence_mean = sum(conf_scores) / len(conf_scores) if conf_scores else None
```

Then include `answer_confidence_mean` in the eval_runs insert/upsert dict:
```python
eval_payload["answer_confidence_mean"] = answer_confidence_mean
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
cd backend && pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/services/nightly_alerts.py
git commit -m "feat(f2): add answer_confidence_mean aggregation to nightly eval"
```

---

## Task 9: Save `confidence_score` + `escalated` to DB

**Files:**
- Modify: `backend/routers/query.py` (or wherever `chat_messages` is saved)

- [ ] **Step 1: Find where chat_messages is written**

```bash
grep -n "chat_messages\|content_type\|retrieved_chunks" backend/routers/query.py | head -20
```

Note the line where the message row is inserted.

- [ ] **Step 2: Add `confidence_score` and `escalated` to the insert**

Find the dict passed to `supabase.table("chat_messages").insert(...)`. Add:

```python
"confidence_score": advisory.confidence_score,
"escalated": advisory.escalation is not None,
```

- [ ] **Step 3: Run backend tests**

```bash
cd backend && pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/query.py
git commit -m "feat(f2): persist confidence_score and escalated flag to chat_messages"
```

---

## Self-Review Checklist

- [x] Migration 008 covers all 3 columns from PRD (`confidence_score`, `escalated`, `answer_confidence_mean`)
- [x] `ClaimResult` label values match between model (`advisory.py`) and guard (`citation_guard_v2.py`)
- [x] `ESCALATION_THRESHOLD` and `SUPPRESSION_THRESHOLD` defined as constants, not magic numbers
- [x] `verify_answer` returns `escalation: None` — caller (`_postprocess_async`) stamps it after FIPS lookup
- [x] `NLIConfidenceBadge` returns `null` when `confidence_score` is absent (backwards compat)
- [x] `_postprocess_async` renamed from `_postprocess` — update call site in `run_rag_query` ✓
- [x] Scraper includes full 75-county FIPS mapping
- [x] Eval aggregation handles empty `conf_scores` list (no division by zero)
- [x] All test files follow existing `importlib.import_module` + sys.path pattern

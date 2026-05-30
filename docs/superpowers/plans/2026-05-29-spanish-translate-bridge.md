# Spanish Translate-Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dedicated Spanish RAG with a translate-bridge: Spanish query → translate to English → existing English RAG (unchanged) → translate answer prose back to Spanish.

**Architecture:** The entire internal pipeline (classify, retrieve, generate, NLI citation guard) stays English. A new `services/translation.py` translates the query in (ES→EN) and the final advisory's user-facing prose out (EN→ES), reusing the existing LLM provider chain (Groq primary, Gemini fallback, local when `LLM_PRIMARY=local`). Trigger is the UI `req.language=="es"` flag.

**Tech Stack:** FastAPI, LangChain (`langchain_groq`, `langchain_google_genai`), Pydantic v2 (`AdvisoryResponse`), pytest.

**Spec:** `docs/superpowers/specs/2026-05-29-spanish-translate-bridge-design.md`

**Env note:** `pytest` may crash on this Windows box via a `pyarrow` import (pandas). If so, run the new pure-logic tests directly, e.g. `python -m pytest backend/tests/test_translation.py -p no:cacheprovider` from `backend/`, or verify with `python -c` snippets. CI (Linux) runs pytest normally.

---

### Task 1: Translation service — query in (ES→EN)

**Files:**
- Create: `backend/services/translation.py`
- Test: `backend/tests/test_translation.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_translation.py
import sys, asyncio, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on path


def _patch_providers(monkeypatch, reply):
    """Make translation._providers() return one fake LLM whose ainvoke returns `reply`."""
    mod = importlib.import_module("services.translation")

    class _Resp:
        def __init__(self, c): self.content = c

    class _LLM:
        async def ainvoke(self, messages):
            return _Resp(reply)

    monkeypatch.setattr(mod, "_providers", lambda: [_LLM()])
    return mod


def test_translate_to_en_returns_translation(monkeypatch):
    mod = _patch_providers(monkeypatch, "How much nitrogen for my rice?")
    out = asyncio.run(mod.translate_to_en("¿Cuánto nitrógeno para mi arroz?"))
    assert out == "How much nitrogen for my rice?"


def test_translate_to_en_falls_back_to_original_on_failure(monkeypatch):
    mod = importlib.import_module("services.translation")
    monkeypatch.setattr(mod, "_providers", lambda: [])  # no provider available
    original = "¿Cuánto nitrógeno?"
    assert asyncio.run(mod.translate_to_en(original)) == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_translation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.translation'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/translation.py
"""ES<->EN translation at the pipeline edges (the translate-bridge).

The query is translated ES->EN before the all-English RAG pipeline; the final
advisory's user-facing prose is translated EN->ES for display. Reuses the LLM
provider chain (Groq primary, Gemini fallback, local when LLM_PRIMARY=local).
"""
import json
import logging
import re

from langchain_core.messages import HumanMessage

import config

logger = logging.getLogger(__name__)

_groq = None
_gemini = None


def _get_groq():
    global _groq
    if _groq is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq = ChatGroq(model=config.GROQ_FAST_MODEL, api_key=config.GROQ_API_KEY,
                         temperature=0)
    return _groq


def _get_gemini():
    global _gemini
    if _gemini is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _gemini = ChatGoogleGenerativeAI(model=config.GEMINI_CLASSIFIER_MODEL,
                                         google_api_key=config.GOOGLE_API_KEY,
                                         temperature=0)
    return _gemini


def _providers():
    if config.LLM_PRIMARY == "local":
        from services.local_llm import get_local_chat
        return [get_local_chat()]
    return ([_get_groq(), _get_gemini()] if config.LLM_PRIMARY == "groq"
            else [_get_gemini(), _get_groq()])


async def _call(prompt: str) -> str | None:
    """Call the first working provider; return stripped text or None on total failure."""
    for llm in _providers():
        if llm is None:
            continue
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            return (resp.content or "").strip()
        except Exception as e:  # quota or transient; try next provider
            logger.warning("translation provider failed: %s", str(e)[:150])
    return None


async def translate_to_en(text: str) -> str:
    """Translate a Spanish farmer query to English. Falls back to the original
    text on failure (degraded retrieval; the citation guard catches bad results)."""
    if not text or not text.strip():
        return text
    prompt = (
        "Translate this Arkansas farmer's question to English. Output ONLY the "
        "English translation — no quotes, no preamble.\n\n" + text
    )
    out = await _call(prompt)
    return out or text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_translation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/translation.py backend/tests/test_translation.py
git commit -m "feat(translation): translate_to_en query bridge (ES->EN, LLM, fallback to original)"
```

---

### Task 2: Translation service — advisory out (EN→ES, prose only)

**Files:**
- Modify: `backend/services/translation.py`
- Test: `backend/tests/test_translation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_translation.py
import json


def _advisory():
    from models.advisory import AdvisoryResponse, Cause, Product, Citation, ContextMeta
    return AdvisoryResponse(
        problem_summary="Rice shows nitrogen deficiency.",
        likely_causes=[Cause(cause="Low N", explanation="Insufficient nitrogen applied.")],
        recommended_actions=["Apply nitrogen at green-up."],
        products_rates=[Product(product="Urea", rate="150 lb N/acre", application_method="broadcast")],
        warnings=["Follow label directions."],
        citations=[Citation(document_title="Arkansas Rice Handbook", section="N management")],
        confidence="Medium",
        confidence_explanation="Grounded in one source.",
        language="en",
        context_meta=ContextMeta(soil_data_available=True, weather_data_available=True, county_fips="05031"),
    )


def test_translate_advisory_translates_prose_preserves_products(monkeypatch):
    # Fake LLM echoes a JSON array marking each input with a 'ES:' prefix, same length/order.
    mod = importlib.import_module("services.translation")

    class _Resp:
        def __init__(self, c): self.content = c

    class _LLM:
        async def ainvoke(self, messages):
            arr = json.loads(messages[0].content.split("\n\n", 1)[1])
            return _Resp(json.dumps(["ES:" + s for s in arr], ensure_ascii=False))

    monkeypatch.setattr(mod, "_providers", lambda: [_LLM()])
    out = asyncio.run(mod.translate_advisory_to_es(_advisory()))

    assert out.problem_summary == "ES:Rice shows nitrogen deficiency."
    assert out.likely_causes[0].cause == "ES:Low N"
    assert out.likely_causes[0].explanation == "ES:Insufficient nitrogen applied."
    assert out.recommended_actions[0] == "ES:Apply nitrogen at green-up."
    assert out.warnings[0] == "ES:Follow label directions."
    assert out.confidence_explanation == "ES:Grounded in one source."
    # PRESERVED verbatim:
    assert out.products_rates[0].product == "Urea"
    assert out.products_rates[0].rate == "150 lb N/acre"
    assert out.citations[0].document_title == "Arkansas Rice Handbook"
    assert out.language == "es"


def test_translate_advisory_falls_back_to_english_on_failure(monkeypatch):
    mod = importlib.import_module("services.translation")
    monkeypatch.setattr(mod, "_providers", lambda: [])  # no provider
    adv = _advisory()
    out = asyncio.run(mod.translate_advisory_to_es(adv))
    assert out.problem_summary == "Rice shows nitrogen deficiency."  # unchanged English
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_translation.py -k advisory -v`
Expected: FAIL — `AttributeError: module 'services.translation' has no attribute 'translate_advisory_to_es'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/services/translation.py`:

```python
from models.advisory import AdvisoryResponse  # noqa: E402  (top of file is fine too)


def _parse_str_array(raw: str | None, n: int) -> list[str] | None:
    """Parse a JSON array of exactly n strings; None if it can't be trusted."""
    if not raw:
        return None
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(arr, list) or len(arr) != n:
        return None
    return [str(x) for x in arr]


async def translate_advisory_to_es(advisory: AdvisoryResponse) -> AdvisoryResponse:
    """Translate the advisory's user-facing prose to Spanish, preserving products,
    rates, citations, escalation, and confidence fields. Falls back to the
    untranslated English advisory on failure."""
    # Collect prose strings in a FIXED order (must match the remap below exactly).
    strings: list[str] = [advisory.problem_summary]
    for c in advisory.likely_causes:
        strings.append(c.cause)
        strings.append(c.explanation)
    strings.extend(advisory.recommended_actions)
    strings.extend(advisory.warnings)
    strings.append(advisory.confidence_explanation)

    prompt = (
        "Translate each string in this JSON array to Spanish for an Arkansas "
        "farmer. Keep product names, chemical names, numbers, rates, and units "
        "unchanged. Preserve the array length and order exactly. Return ONLY a "
        "JSON array of strings.\n\n" + json.dumps(strings, ensure_ascii=False)
    )
    translated = _parse_str_array(await _call(prompt), len(strings))
    if translated is None:
        logger.warning("advisory translation failed — returning English advisory")
        return advisory

    # Remap by index, mirroring the collection order above.
    i = 0
    problem_summary = translated[i]; i += 1
    new_causes = []
    for c in advisory.likely_causes:
        new_causes.append(c.model_copy(update={"cause": translated[i], "explanation": translated[i + 1]}))
        i += 2
    n_actions = len(advisory.recommended_actions)
    recommended_actions = translated[i:i + n_actions]; i += n_actions
    n_warn = len(advisory.warnings)
    warnings = translated[i:i + n_warn]; i += n_warn
    confidence_explanation = translated[i]; i += 1

    return advisory.model_copy(update={
        "problem_summary": problem_summary,
        "likely_causes": new_causes,
        "recommended_actions": recommended_actions,
        "warnings": warnings,
        "confidence_explanation": confidence_explanation,
        "language": "es",
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_translation.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/translation.py backend/tests/test_translation.py
git commit -m "feat(translation): translate_advisory_to_es (prose only, preserve products/citations, index remap, English fallback)"
```

---

### Task 3: Wire the bridge into `query.py`

**Files:**
- Modify: `backend/routers/query.py`
- Test: `backend/tests/test_query_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_query_bridge.py
import sys, asyncio, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_es_request_translates_in_and_out(monkeypatch):
    q = importlib.import_module("routers.query")
    calls = {"to_en": 0, "to_es": 0}

    async def fake_to_en(text):
        calls["to_en"] += 1
        return "EN: " + text

    async def fake_to_es(adv):
        calls["to_es"] += 1
        return adv

    monkeypatch.setattr(q, "translate_to_en", fake_to_en)
    monkeypatch.setattr(q, "translate_advisory_to_es", fake_to_es)
    # maybe_translate_query is the helper under test
    out = asyncio.run(q.maybe_translate_query("¿hola?", "es"))
    assert out == "EN: ¿hola?"
    assert calls["to_en"] == 1

    out_en = asyncio.run(q.maybe_translate_query("hello", "en"))
    assert out_en == "hello"
    assert calls["to_en"] == 1  # not called again for EN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_query_bridge.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'maybe_translate_query'`

- [ ] **Step 3: Write minimal implementation**

In `backend/routers/query.py`, add the import near the existing service imports:

```python
from services.translation import translate_to_en, translate_advisory_to_es
```

Add this helper near the top-level functions (module scope):

```python
async def maybe_translate_query(message: str, language: str) -> str:
    """ES bridge: translate the query to English so the all-English pipeline runs.
    EN passes through unchanged."""
    if language == "es":
        return await translate_to_en(message)
    return message
```

Then in the request handler, replace the message/lang setup + the classify/detect block. Current code (`query.py` around lines 72-104):

```python
    language = req.language

    category = await classify_query(req.message, last_category=req.last_category)
    detected_lang = detect_language(req.message)
    ...
            result, retrieved_chunks = await run_rag_query(
                message=req.message,
                county_fips=county_fips,
                language=language,
                category=category,
                session_history=req.session_history,
                rice_fields=rice_fields,
                detected_lang=detected_lang,
            )
```

becomes:

```python
    language = req.language

    # Translate-bridge: ES query -> EN; the whole RAG pipeline runs in English.
    en_message = await maybe_translate_query(req.message, language)
    category = await classify_query(en_message, last_category=req.last_category)
    ...
            result, retrieved_chunks = await run_rag_query(
                message=en_message,
                county_fips=county_fips,
                language="en",
                category=category,
                session_history=req.session_history,
                rice_fields=rice_fields,
            )
            if language == "es":
                result = await translate_advisory_to_es(result)
```

Remove the `detect_language` import and the `detected_lang = detect_language(req.message)` line. (The OUT_OF_SCOPE / SAFETY_CRITICAL branches between them stay; they already use `category`, which is now computed from `en_message`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_query_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_bridge.py
git commit -m "feat(query): wire translate-bridge — ES query translated in, advisory translated out"
```

---

### Task 4: Make `run_rag_query` English-only (drop ES routing)

**Files:**
- Modify: `backend/services/rag.py`
- Modify: `backend/services/embedding.py`
- Modify: `backend/config.py`
- Modify: `evals/answer_eval_full.py` (caller passes no `detected_lang`)

- [ ] **Step 1: Remove the ES vectorstore + routing in `rag.py`**

Delete the `_vectorstore_es`, `_VECTORSTORE_ES_UNAVAILABLE` globals and the entire `_get_vectorstore_es()` function. In `run_rag_query`, remove the `detected_lang: str = "en"` parameter and replace the routing block:

```python
    # Route to multilingual index for Spanish queries; fall back to EN if unavailable
    if detected_lang == "es":
        vectorstore = _get_vectorstore_es() or _get_vectorstore()
    else:
        vectorstore = _get_vectorstore()
```

with:

```python
    vectorstore = _get_vectorstore()
```

Remove the now-unused `BGEEmbeddings` from the import line `from services.embedding import MiniLMEmbeddings, BGEEmbeddings` → `from services.embedding import MiniLMEmbeddings`.

- [ ] **Step 2: Remove `BGEEmbeddings` + multilingual model from `embedding.py`**

Delete `class BGEEmbeddings`, `get_multilingual_model`, `_multilingual_model`, and `MULTILINGUAL_MODEL_NAME`.

- [ ] **Step 3: Remove multilingual config from `config.py`**

Delete `MULTILINGUAL_EMBEDDING_MODEL_PATH` and `PINECONE_MULTILINGUAL_INDEX_NAME`.

- [ ] **Step 4: Update the eval caller**

In `evals/answer_eval_full.py`, the `run_rag_query(...)` call passes `language=lang`. Change it to `language="en"` (retrieval/generation is always English now; the lang field is irrelevant to the English pipeline). Leave the per-namespace harness otherwise unchanged.

- [ ] **Step 5: Verify imports resolve + grep clean**

Run: `cd backend && python -c "import services.rag, services.embedding, config; print('imports OK')"`
Expected: `imports OK`

Run: `git grep -n "detected_lang\|BGEEmbeddings\|_get_vectorstore_es\|MULTILINGUAL" backend/ evals/`
Expected: no matches (except possibly comments you should also remove).

- [ ] **Step 6: Commit**

```bash
git add backend/services/rag.py backend/services/embedding.py backend/config.py evals/answer_eval_full.py
git commit -m "refactor(rag): English-only pipeline — remove ES vectorstore routing + BGE multilingual path"
```

---

### Task 5: Remove the remaining ES infra

**Files:**
- Modify: `backend/services/classifier.py` (remove `detect_language`)
- Delete: `ingestion/translate_corpus.py`, `ingestion/ingest_es_chunks.py`, `ingestion/create_multilingual_index.py`
- Delete: `backend/tests/test_f1_lang_routing.py`
- Modify: `.github/workflows/nightly-eval.yml` (remove the `eval-es` job)

- [ ] **Step 1: Remove `detect_language`**

In `backend/services/classifier.py`, delete the `detect_language` function and the now-unused `langdetect` imports (`from langdetect import detect, LangDetectException`, `from langdetect import DetectorFactory as _DF`, `_DF.seed = 0`). Confirm nothing else imports it:

Run: `git grep -n "detect_language\|langdetect" backend/`
Expected: no matches.

- [ ] **Step 2: Delete ES ingestion scripts + the routing test**

```bash
git rm ingestion/translate_corpus.py ingestion/ingest_es_chunks.py ingestion/create_multilingual_index.py backend/tests/test_f1_lang_routing.py
```

- [ ] **Step 3: Remove the `eval-es` CI job**

In `.github/workflows/nightly-eval.yml`, delete the entire `eval-es:` job block (the second job, "Run retrieval eval on Spanish corpus"). Keep the base `eval:` job.

- [ ] **Step 4: Verify**

Run: `cd backend && python -c "import services.classifier; print('classifier OK')"`
Expected: `classifier OK`
Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/nightly-eval.yml'))"` (from repo root)
Expected: no error (valid YAML).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dedicated ES RAG infra (detect_language, ES ingestion scripts, eval-es CI, F1 routing test)"
```

---

### Task 6: Bridge eval — validate retrieval + end-to-end

**Files:**
- Create: `evals/eval_bridge.py`

- [ ] **Step 1: Write the bridge retrieval eval**

`ar_agqa_es.jsonl` has Spanish `query` + English `chunk_text` + English `chunk_id` + `namespace`. This script translates each ES query to EN, queries the gte index, and reports per-namespace recall of the gold chunk.

```python
# evals/eval_bridge.py
"""Bridge eval: ES query -> translate_to_en -> gte EN retrieval -> recall of the
English gold chunk, per namespace. Validates the translate-bridge end of F1."""
import asyncio, json, os, sys
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from services.translation import translate_to_en  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from pinecone import Pinecone  # noqa: E402

EVAL = Path(__file__).parent / "ar_agqa_es.jsonl"
INDEX = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte")
MODEL = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
KS = [1, 5, 20]


async def main():
    ev = [json.loads(l) for l in open(EVAL, encoding="utf-8")]
    m = SentenceTransformer(MODEL, device="cuda")
    idx = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(INDEX)
    hits = defaultdict(lambda: {k: 0 for k in KS})
    counts = defaultdict(int)
    for e in ev:
        en = await translate_to_en(e["query"])
        counts[e["namespace"]] += 1
        qv = m.encode(en, normalize_embeddings=True).tolist()
        r = idx.query(vector=qv, top_k=max(KS), namespace=e["namespace"], include_values=False)
        ids = [mm["id"] for mm in r.get("matches", [])]
        for k in KS:
            if e["chunk_id"] in ids[:k]:
                hits[e["namespace"]][k] += 1
    print("=== bridge retrieval recall (ES->EN->gte) ===")
    for ns in sorted(counts):
        n = counts[ns]
        print(f"{ns:>9} n={n:>3}  " + "  ".join(f"@{k}={hits[ns][k]/n:.2f}" for k in KS))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it (local, free)**

Run (from repo root):
```bash
LLM_PRIMARY=local EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte python evals/eval_bridge.py
```
On Windows PowerShell:
```powershell
$env:LLM_PRIMARY="local"; $env:EMBEDDING_MODEL_PATH="thenlper/gte-base"; $env:PINECONE_INDEX_NAME="agroar-prod-gte"; python evals/eval_bridge.py
```
Expected: a per-namespace recall table. Success criterion: bridge recall is in the same ballpark as the EN `eval_set_v2` gte recall (poultry ~0.45@5, soybeans ~0.34@5). Big gaps indicate query-translation problems.

- [ ] **Step 3: End-to-end ES (optional, GPU-heavy)**

Run the full answer eval against the ES set through the bridge once `query.py` is wired — verify suppression/correctness per crop are comparable to EN. (Reuse `evals/answer_eval_full.py`; point it at `ar_agqa_es.jsonl` via a small `--eval-set` flag if added, or hardcode for a one-off.)

- [ ] **Step 4: Commit**

```bash
git add evals/eval_bridge.py
git commit -m "feat(evals): translate-bridge retrieval eval (ES query -> EN -> gte recall)"
```

---

## Post-implementation

- Update `README.md` + CLAUDE.md: Spanish is now a translate-bridge over the English RAG (no dedicated ES index); remove ES-corpus/multilingual references.
- (Optional) delete the `agroar-prod-multilingual` Pinecone index from the account.
- The gte EN index (`agroar-prod-gte`) must be the active EN retrieval index in prod env for the bridge to perform (`EMBEDDING_MODEL_PATH=thenlper/gte-base`, `PINECONE_INDEX_NAME=agroar-prod-gte`).

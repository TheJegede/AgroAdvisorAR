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
from models.advisory import AdvisoryResponse
from utils.llm import _providers

logger = logging.getLogger(__name__)


async def _call_llm(prompt: str) -> str | None:
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
    if not (text and text.strip()):
        return text
    prompt = (
        "Translate this Arkansas farmer's question to English. Output ONLY the "
        "English translation — no quotes, no preamble.\n\n" + text
    )
    out = await _call_llm(prompt)
    return out or text


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
    if not all(isinstance(x, str) for x in arr):
        return None  # element-type corruption (object/number) — don't ship it
    return arr


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
    has_escalation = bool(advisory.escalation)
    if has_escalation:
        strings.append(advisory.escalation)  # contact prose; names/phones kept by the prompt

    prompt = (
        "Translate each string in this JSON array to Spanish for an Arkansas "
        "farmer. Keep product names, chemical names, numbers, rates, and units "
        "unchanged. Preserve the array length and order exactly. Return ONLY a "
        "JSON array of strings.\n\n" + json.dumps(strings, ensure_ascii=False)
    )
    translated = _parse_str_array(await _call_llm(prompt), len(strings))
    if translated is None:
        logger.warning("advisory translation failed — returning English advisory")
        return advisory

    # Remap by index, mirroring the collection order above.
    i = 0
    problem_summary = translated[i]; i += 1
    new_causes = []
    for c in advisory.likely_causes:
        new_causes.append(c.model_copy(update={"cause": translated[i],
                                               "explanation": translated[i + 1]}))
        i += 2
    n_actions = len(advisory.recommended_actions)
    recommended_actions = translated[i:i + n_actions]; i += n_actions
    n_warn = len(advisory.warnings)
    warnings = translated[i:i + n_warn]; i += n_warn
    confidence_explanation = translated[i]; i += 1
    update = {
        "problem_summary": problem_summary,
        "likely_causes": new_causes,
        "recommended_actions": recommended_actions,
        "warnings": warnings,
        "confidence_explanation": confidence_explanation,
        "language": "es",
    }
    if has_escalation:
        update["escalation"] = translated[i]; i += 1
    return advisory.model_copy(update=update)

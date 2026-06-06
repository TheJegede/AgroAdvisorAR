"""LLM-as-judge for answer correctness.

Compares a candidate advisory to a gold chunk (the eval set's labeled
correct source). Returns a 0.0–1.0 score per item:
  1.0 — answer correctly applies the gold-chunk info
  0.5 — partially correct / loosely aligned
  0.0 — incorrect, hallucinated, or unrelated

Uses Groq llama-3.3-70b directly (no Gemini fallback) for cost + speed.
"""
import os
import json
import random
from typing import Iterable
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage


JUDGE_SYSTEM = (
    "You are an agricultural extension agent grading a chatbot's advisory. "
    "You will see a farmer query, the chatbot's advisory summary, and a "
    "reference passage from the University of Arkansas Extension corpus. "
    "Score how well the advisory uses the same information as the reference "
    "to answer the query. Be strict: penalize hallucinations, off-topic "
    "answers, and contradictions of the reference."
)

JUDGE_USER_TEMPLATE = """FARMER QUERY:
{query}

CHATBOT ADVISORY SUMMARY:
{answer}

REFERENCE PASSAGE (gold):
{reference}

Return ONLY a JSON object of the form:
{{"score": <1.0 | 0.5 | 0.0>, "rationale": "<one short sentence>"}}

Score guide:
- 1.0 — advisory correctly conveys the reference's information for the query
- 0.5 — partially correct or loosely aligned (some right, some wrong/missing)
- 0.0 — wrong, hallucinated, contradicts the reference, or off-topic"""


def _summarize_advisory(advisory: dict) -> str:
    """Compact the structured advisory into a single block for the judge."""
    parts = [f"Problem summary: {advisory.get('problem_summary', '')}"]
    causes = advisory.get("likely_causes") or []
    if causes:
        parts.append("Likely causes: " + "; ".join(
            f"{c.get('cause', '')} — {c.get('explanation', '')}" for c in causes
        ))
    actions = advisory.get("recommended_actions") or []
    if actions:
        parts.append("Recommended actions: " + "; ".join(actions))
    products = advisory.get("products_rates") or []
    if products:
        parts.append("Products: " + "; ".join(
            f"{p.get('product', '')} @ {p.get('rate', '')}" for p in products
        ))
    return "\n".join(parts)


_judge_llm: ChatGroq | None = None


def _get_judge() -> ChatGroq:
    global _judge_llm
    if _judge_llm is None:
        _judge_llm = ChatGroq(
            model=os.environ.get("JUDGE_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.environ["GROQ_API_KEY"],
            temperature=0,
        )
    return _judge_llm


_deepinfra_judge_llm = None


def _get_deepinfra_judge():
    global _deepinfra_judge_llm
    if _deepinfra_judge_llm is None:
        from langchain_openai import ChatOpenAI
        _deepinfra_judge_llm = ChatOpenAI(
            model=os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
            openai_api_key=os.environ["DEEPINFRA_API_KEY"],
            openai_api_base="https://api.deepinfra.com/v1",
            temperature=0,
        )
    return _deepinfra_judge_llm


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    # A bare "exceeded" false-positives on context_length_exceeded — an
    # oversized prompt would be misrouted to the DeepInfra fallback (which also
    # overflows), turning a deterministic input-size bug into a paid double
    # failure. Match only genuine rate/quota signals.
    if "context_length_exceeded" in msg or "context length" in msg:
        return False
    return any(k in msg for k in (
        "rate_limit", "rate limit", "429", "quota",
        "too many requests", "tokens per", "tpm", "rpm",
    ))


def score_item(query: str, advisory: dict, gold_chunk_text: str) -> tuple[float, str]:
    answer_block = _summarize_advisory(advisory)
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=JUDGE_USER_TEMPLATE.format(
            query=query,
            answer=answer_block,
            reference=gold_chunk_text[:2000],
        )),
    ]
    try:
        resp = _get_judge().invoke(messages)
    except Exception as e:
        if _is_quota_error(e) and os.environ.get("DEEPINFRA_API_KEY"):
            resp = _get_deepinfra_judge().invoke(messages)
        else:
            raise
    raw = (resp.content or "").strip()
    # Strip code fences if the model wrapped its JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0.0))
        rationale = parsed.get("rationale", "")
    except Exception:
        score, rationale = 0.0, f"parse failure: {raw[:200]}"
    score = max(0.0, min(1.0, score))
    return score, rationale


def sample_items(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    n = min(n, len(items))
    return rng.sample(items, n)

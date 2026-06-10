# evals/diagnostic/conditional_judge.py
"""Conditional-completeness judge: did the GENERATED answer preserve the
condition->branch structure of the gold conditional answer?

Separate from containment_judge: containment reads the retrieved CHUNKS, this
reads the generated ANSWER. Uses Gemini 2.5-flash — a different model from the
70B generator, so the generator never grades itself.
"""
import os
import re
import json
import time
from dataclasses import dataclass
from typing import Optional


def flatten_advisory(advisory: dict) -> str:
    """Join every answer-bearing field of an advisory into one candidate string."""
    parts: list[str] = []
    for key in ("problem_summary", "detailed_explanation"):
        val = advisory.get(key)
        if val:
            parts.append(str(val))
    for key in ("key_points", "recommended_actions", "warnings"):
        for item in advisory.get(key) or []:
            if item:
                parts.append(str(item))
    for pr in advisory.get("products_rates") or []:
        bits = [pr.get("product"), pr.get("rate"), pr.get("application_method")]
        line = " ".join(b for b in bits if b)
        if line:
            parts.append(line)
    return "\n".join(parts)


_TRANSIENT_RE = re.compile(r"\b(503|429|unavailable|overloaded|deadline)\b", re.I)


def _is_transient(err: Exception) -> bool:
    return bool(_TRANSIENT_RE.search(str(err)))


JUDGE_MODEL = os.environ.get("CONDITIONAL_JUDGE_MODEL", "gemini-2.5-flash")


@dataclass
class CompletenessResult:
    preserved: bool
    missing: Optional[str]


JUDGE_SYSTEM = (
    "You are a conditional-completeness checker. You are given a GOLD ANSWER that "
    "contains a conditional rule — a rate, threshold, timing, or restriction that "
    "depends on a stated condition (e.g. soil texture, crop growth stage or weeks "
    "after heading, crop variety, water clarity, application timing) — and a "
    "CANDIDATE ANSWER produced by an advisory system. Decide ONLY whether the "
    "candidate preserves the SAME qualifying condition(s) and their matching "
    "value(s)/branch(es). Ignore wording, extra content, and citations. The "
    "candidate is preserved=true ONLY if every condition in the gold appears in the "
    "candidate with its corresponding branch. If the candidate gives a bare value "
    "without its governing condition, or drops a branch, preserved=false. Do NOT "
    "answer the farmer's question or add knowledge."
)

JUDGE_TEMPLATE = """GOLD ANSWER:
{gold_answer}

CANDIDATE ANSWER:
{candidate_answer}

Return ONLY a JSON object:
{{"preserved": <true if every gold condition appears in the candidate with its matching branch, else false>, "missing": "<short description of the dropped condition/branch, or null>"}}"""


def build_conditional_prompt(gold_answer: str, candidate_answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        gold_answer=gold_answer, candidate_answer=candidate_answer
    )


def parse_conditional_response(raw: str) -> CompletenessResult:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        missing = parsed.get("missing")
        if missing is not None:
            missing = str(missing)
        return CompletenessResult(preserved=bool(parsed.get("preserved", False)),
                                  missing=missing)
    except Exception:
        # Unparseable → never count as a pass.
        return CompletenessResult(preserved=False, missing=None)


_judge_llm = None


def _get_judge():
    global _judge_llm
    if _judge_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _judge_llm = ChatGoogleGenerativeAI(
            model=JUDGE_MODEL,
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0,
        )
    return _judge_llm


def judge_conditional(gold_answer: str, candidate_answer: str, llm=None,
                      max_attempts: int = 3, sleep=time.sleep) -> CompletenessResult:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=build_conditional_prompt(gold_answer, candidate_answer)),
    ]
    judge = llm if llm is not None else _get_judge()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = judge.invoke(messages)
            return parse_conditional_response(resp.content)
        except Exception as err:  # noqa: BLE001 — re-raised below if not retryable
            if attempt >= max_attempts or not _is_transient(err):
                raise
            sleep(2 ** (attempt - 1))

# evals/diagnostic/containment_judge.py
"""Containment judge: does the gold fact appear in the retrieved chunks?

Uses Gemini 2.5-flash — a DIFFERENT model from the DeepInfra/Groq 70B
generator, so the generator never grades its own failure. The judge returns
only a quoted span (or null) + a partial flag. It is never asked to author
the answer.
"""
import os
import re
import json
import time
from dataclasses import dataclass
from typing import Optional

from evals.diagnostic.buckets import JudgeResult

# Gemini returns transient 503 UNAVAILABLE ("high demand") / 429 spikes that
# resolve on their own; a single one must not crash a whole gate run.
_TRANSIENT_RE = re.compile(r"\b(503|429|unavailable|overloaded|deadline)\b", re.I)


def _is_transient(err: Exception) -> bool:
    return bool(_TRANSIENT_RE.search(str(err)))

JUDGE_MODEL = os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash")

JUDGE_SYSTEM = (
    "You are a containment checker. You are given a GOLD FACT and a set of "
    "RETRIEVED PASSAGES. Decide whether the gold fact is supported by the "
    "passages. You must NOT answer the farmer's question or add knowledge. "
    "Return ONLY the exact verbatim span from the passages that supports the "
    "gold fact, or null if no passage supports it."
)

JUDGE_TEMPLATE = """GOLD FACT:
{gold_answer}

RETRIEVED PASSAGES:
{chunks}

Return ONLY a JSON object:
{{"quoted_span": "<exact verbatim span from a passage that supports the gold fact, or null>", "partial": <true if a passage is related but only partially supports the fact, else false>}}"""


def build_judge_prompt(gold_answer: str, chunks: list[dict]) -> str:
    joined = "\n---\n".join(c.get("snippet", "") for c in chunks)
    return JUDGE_TEMPLATE.format(gold_answer=gold_answer, chunks=joined)


def parse_judge_response(raw: str) -> JudgeResult:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        span = parsed.get("quoted_span")
        if span is not None:
            span = str(span)
        return JudgeResult(span=span, partial=bool(parsed.get("partial", False)))
    except Exception:
        # Unparseable → safe absent. Never invent a span.
        return JudgeResult(span=None, partial=False)


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


def judge_containment(gold_answer: str, chunks: list[dict], llm=None,
                      max_attempts: int = 3, sleep=time.sleep) -> JudgeResult:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=build_judge_prompt(gold_answer, chunks)),
    ]
    judge = llm if llm is not None else _get_judge()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = judge.invoke(messages)
            return parse_judge_response(resp.content)
        except Exception as err:  # noqa: BLE001 — re-raised below if not retryable
            if attempt >= max_attempts or not _is_transient(err):
                raise
            sleep(2 ** (attempt - 1))  # 1s, 2s backoff

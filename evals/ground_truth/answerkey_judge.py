"""OFFLINE answer-key correctness judge (eval-only).

Grades an advisory answer against a human-validated reference answer, crediting
any answer that conveys the correct agronomic content regardless of which corpus
chunk it came from. This is the multi-reference fix for the single-gold artifact.

NEVER imported by backend/rag.py or the request path.
"""
import os
import re
from pathlib import Path

_SCORE_RE = re.compile(r"SCORE:\s*([01](?:\.\d+)?)", re.IGNORECASE)


def build_judge_prompt(query: str, answer: str, reference_answer: str) -> str:
    return (
        "You are grading an agricultural advisory answer for correctness.\n"
        "Compare the CANDIDATE answer to the REFERENCE answer. Credit the "
        "candidate if it conveys the same correct, safe agronomic guidance for "
        "the question — regardless of wording, source, or extra detail. A "
        "different-but-correct answer is still correct. Penalize wrong rates, "
        "wrong products, unsafe advice, or failure to answer.\n\n"
        f"QUESTION: {query}\n\n"
        f"REFERENCE ANSWER: {reference_answer}\n\n"
        f"CANDIDATE ANSWER: {answer}\n\n"
        "Reply with one line of reasoning, then a final line exactly:\n"
        "SCORE: <1.0 = correct | 0.5 = partially correct | 0.0 = incorrect>"
    )


def _parse_judge_score(raw: str):
    m = _SCORE_RE.search(raw or "")
    return float(m.group(1)) if m else None


_judge = None


def _get_judge():
    """Independent Gemini 2.5-flash judge (distinct from the generation model)."""
    global _judge
    if _judge is None:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        _judge = ChatGoogleGenerativeAI(
            model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0,
        )
    return _judge


def judge_against_answer_key(query: str, answer: str, reference_answer: str):
    """Return (score in {0.0,0.5,1.0} or None, raw_rationale). Spends Gemini tokens."""
    prompt = build_judge_prompt(query, answer, reference_answer)
    raw = _get_judge().invoke(prompt).content
    return _parse_judge_score(raw), raw


def grade_with_answer_key(query, answer, answer_keys, judge=judge_against_answer_key):
    """Grade `answer` for `query` against a VALIDATED answer key.

    Returns the score, or None when there is no key for the query or the key is
    not human-validated (circularity guard — unvalidated keys never score).
    """
    key = answer_keys.get(query)
    if not key or not key.get("validated"):
        return None
    score, _ = judge(query, answer, key["reference_answer"])
    return score

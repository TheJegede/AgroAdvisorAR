"""Groundedness verification for the F2 citation guard (LLM-as-judge by default,
MiniLM NLI as offline fallback)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
from langchain_core.messages import HumanMessage

import config
from models.advisory import ClaimResult
from utils.llm import _providers

logger = logging.getLogger(__name__)

# Thresholds — env-overridable via config (GUARD_*_THRESHOLD) for eval calibration.
ESCALATION_THRESHOLD = config.GUARD_ESCALATION_THRESHOLD
SUPPRESSION_THRESHOLD = config.GUARD_SUPPRESSION_THRESHOLD
# A CONTRADICTED argmax from the small NLI model is only trusted when the
# contradiction probability clears this bar. score_answer hard-zeroes the WHOLE
# answer on any contradiction, so marginal/false contradictions on grounded
# paraphrases (e.g. a claim that restates the chunk) must not trigger it.
CONTRADICTION_MIN_PROB = 0.55
# A claim restating chunk content (high content-token overlap) cannot be a
# genuine contradiction. Above this lexical-support level, never honor a
# CONTRADICTED label — it is the NLI's systematic false positive on grounded
# paraphrase / technical claims.
LEXICAL_CONTRADICTION_GUARD = 0.6
# Preview length (chars) passed to the LLM judge per evidence chunk.
CHUNK_PREVIEW_LENGTH = 800

_NLI_LABELS = ["CONTRADICTED", "ENTAILED", "NEUTRAL"]

_AGENTS_PATH = str(Path(__file__).parent.parent / "data" / "county_agents.json")
_agents_cache: Optional[dict] = None

_nli_model = None


def _get_nli_model():
    global _nli_model
    if _nli_model is None:
        from sentence_transformers import CrossEncoder
        _nli_model = CrossEncoder("cross-encoder/nli-MiniLM2-L6-H768")
    return _nli_model


def _load_agents() -> dict:
    global _agents_cache
    if _agents_cache is None:
        try:
            _agents_cache = json.loads(Path(_AGENTS_PATH).read_text())
        except Exception as e:
            logger.warning("Failed to load county_agents.json: %s", e)
            _agents_cache = {}
    return _agents_cache


_DECOMPOSE_PROMPT = """Extract all distinct factual claims from the following agricultural advisory text.
Return a JSON array of strings. Each string is one atomic, standalone factual claim.
Maximum 8 claims. Only include claims that could be verified against a knowledge source.

Text:
{text}

Return ONLY a JSON array, e.g. ["Claim one.", "Claim two."]"""


async def _judge_invoke(llm, prompt: str, run_config: dict | None):
    """One guard LLM attempt, capped at GUARD_JUDGE_TIMEOUT_S so a hung provider
    falls through to the next instead of stalling the whole query."""
    return await asyncio.wait_for(
        llm.ainvoke([HumanMessage(content=prompt)], config=run_config),
        timeout=config.GUARD_JUDGE_TIMEOUT_S,
    )


def _judge_providers():
    """Guard judge chain pinned to the fast GUARD_JUDGE_PROVIDER, independent of
    the generation chain (LLM_PRIMARY)."""
    return _providers(config.GUARD_JUDGE_PROVIDER)


async def decompose_claims(answer: str, run_config: dict | None = None) -> list[str]:
    """Break answer prose into atomic factual claims (pinned judge chain,
    then sentence-split)."""
    prompt = _DECOMPOSE_PROMPT.format(text=answer[:2000])
    for llm in _judge_providers():
        if llm is None:
            continue
        try:
            response = await _judge_invoke(llm, prompt, run_config)
            raw = response.content.strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            claims = json.loads(raw)
            if isinstance(claims, list):
                return [str(c) for c in claims[:8] if c]
        except Exception as e:
            logger.warning("Claim decomposition provider failed, trying next: %s", str(e)[:150])
    # Fallback: sentence split
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 10]
    return sentences[:8]


# Lightweight English/Spanish stopwords — dropped from lexical-overlap so the
# signal focuses on content words, numbers, units, product/chemical names.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "is", "are", "be", "by", "as", "it", "this", "that", "your", "you", "should",
    "can", "may", "will", "if", "from", "per", "el", "la", "los", "las", "de",
    "y", "o", "en", "un", "una", "es", "con", "para", "su", "que", "se", "del",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/][0-9]+)?")


def _content_tokens(text: str) -> set[str]:
    toks = _TOKEN_RE.findall(text.lower())
    return {t for t in toks if t.isdigit() or (len(t) > 2 and t not in _STOPWORDS)}


def _lexical_support(claim: str, chunks: list[str]) -> float:
    """Fraction of the claim's content tokens (incl. numbers/units) found in the
    best-matching chunk. Credits paraphrase and specific rates/products that NLI
    entailment misses because they are not stated verbatim. Range [0, 1]."""
    claim_tokens = _content_tokens(claim)
    if not claim_tokens:
        return 0.0
    best_overlap = 0.0
    for chunk in chunks:
        chunk_tokens = _content_tokens(chunk)
        if chunk_tokens:
            best_overlap = max(best_overlap, len(claim_tokens & chunk_tokens) / len(claim_tokens))
    return best_overlap


_JUDGE_PROMPT = """You are auditing an agricultural advisory for groundedness.
Given the EVIDENCE passages and a list of CLAIMS, label each claim:
- ENTAILED: the evidence supports the claim (paraphrase and equivalent numbers count).
- NEUTRAL: the evidence neither supports nor contradicts it.
- CONTRADICTED: the evidence states the opposite (e.g. a different rate/product, a negation).
Return ONLY a JSON array, one object per claim, same order:
[{{"claim": "...", "label": "ENTAILED|NEUTRAL|CONTRADICTED", "score": 0.0-1.0}}]
score = your confidence the claim is supported (1.0 fully supported, 0.0 unsupported/contradicted).

EVIDENCE:
{evidence}

CLAIMS:
{claims}
"""


_MERGED_JUDGE_PROMPT = """You are auditing an agricultural advisory for groundedness.
From the ANSWER, extract up to 8 atomic factual claims (one fact each). Then label
each claim against the EVIDENCE passages:
- ENTAILED: the evidence supports the claim (paraphrase and equivalent numbers count).
- NEUTRAL: the evidence neither supports nor contradicts it.
- CONTRADICTED: the evidence states the opposite (e.g. a different rate/product, a negation).
Return ONLY a JSON array, one object per claim:
[{{"claim": "...", "label": "ENTAILED|NEUTRAL|CONTRADICTED", "score": 0.0-1.0}}]
score = your confidence the claim is supported (1.0 fully supported, 0.0 unsupported/contradicted).

EVIDENCE:
{evidence}

ANSWER:
{answer}
"""


def _postprocess_judge_array(raw: str, claims: list[str], chunks: list[str]) -> list[ClaimResult] | None:
    """Parse a judge LLM's JSON array of {claim,label,score} into ClaimResults,
    applying the lexical backstop and false-contradiction demotion. Returns None
    if the response can't be coerced into one object per claim (caller falls back).
    """
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(raw)
    # Normalize common deviations: a wrapped object, or a dict keyed by claim text.
    if isinstance(parsed, dict):
        for _key in ("claims", "results", "data"):
            if isinstance(parsed.get(_key), list):
                parsed = parsed[_key]
                break
        else:
            if parsed and all(isinstance(v, dict) for v in parsed.values()):
                parsed = [parsed.get(c, {}) for c in claims]
    if not isinstance(parsed, list):
        raise ValueError("judge response is not a list")
    out: list[ClaimResult] = []
    for claim, obj in zip(claims, parsed):
        if not isinstance(obj, dict):
            obj = {}
        label = obj.get("label", "NEUTRAL")
        if label not in _NLI_LABELS:
            label = "NEUTRAL"
        llm_score = float(obj.get("score", 0.0))
        if llm_score > 1.0:
            llm_score = llm_score / 100.0
        llm_score = min(1.0, max(0.0, llm_score))
        lexical = _lexical_support(claim, chunks[:3])
        score = max(llm_score, lexical)
        if label == "CONTRADICTED" and lexical >= LEXICAL_CONTRADICTION_GUARD:
            label = "NEUTRAL"
        out.append(ClaimResult(claim=claim, label=label, score=score))
    if len(out) != len(claims):
        return None
    return out


async def judge_claims_llm(claims: list[str], chunks: list[str], run_config: dict | None = None) -> list[ClaimResult]:
    """Score claims for groundedness with an LLM judge (provider chain), with a
    lexical backstop so specific grounded numbers/products are never under-scored."""
    if not claims:
        return []
    if not chunks:
        return [ClaimResult(claim=c, label="NEUTRAL", score=0.0) for c in claims]
    evidence = "\n---\n".join(chunk[:CHUNK_PREVIEW_LENGTH] for chunk in chunks[:3])
    claims_block = "\n".join(f"{i+1}. {c}" for i, c in enumerate(claims))
    prompt = _JUDGE_PROMPT.format(evidence=evidence, claims=claims_block)
    for llm in _judge_providers():
        if llm is None:
            continue
        try:
            resp = await _judge_invoke(llm, prompt, run_config)
            out = _postprocess_judge_array(resp.content, claims, chunks)
            if out is not None:
                return out
        except Exception as e:
            logger.warning("LLM groundedness judge failed, trying next: %s", str(e)[:150])
    # Fallback: legacy NLI per-claim (sync CrossEncoder → run off the event loop).
    return await asyncio.to_thread(lambda: [verify_claim(c, chunks) for c in claims])


async def judge_answer_llm(
    answer: str,
    chunks: list[str],
    run_config: dict | None = None,
    meta: dict | None = None,
) -> list[ClaimResult]:
    """One-call guard: extract atomic claims from `answer` AND label each for
    groundedness vs `chunks`, returning ClaimResults. Same model/post-processing
    as the two-step path, one fewer round-trip. Raises if every provider fails
    (caller in verify_answer falls back to decompose+judge). `meta`, when given,
    is filled with {judge_provider, judge_attempts} for latency tracing."""
    if not chunks:
        return []
    evidence = "\n---\n".join(chunk[:CHUNK_PREVIEW_LENGTH] for chunk in chunks[:3])
    prompt = _MERGED_JUDGE_PROMPT.format(evidence=evidence, answer=answer[:2000])
    last_err: Exception | None = None
    attempts = 0
    for llm in _judge_providers():
        if llm is None:
            continue
        attempts += 1
        try:
            resp = await _judge_invoke(llm, prompt, run_config)
            # Re-derive the claim list from the response so post-processing aligns
            # one object per claim (the LLM both produced and labeled them).
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for _key in ("claims", "results", "data"):
                    if isinstance(parsed.get(_key), list):
                        parsed = parsed[_key]
                        break
            if not isinstance(parsed, list):
                raise ValueError("merged judge response is not a list")
            claims = [str(obj.get("claim", "")) for obj in parsed if isinstance(obj, dict)][:8]
            out = [] if not claims else _postprocess_judge_array(json.dumps(parsed[:8]), claims, chunks)
            if out is None:
                raise ValueError("merged judge post-processing produced misaligned results")
            if meta is not None:
                meta["judge_provider"] = type(llm).__name__
                meta["judge_attempts"] = attempts
            return out
        except Exception as e:
            last_err = e
            logger.warning("Merged guard judge provider failed, trying next: %s", str(e)[:150])
    raise last_err or RuntimeError("merged guard judge: no providers available")


def verify_claim(claim: str, chunks: list[str]) -> ClaimResult:
    """Score a single claim's groundedness against retrieved chunks.

    Blends NLI entailment probability (semantic support) with lexical token-recall
    (paraphrase / specific numbers & product names that hard NLI misses):
    score = max(entailment_prob, lexical_support). The CONTRADICTED label is demoted
    when either the NLI confidence is marginal (below CONTRADICTION_MIN_PROB) OR the
    claim shares high content-token overlap with a chunk (above LEXICAL_CONTRADICTION_GUARD)
    — both patterns are systematic NLI false positives on grounded technical claims.

    CrossEncoder nli-MiniLM2-L6-H768 label order: [contradiction, entailment, neutral]
    """
    if not chunks:
        # No retrieved evidence → UNGROUNDED, not "neutral". Drives suppression.
        return ClaimResult(claim=claim, label="NEUTRAL", score=0.0)

    model = _get_nli_model()
    pairs = [(claim, chunk) for chunk in chunks[:3]]
    # scores shape: (n_pairs, 3) — apply_softmax=True ensures scores are valid probabilities in [0, 1]
    scores = np.array(model.predict(pairs, apply_softmax=True))
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)

    # Pick the chunk with highest entailment logit (index 1)
    entailment_logits = scores[:, 1]
    best_chunk_idx = int(entailment_logits.argmax())
    best_scores = scores[best_chunk_idx]

    label_idx = int(best_scores.argmax())
    label = _NLI_LABELS[label_idx]

    contradiction_prob = float(best_scores[0])
    entailment_prob = float(best_scores[1])
    neutral_prob = float(best_scores[2])
    lexical = _lexical_support(claim, chunks[:3])
    # Defect-A guard: don't trust an unconfident contradiction, AND never trust a
    # contradiction against a chunk the claim is clearly restating (high lexical
    # overlap). Demote to the better of entailment/neutral.
    if label == "CONTRADICTED" and (
        contradiction_prob < CONTRADICTION_MIN_PROB
        or lexical >= LEXICAL_CONTRADICTION_GUARD
    ):
        label = "ENTAILED" if entailment_prob >= neutral_prob else "NEUTRAL"

    # Either semantic entailment OR lexical grounding counts as support.
    score = max(entailment_prob, lexical)

    return ClaimResult(claim=claim, label=label, score=score)


# A CONTRADICTED claim that names a rate/unit/number is safety-critical: shipping
# a wrong chemical or fertilizer rate can harm a crop or flock, so it still forces
# full suppression rather than being surgically dropped. (Product-name detection
# is deferred — numeric rates/units are the concrete, testable safety signal.)
#
# Calibration: Consume crop growth stages (like V3, R5, V3.5, R-1, R 5) on the left
# of the alternation (WITHOUT Group 1 capture) so they never trip suppression.
# Group 1 captures a true rate ONLY when a number is adjacent to a unit/rate token
# (e.g. "5 lb/ac", "32 oz", "1 qt/ac", "5%"). A bare digit ("10000 years",
# "3 causes") must NOT match — that over-match wiped grounded answers (F2).
_SAFETY_CRITICAL_RE = re.compile(
    r"\b[VRvr]\s?-?\d+(?:\.\d+)?\b"
    r"|(\d+(?:\.\d+)?\s*(?:lbs|lb|oz|qts|qt|gal|gpa|pts|pt|fl\s*oz|%)\b"
    r"|\d+(?:\.\d+)?\s*/\s*ac\b)",
    re.IGNORECASE,
)


def _is_safety_critical_contradiction(result: ClaimResult) -> bool:
    if result.label != "CONTRADICTED":
        return False
    # Check if there is a match that captures Group 1 (which contains the true rate/numbers)
    for m in _SAFETY_CRITICAL_RE.finditer(result.claim):
        if m.group(1) is not None:
            return True
    return False


def score_answer(results: list[ClaimResult]) -> float:
    """Groundedness = mean support of NON-contradicted claims. A contradicted
    claim is dropped (surgically removed from the advisory upstream), not used to
    zero an otherwise grounded answer — UNLESS it is safety-critical (names a
    rate/unit/number), in which case the whole answer is suppressed because a
    wrong rate must never ship. Empty list → 1.0. All claims contradicted → 0.0."""
    if not results:
        return 1.0
    if any(_is_safety_critical_contradiction(r) for r in results):
        return 0.0
    kept = [r for r in results if r.label != "CONTRADICTED"]
    if not kept:
        return 0.0
    return float(sum(r.score for r in kept) / len(kept))


# Statewide fallback when a county is absent from county_agents.json. A
# suppressed (blanked) advisory must never leave the farmer with no next step.
GENERIC_ESCALATION = (
    "Contact your local county Extension office or the University of Arkansas "
    "System Division of Agriculture (Cooperative Extension Service) at "
    "1-800-482-8038 for help with this question."
)


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


async def verify_answer(answer: str, chunks: list[dict], run_config: dict | None = None) -> dict:
    """Orchestrate groundedness scoring. Prefers the one-call merged judge
    (GUARD_MERGED_JUDGE); falls back to decompose -> judge (or NLI) on any
    failure. Returns {confidence_score, claim_verification, escalation: None}."""
    chunk_texts = [c.get("snippet", "") for c in chunks if c.get("snippet")]

    judge_meta: dict = {}
    judge_start = time.perf_counter()

    def _guard_timings() -> dict:
        t = {
            "judge_s": round(time.perf_counter() - judge_start, 3),
            "judge_provider": judge_meta.get("judge_provider"),
            "judge_attempts": judge_meta.get("judge_attempts", 0),
        }
        logger.info(
            "guard timing: judge_s=%.3f provider=%s attempts=%s",
            t["judge_s"], t["judge_provider"], t["judge_attempts"],
        )
        return t

    results = None
    if config.GUARD_MERGED_JUDGE:
        try:
            results = await judge_answer_llm(answer, chunk_texts, run_config, meta=judge_meta)
        except Exception as e:
            logger.warning("Merged guard failed, falling back to two-step: %s", str(e)[:150])
            results = None

    # results is None only when the merged judge errored (or was disabled). An
    # empty list is a valid "no claims to verify" result — treating it as a miss
    # would re-pay the two-step LLM round-trip the merge exists to avoid.
    if results is None:
        claims_text = await decompose_claims(answer, run_config)
        if not claims_text:
            return {"confidence_score": 1.0, "claim_verification": [], "escalation": None,
                    "guard_timings": _guard_timings()}
        if config.GROUNDEDNESS_JUDGE == "llm":
            results = await judge_claims_llm(claims_text, chunk_texts, run_config)
        else:
            results = await asyncio.to_thread(
                lambda: [verify_claim(c, chunk_texts) for c in claims_text]
            )

    if not results:
        return {"confidence_score": 1.0, "claim_verification": [], "escalation": None,
                "guard_timings": _guard_timings()}

    confidence_score = score_answer(results)
    return {
        "confidence_score": confidence_score,
        "claim_verification": results,
        "escalation": None,
        "guard_timings": _guard_timings(),
    }

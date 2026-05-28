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
    # scores shape: (n_pairs, 3) — raw logits, label order: [contradiction, entailment, neutral]
    scores = np.array(model.predict(pairs))
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)

    # Pick the chunk with highest entailment logit (index 1)
    entailment_logits = scores[:, 1]
    best_chunk_idx = int(entailment_logits.argmax())
    best_scores = scores[best_chunk_idx]

    label_idx = int(best_scores.argmax())
    _LABELS = ["CONTRADICTED", "ENTAILED", "NEUTRAL"]
    label = _LABELS[label_idx]

    # Use entailment probability directly (CrossEncoder returns softmax probabilities)
    score = float(best_scores[1])

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
        {confidence_score: float, claim_verification: list[ClaimResult], escalation: None}
        Caller stamps escalation after checking fips.
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
        "escalation": None,
    }

from typing import Literal
from pydantic import BaseModel, Field


class Cause(BaseModel):
    cause: str
    explanation: str


class Product(BaseModel):
    product: str
    rate: str
    application_method: str
    pre_harvest_interval: str | None = None


class Citation(BaseModel):
    document_title: str
    section: str | None = None
    url: str | None = None


class ContextMeta(BaseModel):
    soil_data_available: bool
    weather_data_available: bool
    county_fips: str


class ClaimResult(BaseModel):
    claim: str
    label: Literal['ENTAILED', 'NEUTRAL', 'CONTRADICTED']
    score: float = Field(ge=0, le=1)


class AdvisoryDraft(BaseModel):
    """LLM-authored advisory — the schema passed to with_structured_output.

    Deliberately EXCLUDES the F2 guard fields (confidence_score,
    claim_verification, escalation). Those are computed by the post-hoc NLI
    citation guard in rag._postprocess_async, not the LLM. Exposing them to
    structured output made the model hallucinate claim verifications (wasting
    tokens) and crash generation on enum-label typos (e.g. "ENTAILLED") or wrong
    types ("expected null, but got array"), dropping whole advisories.
    """
    # B1 reasoning-first scratchpad — declared FIRST so it generates before the
    # answer fields (field declaration order = JSON schema property order =
    # generation order). Optional plain string (no nested structure — see the
    # schema-fragility note above). Stripped in rag._postprocess_async before
    # the guard scores prose and before storage/display.
    analysis: str | None = None
    response_type: Literal["diagnostic", "informational"] = "diagnostic"
    problem_summary: str
    detailed_explanation: str | None = None
    key_points: list[str] = []
    likely_causes: list[Cause] = []
    recommended_actions: list[str] = []
    products_rates: list[Product] = []
    warnings: list[str] = []
    citations: list[Citation] = []
    confidence: Literal["High", "Medium", "Low"]
    confidence_explanation: str
    language: Literal["en", "es"]
    context_meta: ContextMeta


class AdvisoryResponse(AdvisoryDraft):
    # F2 guard-computed fields — filled by the citation guard, NOT the LLM.
    # Optional for backwards compat with stored messages.
    confidence_score: float | None = None
    claim_verification: list[ClaimResult] | None = None
    escalation: str | None = None
    suppressed: bool = False  # True when the guard blanked the body (score < SUPPRESSION)

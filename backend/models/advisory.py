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


class AdvisoryDraft(BaseModel):
    """LLM-authored advisory — the schema passed to with_structured_output.

    Deliberately EXCLUDES the F2 guard fields (confidence_score,
    claim_verification, escalation). Those are computed by the post-hoc NLI
    citation guard in rag._postprocess_async, not the LLM. Exposing them to
    structured output made the model hallucinate claim verifications (wasting
    tokens) and crash generation on enum-label typos (e.g. "ENTAILLED") or wrong
    types ("expected null, but got array"), dropping whole advisories.
    """
    response_type: Literal["diagnostic", "informational"] = "diagnostic"
    problem_summary: str
    detailed_explanation: Optional[str] = None
    key_points: List[str] = []
    likely_causes: List[Cause] = []
    recommended_actions: List[str]
    products_rates: List[Product] = []
    warnings: List[str]
    citations: List[Citation]
    confidence: Literal["High", "Medium", "Low"]
    confidence_explanation: str
    language: Literal["en", "es"]
    context_meta: ContextMeta


class AdvisoryResponse(AdvisoryDraft):
    # F2 guard-computed fields — filled by the citation guard, NOT the LLM.
    # Optional for backwards compat with stored messages.
    confidence_score: Optional[float] = None
    claim_verification: Optional[List[ClaimResult]] = None
    escalation: Optional[str] = None
    suppressed: bool = False  # True when the guard blanked the body (score < SUPPRESSION)

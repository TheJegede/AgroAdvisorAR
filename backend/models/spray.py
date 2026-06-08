"""Pydantic schema for the dicamba spray-compliance check (F4 Phase 1).

Single source of truth for the /api/v1/dicamba/check request + per-gate
response. Each CheckResult carries a tier (verifiable_fact vs human_attested)
so the UI can show what the tool measured vs what the applicator must confirm.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

GateId = Literal["A", "B", "C", "D"]
GateStatus = Literal["pass", "fail", "needs_confirmation"]
CheckTier = Literal["verifiable_fact", "human_attested"]
CheckStatus = Literal["pass", "fail", "needs_confirmation"]


class ApplicatorAttestation(BaseModel):
    no_inversion_observed: Optional[bool] = None     # Gate C confirmation
    boom_height_ok: Optional[bool] = None            # Gate D (reserved)
    droplet_setup_ok: Optional[bool] = None          # Gate D (reserved)
    sensitive_crops_checked: Optional[bool] = None   # Gate B — ¼ mi non-tolerant crops
    organic_specialty_checked: Optional[bool] = None # Gate B — ½ mi organic/specialty
    tank_clean_ok: Optional[bool] = None             # Gate D (reserved)


class ResearchStation(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class SprayCheckRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    product: str
    at: datetime
    attestation: ApplicatorAttestation = ApplicatorAttestation()


class CheckResult(BaseModel):
    id: str
    label: str
    tier: CheckTier
    status: CheckStatus
    reason: str
    observed: Optional[str] = None
    expected: Optional[str] = None


class GateResult(BaseModel):
    gate: GateId
    title: str
    status: GateStatus
    checks: list[CheckResult]


class SprayCheckResponse(BaseModel):
    overall_status: GateStatus
    rule_version: str
    evaluated_at: datetime
    weather_available: bool
    gates: list[GateResult]

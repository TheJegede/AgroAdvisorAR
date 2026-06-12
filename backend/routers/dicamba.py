"""Dicamba spray-compliance check endpoint (F4 Phase 1: Gates A + C).

Stateless: given a field point, product, and datetime, return per-gate results.
No persistence yet (Phase 4) so there is no IDOR write surface; the request
carries no owner field and auth is enforced via get_current_user.
"""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from models.spray import (
    ResearchStation, SprayCheckRequest, SprayCheckResponse, SprayRecord,
)
from models.spray_feedback import SprayFeedbackRequest, SprayFeedbackResponse
from services.admin import require_admin
from services.auth import get_current_user
from services.pdf_generator import generate_spray_record_pdf
from services.spray_check import run_spray_check
from services.spray_record import create_record, get_record, list_records
from services.spray_feedback import insert_spray_feedback, verify_record_ownership
from services.spray_rules import RulesNotFoundError, resolve_rules
from services.spray_stats import aggregate_gate_stats
from services.spray_stations import load_stations
from services.user import get_profile
from services.weather_now import fetch_forecast_conditions

router = APIRouter(prefix="/dicamba", tags=["dicamba"])

# Arkansas is America/Chicago. The frontend sends `at` as a UTC ISO string
# (new Date().toISOString()), pydantic parses it tz-aware. Every downstream
# comparison is against Open-Meteo timestamps returned in America/Chicago local
# time and the rules season-window date, so we must convert to Central at the
# boundary — otherwise the UTC clock/date leaks into inversion, rain-window, and
# Gate A season verdicts (F1).
_CENTRAL = ZoneInfo("America/Chicago")


def _to_central(dt: datetime) -> datetime:
    """tz-aware datetime -> Arkansas local. A naive datetime is assumed local."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(_CENTRAL)


@router.post("/check", response_model=SprayCheckResponse)
async def check_spray(
    body: SprayCheckRequest,
    user: dict = Depends(get_current_user),
):
    body.at = _to_central(body.at)
    try:
        rules = resolve_rules(body.at.date())
    except RulesNotFoundError:
        raise HTTPException(
            status_code=422, detail="No dicamba rules effective for that date"
        )
    # Unapproved product is NOT a 422 — Gate A reports product_approved=fail so
    # the checklist surfaces the failure rather than hiding it.
    weather = await fetch_forecast_conditions(body.lat, body.lon, body.at)
    stations = load_stations()
    return run_spray_check(body, rules, weather, stations)


@router.get("/stations", response_model=list[ResearchStation])
async def list_stations(user: dict = Depends(get_current_user)):
    """Static research-station seed list so the Gate B map can plot markers.

    Single source with evaluate_gate_b (both read spray_stations.load_stations).
    Coordinates ship UNVERIFIED (see ar_research_stations.json `source`).
    """
    return load_stations()


def _build_record_payload(body: SprayCheckRequest, resp: SprayCheckResponse, weather: dict) -> dict:
    return {
        "lat": body.lat,
        "lon": body.lon,
        "product": body.product,
        "applied_at": body.at.isoformat(),
        "overall_status": resp.overall_status,
        "rule_version": resp.rule_version,
        "gates": [g.model_dump() for g in resp.gates],
        "attestation": body.attestation.model_dump(),
        "weather_json": weather if weather.get("available") else None,
    }


def _require_legal_attestations(body: SprayCheckRequest) -> None:
    if not (
        body.attestation.license_attested is True
        and body.attestation.training_attested is True
    ):
        raise HTTPException(
            status_code=422,
            detail="Applicator license and annual dicamba training attestations are required before saving a spray record.",
        )


@router.post("/record", response_model=SprayRecord, status_code=201)
async def create_spray_record(
    body: SprayCheckRequest,
    user: dict = Depends(get_current_user),
):
    _require_legal_attestations(body)
    body.at = _to_central(body.at)
    try:
        rules = resolve_rules(body.at.date())
    except RulesNotFoundError:
        raise HTTPException(status_code=422, detail="No dicamba rules effective for that date")
    weather = await fetch_forecast_conditions(body.lat, body.lon, body.at)
    stations = load_stations()
    resp = run_spray_check(body, rules, weather, stations)
    payload = _build_record_payload(body, resp, weather)
    return create_record(user["sub"], payload)


@router.get("/records", response_model=list[SprayRecord])
async def list_spray_records(user: dict = Depends(get_current_user)):
    return list_records(user["sub"])


@router.get("/record/{record_id}", response_model=SprayRecord)
async def get_spray_record(record_id: str, user: dict = Depends(get_current_user)):
    record = get_record(record_id, user["sub"])
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.get("/record/{record_id}/pdf")
async def download_spray_record_pdf(record_id: str, user: dict = Depends(get_current_user)):
    record = get_record(record_id, user["sub"])
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    profile = get_profile(user["sub"]) or {}
    pdf_bytes = generate_spray_record_pdf(record, profile)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=spray_record_{record_id[:8]}.pdf"},
    )


@router.get("/stats")
async def get_spray_stats(admin_user: dict = Depends(require_admin)):
    """Aggregate per-gate statistics across all spray records (admin-only)."""
    return aggregate_gate_stats()


@router.post("/feedback", response_model=SprayFeedbackResponse, status_code=201)
async def submit_spray_feedback(
    body: SprayFeedbackRequest,
    user: dict = Depends(get_current_user),
):
    """Submit rating + optional comment for a saved spray record.

    Validates ownership to prevent IDOR feedback injection.
    """
    if not verify_record_ownership(body.record_id, user["sub"]):
        raise HTTPException(status_code=404, detail="Record not found")

    feedback = insert_spray_feedback(
        record_id=body.record_id,
        farmer_id=user["sub"],
        rating=body.rating,
        comment=body.comment,
    )
    if hasattr(feedback.get("created_at"), "isoformat"):
        feedback["created_at"] = feedback["created_at"].isoformat()
    else:
        feedback["created_at"] = str(feedback.get("created_at") or "")

    return feedback

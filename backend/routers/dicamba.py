"""Dicamba spray-compliance check endpoint (F4 Phase 1: Gates A + C).

Stateless: given a field point, product, and datetime, return per-gate results.
No persistence yet (Phase 4) so there is no IDOR write surface; the request
carries no owner field and auth is enforced via get_current_user.
"""
from fastapi import APIRouter, Depends, HTTPException

from models.spray import SprayCheckRequest, SprayCheckResponse
from services.auth import get_current_user
from services.spray_check import run_spray_check
from services.spray_rules import RulesNotFoundError, resolve_rules
from services.weather_now import fetch_forecast_conditions

router = APIRouter(prefix="/dicamba", tags=["dicamba"])


@router.post("/check", response_model=SprayCheckResponse)
async def check_spray(
    body: SprayCheckRequest,
    user: dict = Depends(get_current_user),
):
    try:
        rules = resolve_rules(body.at.date())
    except RulesNotFoundError:
        raise HTTPException(
            status_code=422, detail="No dicamba rules effective for that date"
        )
    # Unapproved product is NOT a 422 — Gate A reports product_approved=fail so
    # the checklist surfaces the failure rather than hiding it.
    weather = await fetch_forecast_conditions(body.lat, body.lon, body.at)
    return run_spray_check(body, rules, weather)

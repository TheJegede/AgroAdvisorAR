# backend/routers/alerts.py
"""GET /alerts and PATCH /alerts/{id}/dismiss endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.auth import get_current_user
from services.user import _get_service_client, get_profile

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: str
    pest: str
    message: str
    gdd_value: float | None
    fired_at: str


@router.get("", response_model=list[AlertOut])
async def list_alerts(user: dict = Depends(get_current_user)) -> list[AlertOut]:
    farmer_id = user["sub"]
    client = _get_service_client()

    result = (
        client.table("alerts")
        .select("*")
        .eq("farmer_id", farmer_id)
        .is_("dismissed_at", "null")
        .order("fired_at", desc=True)
        .execute()
    )

    profile = get_profile(farmer_id) or {}
    lang = profile.get("language", "en")

    alerts = []
    for row in result.data or []:
        msg = row["message_es"] if lang == "es" else row["message_en"]
        alerts.append(
            AlertOut(
                id=row["id"],
                pest=row["pest"],
                message=msg or "",
                gdd_value=row.get("gdd_value"),
                fired_at=row["fired_at"],
            )
        )
    return alerts


@router.patch("/{alert_id}/dismiss", status_code=204)
async def dismiss_alert(
    alert_id: str, user: dict = Depends(get_current_user)
) -> None:
    farmer_id = user["sub"]
    client = _get_service_client()

    result = (
        client.table("alerts")
        .select("id, farmer_id")
        .eq("id", alert_id)
        .maybe_single()
        .execute()
    )
    if not result.data or result.data["farmer_id"] != farmer_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    client.table("alerts").update(
        {"dismissed_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", alert_id).execute()

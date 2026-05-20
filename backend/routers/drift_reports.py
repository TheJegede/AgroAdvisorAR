"""Drift report submission + PDF generation endpoints."""
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.auth import get_current_user
from services.drift_service import create_report, get_report, list_reports
from services.weather_history import fetch_historical_weather
from services.pdf_generator import generate_complaint_pdf
from services.user import get_profile
from utils.counties import get_county_info

router = APIRouter(prefix="/drift-reports", tags=["drift-reports"])


class DriftReportCreate(BaseModel):
    incident_date: date
    county_fips: str
    affected_crop: Optional[str] = None
    affected_acres: Optional[float] = None
    suspected_herbicide: str = "dicamba"
    symptoms_description: Optional[str] = None
    neighboring_applicator: Optional[str] = None
    photos_attached: bool = False
    aspb_submitted: bool = False


@router.post("", status_code=201)
async def create_drift_report(
    body: DriftReportCreate,
    user: dict = Depends(get_current_user),
):
    county = get_county_info(body.county_fips)
    weather = {"available": False}
    if county:
        weather = await fetch_historical_weather(
            county["lat"], county["lon"], str(body.incident_date)
        )
    report = create_report(user["sub"], body.model_dump(), weather)
    return report


@router.get("")
def list_drift_reports(user: dict = Depends(get_current_user)):
    return list_reports(user["sub"])


@router.get("/{report_id}")
def get_drift_report(report_id: str, user: dict = Depends(get_current_user)):
    report = get_report(report_id, user["sub"])
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/pdf")
def download_drift_report_pdf(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    report = get_report(report_id, user["sub"])
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    profile = get_profile(user["sub"]) or {}
    pdf_bytes = generate_complaint_pdf(report, profile)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=drift_report_{report_id[:8]}.pdf"
            )
        },
    )

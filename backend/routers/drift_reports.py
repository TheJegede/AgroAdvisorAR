"""Drift report submission + PDF generation endpoints."""
from fastapi import APIRouter, Depends
from services.auth import get_current_user

router = APIRouter(prefix="/drift-reports", tags=["drift-reports"])


@router.get("")
async def list_drift_reports(user: dict = Depends(get_current_user)):
    return []

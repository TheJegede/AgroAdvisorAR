"""Farmer profile endpoints — all routes require JWT auth."""
from fastapi import APIRouter, Depends, HTTPException
from models.user import FarmerProfile, UpdateProfileRequest
from services.auth import get_current_user
from services.user import get_profile, update_profile
import config

router = APIRouter(prefix="/profile", tags=["profile"])


def _with_admin_flag(profile: dict, user_id: str) -> dict:
    return {**profile, "is_admin": user_id in config.ADMIN_USER_IDS}


@router.get("", response_model=FarmerProfile)
async def read_profile(user: dict = Depends(get_current_user)):
    profile = get_profile(user["sub"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _with_admin_flag(profile, user["sub"])


@router.patch("", response_model=FarmerProfile)
async def patch_profile(
    body: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    profile = update_profile(user["sub"], updates)
    return _with_admin_flag(profile, user["sub"])

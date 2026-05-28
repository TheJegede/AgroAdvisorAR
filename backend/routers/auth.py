"""Auth endpoints — proxies to Supabase GoTrue for token issuance."""
import hashlib
import logging

from fastapi import APIRouter, HTTPException, status
from supabase import create_client, Client
from models.user import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from services.cache import rate_limit_hit
from services.user import create_profile
import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_anon_client: Client | None = None


def _get_anon_client() -> Client:
    global _anon_client
    if _anon_client is None:
        _anon_client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    return _anon_client


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    client = _get_anon_client()
    try:
        auth_resp = client.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Registration failed. Check your email and password and try again.")

    if auth_resp.user is None:
        raise HTTPException(status_code=400, detail="Registration failed. This email may already be registered.")

    user_id = str(auth_resp.user.id)
    create_profile(
        user_id=user_id,
        full_name=body.full_name,
        county_fips=body.county_fips,
        primary_crops=body.primary_crops,
        language=body.language,
        rice_fields=[f.model_dump() for f in body.rice_fields],
    )

    if auth_resp.session is None:
        # Email confirmation required — profile created, tokens not yet issued
        raise HTTPException(
            status_code=400,
            detail="Email confirmation required. Check your inbox and confirm before logging in.",
        )

    return TokenResponse(
        access_token=auth_resp.session.access_token,
        refresh_token=auth_resp.session.refresh_token,
    )


@router.post("/forgot", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest):
    """Send a password-reset email via Supabase. Always returns 200 to prevent email enumeration."""
    client = _get_anon_client()
    try:
        client.auth.reset_password_email(
            body.email,
            {"redirect_to": f"{config.FRONTEND_URL}/reset-password"},
        )
    except Exception as e:
        logger.warning("reset_password_email failed for %s: %s", body.email, e)
    return {"detail": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest):
    """Apply a new password using the recovery tokens from the magic link."""
    client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    try:
        client.auth.set_session(body.access_token, body.refresh_token)
        client.auth.update_user({"password": body.new_password})
    except Exception as e:
        logger.warning("reset_password failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Reset link is invalid or expired. Request a new one.",
        )
    return {"detail": "Password updated. You can now log in."}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    email_key = hashlib.sha256(body.email.lower().encode()).hexdigest()[:24]
    allowed, _ = rate_limit_hit(f"login_throttle:{email_key}", 10, 900)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in 15 minutes.",
            headers={"Retry-After": "900"},
        )

    client = _get_anon_client()
    try:
        auth_resp = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if auth_resp.session is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=auth_resp.session.access_token,
        refresh_token=auth_resp.session.refresh_token,
    )

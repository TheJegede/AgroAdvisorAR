"""Auth endpoints — proxies to Supabase GoTrue for token issuance."""
from fastapi import APIRouter, HTTPException, status
from supabase import create_client, Client
from models.user import LoginRequest, RegisterRequest, TokenResponse
from services.user import create_profile
import config

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


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
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

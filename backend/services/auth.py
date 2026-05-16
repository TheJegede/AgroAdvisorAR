"""JWT validation and FastAPI auth dependency."""
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import config

_bearer = HTTPBearer()

# Cached JWKS keys: kid → JWK dict
_jwks_cache: dict[str, dict] | None = None


def _fetch_jwks() -> dict[str, dict]:
    jwks_url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    return {k["kid"]: k for k in keys}


def _get_jwks(force_refresh: bool = False) -> dict[str, dict]:
    global _jwks_cache
    if _jwks_cache is None or force_refresh:
        _jwks_cache = _fetch_jwks()
    return _jwks_cache


def decode_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "ES256")
        kid = header.get("kid")

        if alg in ("ES256", "RS256"):
            jwks = _get_jwks()
            key = jwks.get(kid) if kid else next(iter(jwks.values()), None)
            if key is None:
                # Key not in cache — Supabase may have rotated; retry once
                jwks = _get_jwks(force_refresh=True)
                key = jwks.get(kid) if kid else next(iter(jwks.values()), None)
            if key is None:
                raise JWTError("No matching JWKS key found after refresh")
        else:
            # Legacy HS256 path (old Supabase eyJ keys)
            key = config.SUPABASE_JWT_SECRET

        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """FastAPI dependency — validates JWT, returns decoded payload. Access user_id via user['sub']."""
    return decode_token(credentials.credentials)

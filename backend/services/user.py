"""Farmer profile CRUD against Supabase using the service-role client."""
from supabase import create_client, Client
from utils.counties import AR_COUNTIES
from utils.db import _assert_insert
import config

_service_client: Client | None = None


def _get_service_client() -> Client:
    """Service-role client bypasses RLS — use only for server-side operations."""
    global _service_client
    if _service_client is None:
        _service_client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _service_client


def create_profile(
    user_id: str,
    full_name: str,
    county_fips: str,
    primary_crops: list[str],
    language: str,
    rice_fields: list[dict] | None = None,
) -> dict:
    county_name = AR_COUNTIES[county_fips][0]
    client = _get_service_client()
    result = client.table("farmer_profiles").insert({
        "id": user_id,
        "full_name": full_name,
        "county_fips": county_fips,
        "county_name": county_name,
        "primary_crops": primary_crops,
        "language": language,
        "rice_fields": rice_fields or [],
    }).execute()
    _assert_insert(result, f"profile (user {user_id})")
    return result.data[0]


def get_profile(user_id: str) -> dict | None:
    client = _get_service_client()
    result = client.table("farmer_profiles").select("*").eq("id", user_id).maybe_single().execute()
    return result.data


def update_profile(user_id: str, updates: dict) -> dict:
    """updates dict contains only non-None fields from UpdateProfileRequest."""
    if "county_fips" in updates and updates["county_fips"]:
        updates["county_name"] = AR_COUNTIES[updates["county_fips"]][0]
    if "rice_fields" in updates and updates["rice_fields"] is not None:
        updates["rice_fields"] = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in updates["rice_fields"]
        ]
    client = _get_service_client()
    result = (
        client.table("farmer_profiles")
        .update(updates)
        .eq("id", user_id)
        .execute()
    )
    if result.data:
        return result.data[0]
    # No existing row (user created outside /register) — create with defaults
    default_fips = updates.get("county_fips") or config.DEFAULT_COUNTY_FIPS
    row = {
        "id": user_id,
        "full_name": updates.get("full_name", ""),
        "county_fips": default_fips,
        "county_name": AR_COUNTIES[default_fips][0],
        "primary_crops": updates.get("primary_crops", []),
        "language": updates.get("language", "en"),
        "rice_fields": updates.get("rice_fields", []),
    }
    result2 = client.table("farmer_profiles").insert(row).execute()
    _assert_insert(result2, f"profile (user {user_id})")
    return result2.data[0]

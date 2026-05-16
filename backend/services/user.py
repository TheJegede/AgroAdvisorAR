"""Farmer profile CRUD against Supabase using the service-role client."""
from supabase import create_client, Client
from utils.counties import AR_COUNTIES
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
    }).execute()
    if not result.data:
        raise RuntimeError(f"Profile insert returned no data for user {user_id}")
    return result.data[0]


def get_profile(user_id: str) -> dict | None:
    client = _get_service_client()
    result = client.table("farmer_profiles").select("*").eq("id", user_id).maybe_single().execute()
    return result.data


def update_profile(user_id: str, updates: dict) -> dict:
    """updates dict contains only non-None fields from UpdateProfileRequest."""
    if "county_fips" in updates:
        updates["county_name"] = AR_COUNTIES[updates["county_fips"]][0]
    client = _get_service_client()
    result = (
        client.table("farmer_profiles")
        .update(updates)
        .eq("id", user_id)
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Profile update returned no data for user {user_id}")
    return result.data[0]

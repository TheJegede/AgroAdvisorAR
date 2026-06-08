"""CRUD for the immutable spray_records table (F4 Phase 4).

Append-only: only create/read/list. Uses the service-role client (bypasses RLS),
so farmer_id is stamped from the authenticated arg — never client-supplied — and
reads filter by farmer_id manually (mirrors services/session.py, anti-IDOR)."""
from services.user import _get_service_client
from utils.db import _assert_insert

_PERSISTED = (
    "lat", "lon", "product", "applied_at", "overall_status",
    "rule_version", "gates", "attestation", "weather_json",
)


def create_record(farmer_id: str, payload: dict) -> dict:
    row = {k: payload.get(k) for k in _PERSISTED}
    row["farmer_id"] = farmer_id  # from JWT, never the payload
    result = _get_service_client().table("spray_records").insert(row).execute()
    _assert_insert(result, f"spray_record (farmer {farmer_id})")
    return result.data[0]


def get_record(record_id: str, farmer_id: str) -> dict | None:
    result = (
        _get_service_client()
        .table("spray_records")
        .select("*")
        .eq("id", record_id)
        .eq("farmer_id", farmer_id)
        .maybe_single()
        .execute()
    )
    return result.data


def list_records(farmer_id: str, limit: int = 50) -> list[dict]:
    result = (
        _get_service_client()
        .table("spray_records")
        .select("*")
        .eq("farmer_id", farmer_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []

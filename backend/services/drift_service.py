"""CRUD for drift_reports table. Uses service-role client (bypasses RLS)."""
from services.user import _get_service_client


def create_report(farmer_id: str, data: dict, weather: dict) -> dict:
    row = {
        "farmer_id": farmer_id,
        "incident_date": str(data["incident_date"]),
        "county_fips": data["county_fips"],
        "affected_crop": data.get("affected_crop"),
        "affected_acres": data.get("affected_acres"),
        "suspected_herbicide": data.get("suspected_herbicide", "dicamba"),
        "symptoms_description": data.get("symptoms_description"),
        "neighboring_applicator": data.get("neighboring_applicator"),
        "photos_attached": data.get("photos_attached", False),
        "aspb_submitted": data.get("aspb_submitted", False),
        "weather_json": weather if weather.get("available") else None,
        "wind_speed_mph": None,
        "wind_direction": None,
        "temp_at_time_f": None,
    }
    if weather.get("available"):
        s = weather.get("hourly_summary", {})
        row["wind_speed_mph"] = s.get("wind_speed_mph_avg")
        row["wind_direction"] = s.get("wind_direction_label")
        row["temp_at_time_f"] = s.get("temp_f_at_noon")

    result = _get_service_client().table("drift_reports").insert(row).execute()
    if not result.data:
        raise RuntimeError(f"drift_reports insert returned no data for farmer {farmer_id}")
    return result.data[0]


def get_report(report_id: str, farmer_id: str) -> dict | None:
    result = (
        _get_service_client()
        .table("drift_reports")
        .select("*")
        .eq("id", report_id)
        .eq("farmer_id", farmer_id)
        .maybe_single()
        .execute()
    )
    return result.data


def list_reports(farmer_id: str) -> list[dict]:
    result = (
        _get_service_client()
        .table("drift_reports")
        .select("*")
        .eq("farmer_id", farmer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def list_all_reports(
    county_fips: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    q = _get_service_client().table("drift_reports").select("*")
    if county_fips:
        q = q.eq("county_fips", county_fips)
    if date_from:
        q = q.gte("incident_date", date_from)
    if date_to:
        q = q.lte("incident_date", date_to)
    return q.order("created_at", desc=True).execute().data or []

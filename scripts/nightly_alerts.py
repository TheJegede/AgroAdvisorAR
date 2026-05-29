# scripts/nightly_alerts.py
"""Nightly alert orchestrator — run via GitHub Actions."""
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.alert_engine import AlertEngine
from services.awd_scheduler import compute_awd_stage
from services.context import fetch_ssurgo, fetch_usgs_well
from services.user import _get_service_client
from services.cache import _get_client as _get_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

AWD_DEDUP_TTL = 5 * 24 * 60 * 60  # 5 days
ACTIVE_FARMER_WINDOW_DAYS = 90


async def run_awd_alerts(farmers: list[dict], supabase) -> int:
    redis = _get_redis()
    fired = 0

    for farmer in farmers:
        if "rice" not in (farmer.get("primary_crops") or []):
            continue
        rice_fields = farmer.get("rice_fields") or []
        if not rice_fields:
            continue

        fips = farmer.get("county_fips") or ""
        if not fips:
            continue

        soil = await fetch_ssurgo(fips)
        drainage = (soil or {}).get("drainage_class") or "default"
        usgs = await fetch_usgs_well(fips)
        stress = (usgs or {}).get("stress_level", "normal")
        well_m = (usgs or {}).get("current_depth_m")

        for field in rice_fields:
            last_flood_str = field.get("last_flood_date")
            field_name = field.get("field_name") or ""
            if not last_flood_str or not field_name:
                continue

            try:
                last_flood = date.fromisoformat(last_flood_str)
            except ValueError:
                continue

            result = compute_awd_stage(
                field_name=field_name,
                last_flood_date=last_flood,
                drainage_class=drainage,
                current_well_m=well_m,
                aquifer_stress_level=stress,
            )
            if result.days_to_threshold > 2:
                continue

            slug = field_name.lower().replace(" ", "_")[:20]
            redis_key = f"alert:{farmer['id']}:awd_reflood:{slug}"
            if redis is not None:
                try:
                    if redis.exists(redis_key):
                        continue
                except Exception:
                    logger.warning("Redis exists check failed key=%s", redis_key)

            days = result.days_to_threshold
            row = {
                "farmer_id": farmer["id"],
                "pest": "awd_reflood",
                "county_fips": fips,
                "message_en": (
                    f"Rice field '{field_name}': AWD re-flood threshold in {days} day(s). "
                    "Re-flood soon. See UA Extension MP192."
                ),
                "message_es": (
                    f"Arrozal '{field_name}': umbral AWD en {days} dia(s). "
                    "Inunde pronto. Ver MP192."
                ),
            }
            try:
                supabase.table("alerts").insert(row).execute()
            except Exception:
                logger.exception(
                    "AWD alert insert failed farmer=%s field=%s", farmer["id"], field_name
                )
                continue

            if redis is not None:
                try:
                    redis.set(redis_key, "1", ex=AWD_DEDUP_TTL)
                except Exception:
                    logger.warning("Redis set failed key=%s", redis_key)

            fired += 1
            logger.info(
                "AWD alert fired farmer=%s field=%s days=%d", farmer["id"], field_name, days
            )

    return fired


async def main() -> None:
    supabase = _get_service_client()
    cutoff = (date.today() - timedelta(days=ACTIVE_FARMER_WINDOW_DAYS)).isoformat()

    result = (
        supabase.table("farmer_profiles")
        .select("id, county_fips, primary_crops, language, rice_fields")
        .gte("last_active", cutoff)
        .execute()
    )
    farmers = result.data or []
    logger.info("Processing %d active farmers (last_active > %s)", len(farmers), cutoff)

    engine = AlertEngine()
    total_gdd_fired = 0

    for farmer in farmers:
        county = farmer.get("county_fips") or ""
        crops = farmer.get("primary_crops") or []
        if not county or not crops:
            continue
        try:
            fired = await engine.run_for_farmer(
                farmer_id=farmer["id"],
                county_fips=county,
                primary_crops=crops,
                language=farmer.get("language", "en"),
                rice_fields=farmer.get("rice_fields") or [],
            )
            total_gdd_fired += len(fired)
        except Exception:
            logger.exception("GDD alert run failed for farmer=%s", farmer["id"])

    awd_fired = await run_awd_alerts(farmers, supabase)

    logger.info(
        "Nightly alerts complete. GDD alerts: %d, AWD alerts: %d",
        total_gdd_fired,
        awd_fired,
    )


if __name__ == "__main__":
    asyncio.run(main())

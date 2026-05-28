# scripts/nightly_alerts.py
"""Nightly alert orchestrator — run via GitHub Actions."""
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.alert_engine import AlertEngine
from services.user import _get_service_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    supabase = _get_service_client()
    cutoff = (date.today() - timedelta(days=30)).isoformat()

    result = (
        supabase.table("farmer_profiles")
        .select("id, county_fips, primary_crops, language")
        .gte("last_active", cutoff)
        .execute()
    )
    farmers = result.data or []
    logger.info("Processing %d active farmers (last_active > %s)", len(farmers), cutoff)

    engine = AlertEngine()
    total_fired = 0

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
            )
            total_fired += len(fired)
        except Exception:
            logger.exception("Alert run failed for farmer=%s", farmer["id"])

    logger.info("Nightly alerts complete. Total fired: %d", total_fired)


if __name__ == "__main__":
    asyncio.run(main())

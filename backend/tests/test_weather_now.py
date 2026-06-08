import asyncio
import importlib
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import weather_now  # noqa: E402


def _mock_httpx(payload: dict):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(
        return_value=AsyncMock(get=AsyncMock(return_value=mock_resp))
    )
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return lambda *a, **k: mock_client


def _payload(*, at_hour="09:00", hourly_times=None, precip=None,
             soil=None, wind=6.0, wdir=200.0, temp=78.0,
             sunrise="2026-06-08T05:58", sunset="2026-06-08T20:21"):
    if hourly_times is None:
        hourly_times = [f"2026-06-08T{h:02d}:00" for h in range(24)]
    n = len(hourly_times)
    if precip is None:
        precip = [0.0] * n
    if soil is None:
        soil = [0.20] * n
    return {
        "current": {
            "time": f"2026-06-08T{at_hour}",
            "wind_speed_10m": wind,
            "wind_direction_10m": wdir,
            "temperature_2m": temp,
        },
        "hourly": {
            "time": hourly_times,
            "wind_speed_10m": [wind] * n,
            "precipitation": precip,
            "soil_moisture_0_to_1cm": soil,
            "temperature_2m": [temp] * n,
        },
        "daily": {
            "time": ["2026-06-08"],
            "sunrise": [sunrise],
            "sunset": [sunset],
        },
    }


def test_fetch_forecast_conditions_success_parses_fields():
    import httpx
    with patch.object(httpx, "AsyncClient", side_effect=_mock_httpx(_payload())):
        out = asyncio.run(
            weather_now.fetch_forecast_conditions(34.74, -91.83, datetime(2026, 6, 8, 9, 0))
        )
    assert out["available"] is True
    assert out["wind_speed_mph"] == 6.0
    assert out["wind_direction_deg"] == 200.0
    assert out["wind_direction_label"] == "SSW"
    assert out["temp_f"] == 78.0
    assert out["soil_moisture_0_1cm"] == 0.20
    assert out["sunrise"] == "2026-06-08T05:58"
    assert out["sunset"] == "2026-06-08T20:21"
    assert out["inversion"]["is_estimate"] is True


def test_fetch_forecast_conditions_graceful_fail():
    import httpx
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(
        return_value=AsyncMock(get=AsyncMock(side_effect=Exception("network timeout")))
    )
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch.object(httpx, "AsyncClient", side_effect=lambda *a, **k: mock_client):
        out = asyncio.run(
            weather_now.fetch_forecast_conditions(34.74, -91.83, datetime(2026, 6, 8, 9, 0))
        )
    assert out["available"] is False
    assert "wind_speed_mph" not in out


def test_precip_next_48h_sums_hourly_window():
    import httpx
    # 49 hourly entries: one BEFORE `at` (must be excluded) + 48 from `at` forward.
    times = ["2026-06-07T23:00"] + [
        f"2026-06-{8 + (h // 24):02d}T{h % 24:02d}:00" for h in range(48)
    ]
    precip = [5.0] + [0.1] * 48  # the 5.0 is before `at`, excluded
    with patch.object(httpx, "AsyncClient",
                      side_effect=_mock_httpx(_payload(hourly_times=times, precip=precip))):
        out = asyncio.run(
            weather_now.fetch_forecast_conditions(34.74, -91.83, datetime(2026, 6, 8, 0, 0))
        )
    assert out["precip_next_48h_in"] == 4.8


def test_estimate_inversion_elevated_calm_wind_near_dawn():
    sunrise = datetime(2026, 6, 8, 6, 0)
    sunset = datetime(2026, 6, 8, 20, 0)
    out = weather_now._estimate_inversion(1.5, datetime(2026, 6, 8, 7, 0), sunrise, sunset)
    assert out["risk"] == "elevated"
    assert out["is_estimate"] is True


def test_estimate_inversion_low_midday_breezy():
    sunrise = datetime(2026, 6, 8, 6, 0)
    sunset = datetime(2026, 6, 8, 20, 0)
    out = weather_now._estimate_inversion(8.0, datetime(2026, 6, 8, 13, 0), sunrise, sunset)
    assert out["risk"] == "low"
    assert out["is_estimate"] is True


def test_estimate_inversion_unknown_when_inputs_missing():
    out = weather_now._estimate_inversion(None, datetime(2026, 6, 8, 7, 0), None, None)
    assert out["risk"] == "unknown"
    assert out["is_estimate"] is True


def test_inversion_always_is_estimate_true():
    sunrise = datetime(2026, 6, 8, 6, 0)
    sunset = datetime(2026, 6, 8, 20, 0)
    for wind, at in [(1.0, datetime(2026, 6, 8, 6, 30)),
                     (9.0, datetime(2026, 6, 8, 12, 0)),
                     (1.0, datetime(2026, 6, 8, 19, 30))]:
        assert weather_now._estimate_inversion(wind, at, sunrise, sunset)["is_estimate"] is True

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _make_open_meteo_mock():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # 24-hour data: wind=8.0 mph, direction=180deg (South), temp index 12 = 91.4
    temps = [70.0 + i * 0.5 for i in range(24)]  # index 12 = 76.0
    temps[12] = 91.4
    mock_resp.json.return_value = {
        "hourly": {
            "time": [f"2024-07-14T{h:02d}:00" for h in range(24)],
            "windspeed_10m": [8.0] * 24,
            "winddirection_10m": [180.0] * 24,  # 180 deg -> "S"
            "temperature_2m": temps,
        }
    }
    return mock_resp


def test_fetch_historical_weather_success():
    mock_resp = _make_open_meteo_mock()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(return_value=mock_resp)
        ))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        weather_mod = importlib.import_module("services.weather_history")
        result = asyncio.run(
            weather_mod.fetch_historical_weather(34.74, -91.83, "2024-07-14")
        )

    assert result["available"] is True
    assert result["source"] == "open-meteo"
    assert result["date"] == "2024-07-14"
    s = result["hourly_summary"]
    assert s["wind_speed_mph_avg"] == 8.0
    assert s["wind_direction_label"] == "S"
    assert s["temp_f_at_noon"] == 91.4


def test_fetch_historical_weather_graceful_fail():
    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(side_effect=Exception("network timeout"))
        ))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        weather_mod = importlib.import_module("services.weather_history")
        result = asyncio.run(
            weather_mod.fetch_historical_weather(34.74, -91.83, "2024-07-14")
        )

    assert result["available"] is False
    assert "hourly_summary" not in result


def _mock_httpx(hourly: dict):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"hourly": hourly}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(
        return_value=AsyncMock(get=AsyncMock(return_value=mock_resp))
    )
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return lambda *a, **k: mock_client


def test_noon_temp_picked_by_hour_label_not_index():
    # F14: day starts at 01:00 (DST spring-forward skips an hour) so hour 12
    # lands at index 11, not 12. Old temps[12] picked 13:00 (99); the hour-label
    # lookup must pick the true noon value (77).
    import httpx
    wh = importlib.import_module("services.weather_history")

    hours = list(range(1, 24))  # 01:00 .. 23:00
    times = [f"2026-03-08T{h:02d}:00" for h in hours]
    temps = [50.0] * len(times)
    temps[hours.index(12)] = 77.0   # index 11 → noon
    temps[hours.index(13)] = 99.0   # index 12 → 13:00 (old buggy pick)
    hourly = {
        "time": times,
        "temperature_2m": temps,
        "windspeed_10m": [5.0] * len(times),
        "winddirection_10m": [180.0] * len(times),
    }
    with patch.object(httpx, "AsyncClient", side_effect=_mock_httpx(hourly)):
        out = asyncio.run(wh.fetch_historical_weather(35.0, -91.0, "2026-03-08"))

    assert out["hourly_summary"]["temp_f_at_noon"] == 77.0


def test_wind_uses_daytime_application_window():
    # F14: calm overnight must not dilute the spray-window wind in the drift PDF.
    import httpx
    wh = importlib.import_module("services.weather_history")

    times = [f"2026-06-01T{h:02d}:00" for h in range(24)]
    speeds = [20.0 if 8 <= h <= 18 else 0.0 for h in range(24)]
    hourly = {
        "time": times,
        "temperature_2m": [70.0] * 24,
        "windspeed_10m": speeds,
        "winddirection_10m": [270.0] * 24,
    }
    with patch.object(httpx, "AsyncClient", side_effect=_mock_httpx(hourly)):
        out = asyncio.run(wh.fetch_historical_weather(35.0, -91.0, "2026-06-01"))

    # Daytime-only average is 20.0 (a 24h average would dilute to ~9.2).
    assert out["hourly_summary"]["wind_speed_mph_avg"] == 20.0

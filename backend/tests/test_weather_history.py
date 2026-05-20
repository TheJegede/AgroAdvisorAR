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

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _mock_open_meteo(t_max_list, t_min_list):
    """Returns an httpx mock that yields Open-Meteo daily response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    dates = [f"2026-01-{i+1:02d}" for i in range(len(t_max_list))]
    mock_resp.json.return_value = {
        "daily": {
            "time": dates,
            "temperature_2m_max": t_max_list,
            "temperature_2m_min": t_min_list,
        }
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def fake_async_client(*args, **kwargs):
        return mock_client

    return fake_async_client


def test_gdd_accumulates_correctly():
    """Two days: (20+10)/2 - 10 = 5; (15+5)/2 - 10 = 0 → total 5.0"""
    import httpx
    gdd_mod = importlib.import_module("services.gdd_calculator")

    with patch.object(httpx, "AsyncClient", side_effect=_mock_open_meteo([20.0, 15.0], [10.0, 5.0])):
        result = asyncio.run(gdd_mod.compute_gdd_since_jan1("05001"))

    assert result == 5.0


def test_gdd_unknown_fips_returns_zero():
    """Unknown FIPS should return 0.0 without making any network call."""
    gdd_mod = importlib.import_module("services.gdd_calculator")
    result = asyncio.run(gdd_mod.compute_gdd_since_jan1("99999"))
    assert result == 0.0


def test_gdd_skips_none_values():
    """None temperature values should be skipped; only valid day accumulates."""
    import httpx
    gdd_mod = importlib.import_module("services.gdd_calculator")

    with patch.object(httpx, "AsyncClient", side_effect=_mock_open_meteo([20.0, None], [10.0, None])):
        result = asyncio.run(gdd_mod.compute_gdd_since_jan1("05001"))

    assert result == 5.0

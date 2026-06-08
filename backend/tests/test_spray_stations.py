import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import spray_stations  # noqa: E402

# Stuttgart ↔ Fayetteville ≈ 184 mi great-circle (verified externally).
STUTTGART = (34.4664, -91.4151)
FAYETTEVILLE = (36.0972, -94.1733)


def test_haversine_ft_known_pair():
    d_mi = spray_stations.haversine_ft(*STUTTGART, *FAYETTEVILLE) / 5280
    assert 175 < d_mi < 195


def test_haversine_ft_zero_for_same_point():
    assert spray_stations.haversine_ft(34.7, -91.8, 34.7, -91.8) == 0.0


def test_nearest_station_picks_closest():
    stations = [
        {"id": "far", "name": "Far", "lat": 36.0972, "lon": -94.1733},
        {"id": "near", "name": "Near", "lat": 34.47, "lon": -91.42},
    ]
    s, d = spray_stations.nearest_station(34.4664, -91.4151, stations)
    assert s["id"] == "near"
    assert d < spray_stations.haversine_ft(34.4664, -91.4151, 36.0972, -94.1733)


def test_nearest_station_empty_list_returns_none():
    assert spray_stations.nearest_station(34.7, -91.8, []) == (None, None)


def test_load_stations_reads_seed_file():
    stations = spray_stations.load_stations()
    assert len(stations) >= 5
    assert all({"id", "name", "lat", "lon"} <= set(s) for s in stations)


def test_bearing_due_north_is_zero():
    b = spray_stations.bearing_deg(34.70, -91.80, 34.85, -91.80)
    assert abs(b - 0.0) < 0.5 or abs(b - 360.0) < 0.5


def test_bearing_due_east_is_ninety():
    b = spray_stations.bearing_deg(34.70, -91.80, 34.70, -91.60)
    assert abs(b - 90.0) < 0.5


def test_angular_diff_wraps_across_zero():
    assert spray_stations.angular_diff(350.0, 10.0) == 20.0
    assert spray_stations.angular_diff(10.0, 350.0) == 20.0
    assert spray_stations.angular_diff(0.0, 180.0) == 180.0

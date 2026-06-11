import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import answer_cache as ac


def test_normalized_key_collapses_case_punctuation_whitespace():
    k1 = ac.answer_cache_key("Soybean seeding rate, NE Arkansas?", "en", "05055", None)
    k2 = ac.answer_cache_key("soybean   seeding rate NE arkansas", "en", "05055", None)
    assert k1 == k2


def test_key_differs_by_language_county_and_profile():
    base = ac.answer_cache_key("soybean seeding rate", "en", "05055", None)
    assert base != ac.answer_cache_key("soybean seeding rate", "es", "05055", None)
    assert base != ac.answer_cache_key("soybean seeding rate", "en", "05001", None)
    rf = [{"field_name": "north40", "last_flood_date": "2026-05-01"}]
    assert base != ac.answer_cache_key("soybean seeding rate", "en", "05055", rf)


def test_paraphrase_misses():
    k1 = ac.answer_cache_key("soybean seeding rate", "en", "05055", None)
    k2 = ac.answer_cache_key("how many soybean seeds per acre", "en", "05055", None)
    assert k1 != k2


def test_is_cacheable_only_clean_informational():
    good = {"response_type": "informational", "products_rates": [], "warnings": [],
            "problem_summary": "Soybeans are a legume grown widely.", "recommended_actions": ["Rotate crops yearly."],
            "key_points": [], "detailed_explanation": "", "suppressed": False}
    assert ac.is_cacheable_as_reference(good) is True

    assert ac.is_cacheable_as_reference({**good, "response_type": "diagnostic"}) is False
    assert ac.is_cacheable_as_reference({**good, "products_rates": [{"product": "X"}]}) is False
    assert ac.is_cacheable_as_reference({**good, "warnings": ["Wear gloves"]}) is False
    assert ac.is_cacheable_as_reference({**good, "recommended_actions": ["Spray today before wind picks up"]}) is False
    assert ac.is_cacheable_as_reference({**good, "suppressed": True}) is False


def test_get_set_roundtrip(monkeypatch):
    store = {}
    monkeypatch.setattr(ac, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(ac, "cache_set", lambda k, v, ttl=None: store.__setitem__(k, v))
    ac.set_cached_answer("answer:abc", {"problem_summary": "ok"})
    assert ac.get_cached_answer("answer:abc") == {"problem_summary": "ok"}

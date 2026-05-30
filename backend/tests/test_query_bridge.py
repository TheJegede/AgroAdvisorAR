import sys, asyncio, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_es_request_translates_in(monkeypatch):
    q = importlib.import_module("routers.query")
    calls = {"to_en": 0}

    async def fake_to_en(text):
        calls["to_en"] += 1
        return "EN: " + text

    monkeypatch.setattr(q, "translate_to_en", fake_to_en)

    out = asyncio.run(q.maybe_translate_query("¿hola?", "es"))
    assert out == "EN: ¿hola?"
    assert calls["to_en"] == 1

    out_en = asyncio.run(q.maybe_translate_query("hello", "en"))
    assert out_en == "hello"
    assert calls["to_en"] == 1  # not called for EN

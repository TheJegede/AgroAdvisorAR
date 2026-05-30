import sys, asyncio, importlib, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on path


def _patch_providers(monkeypatch, reply):
    mod = importlib.import_module("services.translation")

    class _Resp:
        def __init__(self, c): self.content = c

    class _LLM:
        async def ainvoke(self, messages):
            return _Resp(reply)

    monkeypatch.setattr(mod, "_providers", lambda: [_LLM()])
    return mod


def test_translate_to_en_returns_translation(monkeypatch):
    mod = _patch_providers(monkeypatch, "How much nitrogen for my rice?")
    out = asyncio.run(mod.translate_to_en("¿Cuánto nitrógeno para mi arroz?"))
    assert out == "How much nitrogen for my rice?"


def test_translate_to_en_falls_back_to_original_on_failure(monkeypatch):
    mod = importlib.import_module("services.translation")
    monkeypatch.setattr(mod, "_providers", lambda: [])
    original = "¿Cuánto nitrógeno?"
    assert asyncio.run(mod.translate_to_en(original)) == original


def _advisory():
    from models.advisory import AdvisoryResponse, Cause, Product, Citation, ContextMeta
    return AdvisoryResponse(
        problem_summary="Rice shows nitrogen deficiency.",
        likely_causes=[Cause(cause="Low N", explanation="Insufficient nitrogen applied.")],
        recommended_actions=["Apply nitrogen at green-up."],
        products_rates=[Product(product="Urea", rate="150 lb N/acre", application_method="broadcast")],
        warnings=["Follow label directions."],
        citations=[Citation(document_title="Arkansas Rice Handbook", section="N management")],
        confidence="Medium",
        confidence_explanation="Grounded in one source.",
        language="en",
        context_meta=ContextMeta(soil_data_available=True, weather_data_available=True, county_fips="05031"),
    )


def test_translate_advisory_translates_prose_preserves_products(monkeypatch):
    mod = importlib.import_module("services.translation")

    class _Resp:
        def __init__(self, c): self.content = c

    class _LLM:
        async def ainvoke(self, messages):
            arr = json.loads(messages[0].content.split("\n\n", 1)[1])
            return _Resp(json.dumps(["ES:" + s for s in arr], ensure_ascii=False))

    monkeypatch.setattr(mod, "_providers", lambda: [_LLM()])
    out = asyncio.run(mod.translate_advisory_to_es(_advisory()))

    assert out.problem_summary == "ES:Rice shows nitrogen deficiency."
    assert out.likely_causes[0].cause == "ES:Low N"
    assert out.likely_causes[0].explanation == "ES:Insufficient nitrogen applied."
    assert out.recommended_actions[0] == "ES:Apply nitrogen at green-up."
    assert out.warnings[0] == "ES:Follow label directions."
    assert out.confidence_explanation == "ES:Grounded in one source."
    assert out.products_rates[0].product == "Urea"
    assert out.products_rates[0].rate == "150 lb N/acre"
    assert out.citations[0].document_title == "Arkansas Rice Handbook"
    assert out.language == "es"


def test_translate_advisory_falls_back_to_english_on_failure(monkeypatch):
    mod = importlib.import_module("services.translation")
    monkeypatch.setattr(mod, "_providers", lambda: [])
    out = asyncio.run(mod.translate_advisory_to_es(_advisory()))
    assert out.problem_summary == "Rice shows nitrogen deficiency."

# evals/tests/test_diagnostic_runner.py
from evals.diagnostic.buckets import Bucket
from evals.diagnostic.runner import build_report, ClassifiedItem


def _item(bucket, human=None, abstained=False, rule_type="flat"):
    return ClassifiedItem(query="q", bucket=bucket, human_bucket=human,
                          abstained=abstained, rule_type=rule_type)


def test_split_counts_and_b1_derivation():
    items = [
        _item(Bucket.B2),
        _item(Bucket.B2),
        _item(Bucket.B3),
        _item(Bucket.B_ABSENT, abstained=True),   # → B1
        _item(Bucket.B_ABSENT, abstained=False),  # absent but pipeline answered: hallucination flag
        _item(Bucket.B_MISS),
        _item(Bucket.QUARANTINED),
    ]
    report = build_report(items)
    assert report["counts"]["B2"] == 2
    assert report["counts"]["B3"] == 1
    assert report["counts"]["B_MISS"] == 1
    assert report["counts"]["B1"] == 1            # one B_ABSENT + abstained
    assert report["counts"]["B_ABSENT_answered"] == 1  # hallucination flag
    assert report["counts"]["QUARANTINED"] == 1


def test_judge_error_band_from_human_agreement():
    items = [
        _item(Bucket.B2, human="B2"),
        _item(Bucket.B2, human="B2"),
        _item(Bucket.B3, human="B2"),   # disagreement
        _item(Bucket.B_MISS, human=None),  # not hand-labeled → excluded
    ]
    report = build_report(items)
    # 2/3 agree on hand-labeled items → error rate ~0.333
    assert report["judge_error_rate"] == round(1 / 3, 3)
    assert report["calibration_n"] == 3


def test_conditional_rule_fraction_for_lever1():
    items = [
        _item(Bucket.B2, rule_type="conditional"),
        _item(Bucket.B2, rule_type="flat"),
        _item(Bucket.B3, rule_type="flat"),
    ]
    report = build_report(items)
    # Of answerable (B2) items, 1 of 2 is conditional.
    assert report["lever1_conditional_fraction_of_b2"] == 0.5


def _item_cond(bucket, rule_type="conditional", cond_preserved=None):
    return ClassifiedItem(query="q", bucket=bucket, human_bucket=None,
                          abstained=False, rule_type=rule_type,
                          cond_preserved=cond_preserved)


def test_conditional_completeness_rate():
    items = [
        _item_cond(Bucket.B2, cond_preserved=True),
        _item_cond(Bucket.B2, cond_preserved=False),
        _item_cond(Bucket.B2, cond_preserved=True),
        _item_cond(Bucket.B2, rule_type="flat", cond_preserved=None),  # excluded
        _item_cond(Bucket.QUARANTINED, cond_preserved=None),           # excluded
    ]
    report = build_report(items)
    # 2 of 3 scored conditional items preserved the condition.
    assert report["conditional_completeness_rate"] == round(2 / 3, 3)
    assert report["conditional_scored_n"] == 3


def test_conditional_completeness_rate_none_when_unscored():
    items = [_item_cond(Bucket.B2, rule_type="flat", cond_preserved=None)]
    report = build_report(items)
    assert report["conditional_completeness_rate"] is None
    assert report["conditional_scored_n"] == 0


import asyncio
import evals.diagnostic.runner as runner_mod
from evals.diagnostic.gold_schema import GoldRecord


def _gold(**kw):
    base = dict(
        query="how many stink bugs before I spray?", namespace="rice",
        source_in_index=True, gold_found=True,
        gold_answer="5 per 10 sweeps weeks 1-2, 10 per 10 sweeps weeks 3-4",
        gold_source="rice insect thresholds", gold_snippet="10 RSB per 10 sweeps",
        rule_type="conditional", human_bucket=None, set_aside=False,
        set_aside_reason=None,
    )
    base.update(kw)
    return GoldRecord(**base)


def test_classify_scores_conditional_item(monkeypatch):
    advisory = {"problem_summary": "Treat at 10 per 10 sweeps.",
                "key_points": [], "recommended_actions": [], "warnings": [],
                "products_rates": [], "detailed_explanation": None}

    async def fake_rag(**kwargs):
        return advisory, [{"snippet": "our threshold is 10 RSB per 10 sweeps"}]

    monkeypatch.setattr(runner_mod, "judge_containment",
                        lambda *a, **k: runner_mod.JudgeResult(span="10 RSB per 10 sweeps", partial=False))
    monkeypatch.setattr(runner_mod, "fact_retrieved", lambda *a, **k: True)
    monkeypatch.setattr(runner_mod, "judge_conditional",
                        lambda *a, **k: runner_mod.CompletenessResult(preserved=False, missing="weeks 1-2 branch"))

    item = asyncio.run(runner_mod._classify_record(_gold(), fake_rag))
    assert item.bucket is Bucket.B2
    assert item.cond_preserved is False


def test_classify_skips_conditional_scoring_for_flat_rule(monkeypatch):
    advisory = {"problem_summary": "x", "key_points": [], "recommended_actions": [],
                "warnings": [], "products_rates": [], "detailed_explanation": None}

    async def fake_rag(**kwargs):
        return advisory, [{"snippet": "y"}]

    monkeypatch.setattr(runner_mod, "judge_containment",
                        lambda *a, **k: runner_mod.JudgeResult(span="y", partial=False))
    monkeypatch.setattr(runner_mod, "fact_retrieved", lambda *a, **k: True)

    def _boom(*a, **k):
        raise AssertionError("judge_conditional must not run for flat rules")
    monkeypatch.setattr(runner_mod, "judge_conditional", _boom)

    item = asyncio.run(runner_mod._classify_record(_gold(rule_type="flat"), fake_rag))
    assert item.cond_preserved is None

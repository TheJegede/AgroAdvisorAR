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

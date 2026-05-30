"""Standalone unit test for the per-namespace aggregation in answer_eval_full.

Uses FAKE/synthetic per-item result dicts only — NO model, NO network, NO GPU.
Run:  python evals/test_per_namespace_breakdown.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from answer_eval_full import per_namespace_breakdown, _mean  # noqa: E402


def _r(ns, supp, corr, faith, conf, lang="en"):
    return {
        "namespace": ns, "lang": lang, "suppressed": supp,
        "correctness": corr, "faithfulness": faith, "confidence_score": conf,
    }


def approx(a, b, eps=1e-9):
    if a is None or b is None:
        return a is b
    return abs(a - b) < eps


def test():
    results = [
        # rice: 4 items, 1 suppressed; conf has one None (should be skipped)
        _r("rice", True, 0.0, 0.0, None),
        _r("rice", False, 1.0, 1.0, 0.90),
        _r("rice", False, 0.5, 1.0, 0.70),
        _r("rice", False, 1.0, 0.5, 0.80),
        # soybeans: 2 items, 0 suppressed
        _r("soybeans", False, 1.0, 1.0, 0.95),
        _r("soybeans", False, 0.0, 0.5, 0.40),
        # poultry: 1 item, suppressed, conf all None
        _r("poultry", True, 0.0, 0.0, None),
    ]

    rows = per_namespace_breakdown(results)
    by_ns = {(r["namespace"], r["lang"]): r for r in rows}

    # Sorted order: poultry, rice, soybeans
    assert [r["namespace"] for r in rows] == ["poultry", "rice", "soybeans"], \
        [r["namespace"] for r in rows]

    rice = by_ns[("rice", "en")]
    assert rice["count"] == 4
    assert approx(rice["suppression_rate"], 1 / 4)                      # 1 of 4 suppressed
    assert approx(rice["mean_correctness"], (0.0 + 1.0 + 0.5 + 1.0) / 4)  # 0.625
    assert approx(rice["mean_faithfulness"], (0.0 + 1.0 + 1.0 + 0.5) / 4)  # 0.625
    # confidence: None skipped -> mean of 3 values
    assert approx(rice["mean_confidence_score"], (0.90 + 0.70 + 0.80) / 3)  # 0.80

    soy = by_ns[("soybeans", "en")]
    assert soy["count"] == 2
    assert approx(soy["suppression_rate"], 0.0)
    assert approx(soy["mean_correctness"], 0.5)
    assert approx(soy["mean_faithfulness"], 0.75)
    assert approx(soy["mean_confidence_score"], (0.95 + 0.40) / 2)  # 0.675

    poultry = by_ns[("poultry", "en")]
    assert poultry["count"] == 1
    assert approx(poultry["suppression_rate"], 1.0)
    assert approx(poultry["mean_correctness"], 0.0)
    assert approx(poultry["mean_faithfulness"], 0.0)
    assert poultry["mean_confidence_score"] is None  # all-None -> None, not crash

    # lang segmentation: same namespace, different lang -> separate rows
    multilang = per_namespace_breakdown([
        _r("rice", False, 1.0, 1.0, 0.9, lang="en"),
        _r("rice", True, 0.0, 0.0, 0.1, lang="es"),
    ])
    keys = {(r["namespace"], r["lang"]) for r in multilang}
    assert keys == {("rice", "en"), ("rice", "es")}, keys

    # _mean edge cases
    assert _mean([]) is None
    assert _mean([None, None]) is None
    assert approx(_mean([1.0, None, 2.0]), 1.5)

    print("ALL ASSERTIONS PASSED")
    print("\n--- sample breakdown output ---")
    from answer_eval_full import print_per_namespace
    print_per_namespace(results)


if __name__ == "__main__":
    test()

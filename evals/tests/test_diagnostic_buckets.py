# evals/tests/test_diagnostic_buckets.py
from evals.diagnostic.buckets import Bucket, classify, JudgeResult
from evals.diagnostic.gold_schema import GoldRecord


def _gold(**over):
    base = {
        "query": "q", "namespace": "soybeans", "gold_found": True,
        "gold_answer": "a", "gold_source": "s", "gold_snippet": "snip",
        "source_in_index": True, "rule_type": "flat",
        "human_bucket": None, "set_aside": False, "set_aside_reason": None,
    }
    base.update(over)
    return GoldRecord.from_dict(base)


def test_set_aside_is_quarantined():
    rec = _gold(set_aside=True, set_aside_reason="conflicting pubs")
    assert classify(rec, JudgeResult(span="snip", partial=False), span_verified=True) is Bucket.QUARANTINED


def test_gold_not_found_is_absent():
    rec = _gold(gold_found=False, gold_answer=None, gold_source=None, gold_snippet=None, source_in_index=None)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B_ABSENT


def test_partial_is_b4():
    rec = _gold()
    assert classify(rec, JudgeResult(span="snip", partial=True), span_verified=True) is Bucket.B4


def test_verified_span_is_b2():
    rec = _gold()
    assert classify(rec, JudgeResult(span="snip", partial=False), span_verified=True) is Bucket.B2


def test_span_in_index_but_not_retrieved_is_b_miss():
    rec = _gold(source_in_index=True)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B_MISS


def test_span_absent_and_not_in_index_is_b3():
    rec = _gold(source_in_index=False)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B3


def test_judge_claims_span_but_string_match_fails_downgrades():
    # Judge returned a span, but the deterministic verifier rejected it → treat as absent.
    rec = _gold(source_in_index=False)
    assert classify(rec, JudgeResult(span="hallucinated", partial=False), span_verified=False) is Bucket.B3

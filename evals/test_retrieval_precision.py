"""Offline tests for the pure helpers in retrieval_precision.
No network, no model load — heavy imports live inside main()."""
from evals.retrieval_precision import rank_of, classify_failure, join_dump


def test_rank_of_found_first():
    assert rank_of("c3", ["c3", "c1", "c2"]) == 1

def test_rank_of_found_third():
    assert rank_of("c2", ["c0", "c1", "c2"]) == 3

def test_rank_of_missing_returns_none():
    assert rank_of("zzz", ["c0", "c1"]) is None

def test_rank_of_empty():
    assert rank_of("c0", []) is None


def test_classify_ok_when_correct():
    # corr >= 0.5 is a pass, never a failure label
    assert classify_failure(corr=1.0, faith=0.5, hit5=False) == "OK"
    assert classify_failure(corr=0.5, faith=0.0, hit5=False) == "OK"

def test_classify_retrieval_miss_when_gold_not_retrieved():
    assert classify_failure(corr=0.0, faith=0.5, hit5=False) == "RETRIEVAL_MISS"

def test_classify_gen_specificity_grounded_but_wrong():
    # gold chunk WAS retrieved, answer grounded (faith>=0.5) but wrong specifics
    assert classify_failure(corr=0.0, faith=0.5, hit5=True) == "GEN_SPECIFICITY"

def test_classify_gen_hallucination_retrieved_but_ungrounded():
    assert classify_failure(corr=0.0, faith=0.0, hit5=True) == "GEN_HALLUCINATION"


def test_join_dump_matches_by_query():
    dump = [{"query": "q1", "correctness": 0.0, "faithfulness": 0.5},
            {"query": "q2", "correctness": 1.0, "faithfulness": 1.0}]
    rec = join_dump("q2", dump)
    assert rec["correctness"] == 1.0 and rec["faithfulness"] == 1.0

def test_join_dump_missing_query_returns_none():
    assert join_dump("nope", [{"query": "q1"}]) is None

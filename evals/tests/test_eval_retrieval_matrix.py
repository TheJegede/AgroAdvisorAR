import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_retrieval_matrix import (  # noqa: E402
    EvalItem,
    hybrid_rankings,
    ndcg_at_k,
    reciprocal_rank,
    summarize_rankings,
)


def test_reciprocal_rank_and_ndcg_for_single_gold():
    ranked = ["a", "b", "gold", "c"]
    assert reciprocal_rank(ranked, "gold", 5) == 1 / 3
    assert ndcg_at_k(ranked, "gold", 5) == 0.5
    assert reciprocal_rank(ranked, "missing", 5) == 0.0
    assert ndcg_at_k(ranked, "gold", 2) == 0.0


def test_hybrid_rankings_rrf_common_candidate_wins():
    dense = [["a", "gold", "b"]]
    sparse = [["gold", "c"]]
    fused = hybrid_rankings(dense, sparse, rrf_k=60)[0]
    assert fused[0] == "gold"
    assert set(fused) == {"a", "gold", "b", "c"}


def test_summarize_rankings_global_and_namespace_breakdown():
    items = [
        EvalItem(query="q1", namespace="rice", chunk_id="r1"),
        EvalItem(query="q2", namespace="rice", chunk_id="r2"),
        EvalItem(query="q3", namespace="soybeans", chunk_id="s1"),
    ]
    rankings = {
        "dense": [
            ["r1", "x"],       # hit@1
            ["x", "r2"],       # hit@5, reciprocal rank 1/2
            ["x", "y", "z"],   # miss
        ],
        "sparse": [
            ["x", "r1"],
            ["r2"],
            ["s1"],
        ],
    }
    summary = summarize_rankings(items, rankings, top_k=5, candidate_ks=(2, 3))

    dense = summary["dense"]
    assert dense["count"] == 3
    assert dense["hit_at_1"] == 0.3333
    assert dense["hit_at_k"] == 0.6667
    assert dense["mrr_at_k"] == 0.5
    assert dense["candidate_recall_at_2"] == 0.6667
    assert dense["candidate_recall_at_3"] == 0.6667

    rice = dense["by_namespace"]["rice"]
    assert rice["count"] == 2
    assert rice["hit_at_k"] == 1.0
    assert rice["mrr_at_k"] == 0.75

    sparse = summary["sparse"]
    assert sparse["hit_at_1"] == 0.6667
    assert sparse["hit_at_k"] == 1.0

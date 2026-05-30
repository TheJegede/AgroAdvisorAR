import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_core import build_bm25, bm25_topk, rrf_fuse


def test_bm25_ranks_lexical_match_first():
    docs = [
        ("d1", "Before mixing, calibrate the sprayer accurately for the ounce method."),
        ("d2", "Poultry house ventilation and heat dissipation in summer."),
    ]
    bm = build_bm25(docs)
    ids = bm25_topk(bm, "sprayer calibration", 2)
    assert ids[0] == "d1"


def test_rrf_ranks_item_common_to_both_lists_first():
    fused = rrf_fuse([["a", "b", "c"], ["a", "d", "e"]])
    assert fused[0] == "a"


def test_rrf_includes_all_unique_ids():
    fused = rrf_fuse([["a", "b"], ["c"]])
    assert set(fused) == {"a", "b", "c"}


def test_rrf_better_rank_outranks_worse():
    fused = rrf_fuse([["x", "p", "y"]])
    assert fused.index("x") < fused.index("y")

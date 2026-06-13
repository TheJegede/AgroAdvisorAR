import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from rice_gold_curation import flag_yearly_volume_gold


def test_flag_matches_br_wells_research_volumes_only():
    rows = [
        {"query": "q1", "namespace": "rice",
         "document_title": "rice 2019 br wells arkansas rice research studies"},
        {"query": "q2", "namespace": "rice",
         "document_title": "rice 2023 br wells arkansas rice research studies"},
        # answer-bearing docs that contain a year but are NOT TOC volumes -> keep
        {"query": "q3", "namespace": "rice",
         "document_title": "rice 2026 arkansas rice management guide"},
        {"query": "q4", "namespace": "rice",
         "document_title": "rice arkansas rice production handbook"},
        # non-rice row -> never flagged
        {"query": "q5", "namespace": "soybeans",
         "document_title": "soybeans 2020 br wells research studies"},
    ]
    flagged = flag_yearly_volume_gold(rows)
    titles = {r["query"] for r in flagged}
    assert titles == {"q1", "q2"}


from rice_gold_curation import candidate_chunks


def test_candidate_chunks_ranks_topical_overlap_and_excludes_toc():
    corpus = [
        {"chunk_id": "c_pot", "namespace": "rice",
         "document_title": "rice ch 9 soil fertility",
         "source_text": "Potassium deficiency in rice reduces yield; apply potash "
                          "based on soil test potassium levels."},
        {"chunk_id": "c_water", "namespace": "rice",
         "document_title": "rice ch 10 water management",
         "source_text": "Maintain a consistent flood depth for water-seeded rice."},
        # a TOC volume must be excluded even if terms overlap
        {"chunk_id": "c_toc", "namespace": "rice",
         "document_title": "rice 2019 br wells arkansas rice research studies",
         "source_text": "potassium potassium potassium table of contents"},
        # non-rice chunk must be excluded
        {"chunk_id": "c_soy", "namespace": "soybeans",
         "document_title": "soybeans fertility",
         "source_text": "potassium for soybeans"},
    ]
    cands = candidate_chunks("how much potassium potash for my rice", corpus, k=3)
    ids = [c["chunk_id"] for c in cands]
    # top candidate is the topical potassium chunk; TOC + non-rice excluded
    assert ids[0] == "c_pot"
    assert "c_toc" not in ids
    assert "c_soy" not in ids


from rice_gold_curation import apply_curation


def test_apply_curation_drops_repoints_and_passes_through():
    rows = [
        {"query": "q_drop", "namespace": "rice", "chunk_id": "old1",
         "chunk_text": "old text 1", "document_title": "rice 2019 br wells arkansas rice research studies"},
        {"query": "q_repoint", "namespace": "rice", "chunk_id": "old2",
         "chunk_text": "old text 2", "document_title": "rice 2023 br wells arkansas rice research studies"},
        {"query": "q_keep_rice", "namespace": "rice", "chunk_id": "old3",
         "chunk_text": "keep me", "document_title": "rice arkansas rice production handbook"},
        {"query": "q_soy", "namespace": "soybeans", "chunk_id": "old4",
         "chunk_text": "soy", "document_title": "soybeans doc"},
    ]
    corpus_index = {
        "new_pot": {"chunk_id": "new_pot", "document_title": "rice ch 9 soil fertility",
                    "source_text": "potassium guidance text"},
    }
    decisions = [
        {"query": "q_drop", "action": "drop", "new_chunk_id": None, "reason": "corn question"},
        {"query": "q_repoint", "action": "repoint", "new_chunk_id": "new_pot", "reason": "potassium doc"},
    ]
    out = apply_curation(rows, corpus_index, decisions)

    queries = [r["query"] for r in out]
    assert "q_drop" not in queries                 # dropped
    assert queries == ["q_repoint", "q_keep_rice", "q_soy"]  # order preserved, drop removed

    repointed = next(r for r in out if r["query"] == "q_repoint")
    assert repointed["chunk_id"] == "new_pot"
    assert repointed["chunk_text"] == "potassium guidance text"
    assert repointed["document_title"] == "rice ch 9 soil fertility"
    assert set(repointed.keys()) == {"query", "namespace", "chunk_id", "chunk_text", "document_title"}

    # untouched rows pass through byte-for-byte
    assert next(r for r in out if r["query"] == "q_keep_rice")["chunk_text"] == "keep me"
    assert next(r for r in out if r["query"] == "q_soy")["document_title"] == "soybeans doc"


def test_apply_curation_raises_on_unknown_repoint_chunk():
    rows = [{"query": "q", "namespace": "rice", "chunk_id": "o",
             "chunk_text": "t", "document_title": "rice 2019 br wells arkansas rice research studies"}]
    decisions = [{"query": "q", "action": "repoint", "new_chunk_id": "missing", "reason": "x"}]
    try:
        apply_curation(rows, {}, decisions)
        assert False, "expected KeyError for unknown chunk_id"
    except KeyError:
        pass


from rice_gold_curation import write_audit


def test_write_audit_renders_one_row_per_change():
    rows = [
        {"query": "how much potassium for rice", "namespace": "rice", "chunk_id": "old2",
         "document_title": "rice 2023 br wells arkansas rice research studies"},
        {"query": "corn nitrogen question", "namespace": "rice", "chunk_id": "old1",
         "document_title": "rice 2019 br wells arkansas rice research studies"},
    ]
    corpus_index = {
        "new_pot": {"chunk_id": "new_pot", "document_title": "rice ch 9 soil fertility",
                    "source_text": "potassium guidance"},
    }
    decisions = [
        {"query": "how much potassium for rice", "action": "repoint",
         "new_chunk_id": "new_pot", "reason": "dedicated potassium doc"},
        {"query": "corn nitrogen question", "action": "drop",
         "new_chunk_id": None, "reason": "corn, not rice"},
    ]
    md = write_audit(rows, corpus_index, decisions)
    assert "how much potassium for rice" in md
    assert "rice 2023 br wells" in md                 # old title shown
    assert "rice ch 9 soil fertility" in md           # new title shown
    assert "new_pot" in md                            # new chunk_id shown
    assert "drop" in md.lower()                       # drop action shown
    assert "dedicated potassium doc" in md            # reason shown

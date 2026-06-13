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

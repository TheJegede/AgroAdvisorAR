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

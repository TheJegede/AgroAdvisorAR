import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from remap_eval_set import best_new_chunk_id


class _Doc:
    def __init__(self, cid, ns, text):
        self.metadata = {"chunk_id": cid, "crop_type": ns}
        self.page_content = text


def test_picks_chunk_containing_the_gold_span():
    new = [
        _Doc("n1", "rice", "Totally unrelated poultry ventilation content here."),
        _Doc("n2", "rice", "Before mixing, calibrate the sprayer accurately. "
                            "Determine gallons per acre using the ounce method."),
    ]
    gold = "calibrate the sprayer accurately"
    assert best_new_chunk_id(gold, "rice", new) == "n2"


def test_respects_namespace():
    new = [
        _Doc("p1", "poultry", "calibrate the sprayer accurately ounce method"),
        _Doc("r1", "rice", "calibrate the sprayer accurately ounce method"),
    ]
    assert best_new_chunk_id("calibrate the sprayer", "rice", new) == "r1"

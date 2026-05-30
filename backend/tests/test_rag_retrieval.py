import sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeDoc:
    def __init__(self, doc_id):
        self.id = doc_id


class _FakeVectorStore:
    """Records which namespaces were queried; returns per-namespace (doc, score)."""

    _DATA = {
        "rice": [(_FakeDoc("r1"), 0.9), (_FakeDoc("r2"), 0.4)],
        "soybeans": [(_FakeDoc("s1"), 0.7)],
        "poultry": [(_FakeDoc("p1"), 0.2)],
    }

    def __init__(self):
        self.queried_namespaces = []

    def similarity_search_with_score(self, query, k, namespace):
        self.queried_namespaces.append(namespace)
        return self._DATA.get(namespace, [])


def test_general_ag_resolves_to_all_crop_namespaces():
    rag = importlib.import_module("services.rag")
    # GENERAL_AG must fan out across the populated crop namespaces, NOT the empty
    # default namespace (the bug: it mapped to None -> Pinecone default "" -> 0 docs).
    assert rag._namespaces_for("IN_SCOPE_GENERAL_AG") == ["rice", "soybeans", "poultry"]
    # A specific crop still resolves to its single namespace.
    assert rag._namespaces_for("IN_SCOPE_RICE") == ["rice"]


def test_fanout_search_merges_namespaces_by_score():
    rag = importlib.import_module("services.rag")
    vs = _FakeVectorStore()
    docs = rag._fanout_search(vs, "cover crop after rice", 3, ["rice", "soybeans", "poultry"])
    # All crop namespaces were searched.
    assert set(vs.queried_namespaces) == {"rice", "soybeans", "poultry"}
    # Results merged and ordered by descending score, trimmed to k=3.
    assert [d.id for d in docs] == ["r1", "s1", "r2"]  # 0.9, 0.7, 0.4

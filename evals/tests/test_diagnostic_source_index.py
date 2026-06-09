# evals/tests/test_diagnostic_source_index.py
from evals.diagnostic.source_index import doc_title_in_index


class _FakeIndex:
    def __init__(self, matches):
        self._matches = matches

    def query(self, *args, **kwargs):
        # Mimic pinecone query response shape.
        return {"matches": self._matches}


def test_title_present_returns_true():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "MP44 Weed Control"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is True


def test_title_absent_returns_false():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "Rice Production Handbook"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is False


def test_match_is_case_insensitive():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "mp44 weed control"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is True


def test_no_matches_returns_false():
    idx = _FakeIndex(matches=[])
    assert doc_title_in_index("anything", index=idx, embed=lambda t: [0.0] * 8) is False

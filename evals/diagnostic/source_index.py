# evals/diagnostic/source_index.py
"""Mechanical check: is a document_title present in the Pinecone index?

Pinecone has no full-scan-by-metadata, so we embed the title text and query
top-k across namespaces, then string-match the returned titles. Good enough to
confirm presence; the human still records the flag, this just assists.
"""
import os
from typing import Callable, Optional

NAMESPACES = ("rice", "soybeans", "poultry", "general")


def doc_title_in_index(
    document_title: str,
    index=None,
    embed: Optional[Callable[[str], list]] = None,
    top_k: int = 10,
) -> bool:
    if index is None or embed is None:
        index, embed = _default_index_and_embed()
    target = document_title.strip().lower()
    vec = embed(document_title)
    for ns in NAMESPACES:
        try:
            resp = index.query(vector=vec, top_k=top_k, include_metadata=True, namespace=ns)
        except TypeError:
            # Fake/simple indexes in tests accept no kwargs.
            resp = index.query()
        matches = resp.get("matches", []) if isinstance(resp, dict) else getattr(resp, "matches", [])
        for m in matches:
            md = m.get("metadata", {}) if isinstance(m, dict) else getattr(m, "metadata", {})
            if (md.get("document_title", "") or "").strip().lower() == target:
                return True
    return False


def _default_index_and_embed():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
    from pinecone import Pinecone
    import config
    from services.embedding import MiniLMEmbeddings
    pc = Pinecone(api_key=config.PINECONE_API_KEY)
    index = pc.Index(config.PINECONE_INDEX_NAME)
    embedder = MiniLMEmbeddings()
    return index, lambda t: embedder.embed_query(t)

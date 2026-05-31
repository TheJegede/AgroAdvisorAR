"""Diagnostic: trace the RETRIEVAL stage only (no LLM, no quota).

For a handful of real farmer-style queries, embed with the production
embedder and dump the top-5 Pinecone chunks so we can eyeball whether the
"injection side" returns on-topic context BEFORE generation ever runs.

Run:
  python evals/trace_retrieval.py
Env (from repo .env): PINECONE_API_KEY, PINECONE_INDEX_NAME, EMBEDDING_MODEL_PATH
"""
import os
import json

import sys

from dotenv import load_dotenv

# Windows consoles default to cp1252 and choke on bullets/em-dashes in chunk text.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

from pinecone import Pinecone  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

INDEX = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte")
MODEL = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
EVAL = os.path.join(_ROOT, "evals", "eval_set_v2.jsonl")


def _load_samples(n_per_ns=2):
    rows = [json.loads(l) for l in open(EVAL, encoding="utf-8")]
    by_ns = {}
    for r in rows:
        by_ns.setdefault(r["namespace"], []).append(r)
    out = []
    for ns, items in by_ns.items():
        out.extend(items[:n_per_ns])
    return out


def main():
    print(f"index={INDEX}  model={MODEL}\n")
    model = SentenceTransformer(MODEL)
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(INDEX)

    samples = _load_samples()
    for r in samples:
        q, ns, gold_id, gold_title = r["query"], r["namespace"], r["chunk_id"], r.get("document_title", "?")
        qv = model.encode(q, normalize_embeddings=True).tolist()
        res = index.query(vector=qv, top_k=5, namespace=ns, include_metadata=True)
        matches = res.get("matches", [])
        ids = [m["id"] for m in matches]
        print("=" * 100)
        print(f"[{ns}] Q: {q}")
        print(f"   GOLD chunk {gold_id}  doc='{gold_title}'   gold_in_top5={gold_id in ids}")
        for i, m in enumerate(matches, 1):
            md = m.get("metadata", {}) or {}
            title = md.get("document_title", "(no title meta)")
            text = (md.get("text") or md.get("source_text") or "").replace("\n", " ")[:160]
            print(f"   #{i} score={m['score']:.3f}  doc='{title}'")
            print(f"       {text}")
        print()


if __name__ == "__main__":
    main()

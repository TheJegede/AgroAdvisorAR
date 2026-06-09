"""Bridge eval: ES query -> translate_to_en -> gte EN retrieval -> recall of the
English gold chunk, per namespace. Validates the translate-bridge end of F1.

Run (local, free):
  LLM_PRIMARY=local EMBEDDING_MODEL_PATH=thenlper/gte-base \
  PINECONE_INDEX_NAME=agroar-prod-gte-v2 python evals/eval_bridge.py
"""
import asyncio, json, os, sys
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from services.translation import translate_to_en  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from pinecone import Pinecone  # noqa: E402

EVAL = Path(__file__).parent / "ar_agqa_es.jsonl"
INDEX = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte-v2")
MODEL = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
KS = [1, 5, 20]


async def main():
    with EVAL.open(encoding="utf-8") as f:
        ev = [json.loads(l) for l in f]
    m = SentenceTransformer(MODEL, device="cuda")
    idx = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(INDEX)
    hits = defaultdict(lambda: {k: 0 for k in KS})
    counts = defaultdict(int)
    for i, e in enumerate(ev):
        en = await translate_to_en(e["query"])
        counts[e["namespace"]] += 1
        qv = m.encode(en, normalize_embeddings=True).tolist()
        r = idx.query(vector=qv, top_k=max(KS), namespace=e["namespace"], include_values=False)
        ids = [mm["id"] for mm in r.get("matches", [])]
        for k in KS:
            if e["chunk_id"] in ids[:k]:
                hits[e["namespace"]][k] += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(ev)} processed")
    print("\n=== bridge retrieval recall (ES->EN->gte) ===")
    for ns in sorted(counts):
        n = counts[ns]
        print(f"{ns:>9} n={n:>3}  " + "  ".join(f"@{k}={hits[ns][k]/n:.2f}" for k in KS))
    tot = sum(counts.values())
    print(f"overall @5={sum(hits[ns][5] for ns in counts)/tot:.2f}")


if __name__ == "__main__":
    asyncio.run(main())

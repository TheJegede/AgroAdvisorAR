"""
Build hard-negative triplets for round-2 fine-tuning.

Differences from generate_triplets.py:
  - Reads evals/eval_set_v2.jsonl (200 items)
  - Embeds with v1 fine-tuned model (harder negatives from better embedding space)
  - 3 negatives per query instead of 2
  - Outputs evals/triplets_v2.jsonl  (~600 triplets)

Run: python evals/generate_triplets_v2.py
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

V1_MODEL_PATH = str(Path(__file__).parent.parent / "models" / "agroar-embeddings-v1")
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")

EVAL_SET_PATH = Path(__file__).parent / "eval_set_v2.jsonl"
OUTPUT_PATH = Path(__file__).parent / "triplets_v2.jsonl"
TOP_K = 6
MAX_NEGATIVES_PER_QUERY = 3


def main():
    items = [json.loads(l) for l in open(EVAL_SET_PATH)]
    print(f"Eval items:      {len(items)}")
    print(f"Embedding model: {V1_MODEL_PATH}  (v1 checkpoint)")

    model = SentenceTransformer(V1_MODEL_PATH)
    index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)

    triplets = []
    skipped = 0

    for i, item in enumerate(items):
        vec = model.encode(item["query"], normalize_embeddings=True).tolist()
        result = index.query(
            vector=vec,
            top_k=TOP_K,
            namespace=item["namespace"],
            include_metadata=True,
        )

        hard_negatives = []
        for match in result.get("matches", []):
            if match["id"] == item["chunk_id"]:
                continue
            text = (match.get("metadata") or {}).get("text", "")
            if len(text) >= 100:
                hard_negatives.append(text)
            if len(hard_negatives) >= MAX_NEGATIVES_PER_QUERY:
                break

        if not hard_negatives:
            skipped += 1
            continue

        for neg_text in hard_negatives:
            triplets.append({
                "anchor": item["query"],
                "positive": item["chunk_text"],
                "negative": neg_text,
            })

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(items)} processed, {len(triplets)} triplets so far")

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for t in triplets:
            f.write(json.dumps(t) + "\n")

    print(f"\n{len(triplets)} triplets written -> {OUTPUT_PATH}")
    if skipped:
        print(f"{skipped} queries skipped (no valid hard negatives in metadata)")


if __name__ == "__main__":
    main()

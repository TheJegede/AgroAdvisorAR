"""Zero-LLM-cost retrieval/generation failure split.

Reproduces the seed=7 answer-eval sample, runs retrieval ONLY (local gte-base
embed + Pinecone top-5, no generation, no judge), and joins the gold chunk
hit@5/rank against the correctness/faithfulness already scored in the L2 dump.

Failure taxonomy per item ("hit" = gold SOURCE DOCUMENT in top-5; see below):
  OK                : corr >= 0.5 (not a failure)
  RETRIEVAL_MISS    : corr < 0.5 AND gold doc NOT in top-5  -> retrieval/corpus lever
  GEN_SPECIFICITY   : corr < 0.5 AND gold doc in top-5 AND faith >= 0.5 -> generation lever (L3: quote exact rate)
  GEN_HALLUCINATION : corr < 0.5 AND gold doc in top-5 AND faith < 0.5  -> generation/guard lever

WHY DOCUMENT-LEVEL HIT (not exact chunk_id): the eval set's gold `chunk_id`s
were minted against the v2 index. The v3 Docling re-ingest (968bc42) re-chunked
every doc, so chunk_ids changed and ZERO eval gold ids exist in v3 — an exact
chunk_id hit@5 against v3 is structurally always-miss (garbage). The dump's
corr/faith were generated on v3. `document_title` survived the migration as a
stable exact key, so we ask the joinable question: did v3 top-5 surface the gold
SOURCE DOCUMENT? Coarser than passage-level but exact, threshold-free, and
aligned to the index that produced the scored answers. (Dense cosine-to-gold
was rejected: same-crop agronomy text floors at ~0.83, so it can't discriminate
the gold passage from same-topic text.)

Heavy imports (pinecone, sentence-transformers, judge) are done inside
main() so the pure helpers below stay offline-testable.

Usage:
  cd <repo> && python -m evals.retrieval_precision \
      --eval-set evals/eval_set_v2.jsonl --sample 20 --seed 7 \
      --dump evals/_out_v3_L2on.jsonl --out evals/_retrieval_split.jsonl
"""
from __future__ import annotations


def rank_of(gold_id, ids):
    """1-based rank of gold_id in ids, or None if absent."""
    for i, x in enumerate(ids, 1):
        if x == gold_id:
            return i
    return None


def classify_failure(corr, faith, hit5):
    """Map a scored item to a failure-cause label. corr>=0.5 == pass == OK.
    hit5 = gold SOURCE DOCUMENT present in top-5 (see module docstring)."""
    if corr >= 0.5:
        return "OK"
    if not hit5:
        return "RETRIEVAL_MISS"
    if faith >= 0.5:
        return "GEN_SPECIFICITY"
    return "GEN_HALLUCINATION"


def _norm_title(t):
    """Lowercase + collapse whitespace for robust exact title matching."""
    return " ".join(str(t).lower().split())


def title_hit(gold_title, titles):
    """True if gold_title (normalized) is among the retrieved titles.
    Document-level hit@5 — stable across the v2->v3 re-chunk (chunk_ids broke,
    document_title did not). See module docstring."""
    g = _norm_title(gold_title)
    return any(_norm_title(t) == g for t in titles)


def join_dump(query, dump):
    """Find the scored dump record for query (exact match), or None."""
    for r in dump:
        if r.get("query") == query:
            return r
    return None


def _retrieve_ids(model, index, query, namespace, top_k):
    """Embed query with gte-base and return the top_k chunk ids from Pinecone.
    Mirrors evals/eval_runner.py:150-164 and ingestion/spot_check.py."""
    vec = model.encode(query, normalize_embeddings=True).tolist()
    res = index.query(vector=vec, top_k=top_k, namespace=namespace,
                      include_metadata=True)
    matches = res.get("matches", [])
    ids = [m["id"] for m in matches]
    titles = [m.get("metadata", {}).get("document_title", "?") for m in matches]
    return ids, titles


def main():
    import os, json, argparse
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    import torch
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone
    # reuse the EXACT sampler the answer-eval used, so we hit the same 20 items.
    # sample_items lives in evals/judge (answer_eval re-exports it); importing
    # straight from judge avoids pulling in heavy services.rag deps.
    from evals.judge import sample_items

    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", default="evals/eval_set_v2.jsonl")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--dump", default="evals/_out_v3_L2on.jsonl",
                    help="scored answer-eval dump to join corr/faith from")
    ap.add_argument("--out", default="evals/_retrieval_split.jsonl")
    ap.add_argument("--index", default="agroar-prod-gte-v3",
                    help="Pinecone index to retrieve from. Defaults to the "
                         "v3 index the dump was generated on (local .env may "
                         "still point at the stale v2 index).")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.eval_set, encoding="utf-8") if l.strip()]
    sample = sample_items(items, args.sample, seed=args.seed)
    dump = [json.loads(l) for l in open(args.dump, encoding="utf-8") if l.strip()]

    model_name = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)
    index_name = args.index or os.environ["PINECONE_INDEX_NAME"]
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(index_name)
    print(f"index={index_name} model={model_name} device={device} "
          f"sample={len(sample)} dump={len(dump)}")
    print("hit5 = gold SOURCE DOCUMENT (document_title) in top-5 "
          "(chunk_id hit@5 is invalid on v3 — see module docstring)")

    from collections import Counter
    counts = Counter()
    rows = []
    missing_in_dump = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for it in sample:
            ids, titles = _retrieve_ids(model, index, it["query"],
                                        it["namespace"], args.top_k)
            id_rank = rank_of(it["chunk_id"], ids)  # informational; ~always None on v3
            hit5 = title_hit(it["document_title"], titles)
            scored = join_dump(it["query"], dump)
            if scored is None:
                missing_in_dump += 1
                continue
            label = classify_failure(scored["correctness"],
                                     scored["faithfulness"], hit5)
            counts[label] += 1
            row = {
                "namespace": it["namespace"], "query": it["query"],
                "gold_chunk_id": it["chunk_id"], "gold_doc": it["document_title"],
                "hit5": hit5, "id_rank": id_rank,
                "corr": scored["correctness"], "faith": scored["faithfulness"],
                "label": label, "top_titles": titles,
            }
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nwrote {len(rows)} rows -> {args.out} "
          f"({missing_in_dump} sample items absent from dump)")
    print("\n=== FAILURE TAXONOMY (all crops) ===")
    for lbl in ["OK", "RETRIEVAL_MISS", "GEN_SPECIFICITY", "GEN_HALLUCINATION"]:
        print(f"  {lbl:18} {counts[lbl]}")
    print("\n=== PER-CROP label breakdown ===")
    by = {}
    for r in rows:
        by.setdefault(r["namespace"], Counter())[r["label"]] += 1
    for ns in sorted(by):
        c = by[ns]
        print(f"  {ns:9} " + "  ".join(f"{k}={c[k]}" for k in
              ["OK", "RETRIEVAL_MISS", "GEN_SPECIFICITY", "GEN_HALLUCINATION"]))
    print("\n=== soybean failing items (for label audit, Task 4) ===")
    for r in rows:
        if r["namespace"] == "soybeans" and r["label"] != "OK":
            print(f"  [{r['label']:16}] hit5={r['hit5']} "
                  f"corr={r['corr']} gold_doc={r['gold_doc'][:40]!r} "
                  f":: {r['query'][:70]}")


if __name__ == "__main__":
    main()

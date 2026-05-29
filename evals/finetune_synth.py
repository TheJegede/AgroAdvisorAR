"""Fine-tune retrieval embeddings on the DISJOINT synthetic query set, then
evaluate on the held-out human-style eval set. Any lift here is real
generalization (training chunks exclude all eval gold chunk_ids).

In-memory brute-force retrieval keeps query+corpus in the same model space, so
base vs fine-tuned is a fair comparison without touching Pinecone.

Usage:
    python evals/finetune_synth.py --lang en
    python evals/finetune_synth.py --lang es
"""
import argparse, json, tempfile
from pathlib import Path
from collections import defaultdict
import numpy as np

ROOT = Path(__file__).parent.parent
CFG = {
    "en": dict(base="sentence-transformers/all-MiniLM-L6-v2",
               corpus=ROOT / "ingestion" / "en_chunks" / "corpus_en.jsonl",
               synth=Path(__file__).parent / "synth_queries_en.jsonl",
               evalset=Path(__file__).parent / "eval_set_v2.jsonl"),
    "es": dict(base="BAAI/bge-m3",
               corpus=ROOT / "ingestion" / "es_chunks" / "corpus_es.jsonl",
               synth=Path(__file__).parent / "synth_queries_es.jsonl",
               evalset=Path(__file__).parent / "ar_agqa_es.jsonl"),
}
EPOCHS, BATCH, NEG_PER_Q = 3, 64, 3


def load_corpus(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    return rows, {r["chunk_id"]: r["text"] for r in rows}


def embed_corpus(model, rows):
    vecs = model.encode([r["text"] for r in rows], normalize_embeddings=True,
                        batch_size=128, show_progress_bar=False).astype("float32")
    by_ns = defaultdict(list)
    for i, r in enumerate(rows):
        by_ns[r["namespace"]].append(i)
    return {ns: (np.stack([vecs[i] for i in ix]), [rows[i]["chunk_id"] for i in ix])
            for ns, ix in by_ns.items()}


def mine(synth, ns_mat, model, text_by_id):
    qs = [s["query"] for s in synth]
    qv = model.encode(qs, normalize_embeddings=True, batch_size=128, show_progress_bar=False)
    triplets = []
    for s, v in zip(synth, qv):
        if s["namespace"] not in ns_mat:
            continue
        mat, ids = ns_mat[s["namespace"]]
        pos = text_by_id.get(s["chunk_id"])
        if not pos:
            continue
        negs = []
        for i in np.argsort(-(mat @ v))[:8]:
            cid = ids[i]
            if cid == s["chunk_id"]:
                continue
            t = text_by_id.get(cid, "")
            if len(t) >= 100:
                negs.append(t)
            if len(negs) >= NEG_PER_Q:
                break
        for nt in negs:
            triplets.append((s["query"], pos, nt))
    return triplets


def evaluate(model, rows, evalset):
    from math import log2
    ns_mat = embed_corpus(model, rows)
    ev = [json.loads(l) for l in open(evalset, encoding="utf-8")]
    mrr = ndcg = h1 = h5 = 0
    for e in ev:
        if e["namespace"] not in ns_mat:
            continue
        v = model.encode(e["query"], normalize_embeddings=True)
        mat, ids = ns_mat[e["namespace"]]
        ranked = [ids[i] for i in np.argsort(-(mat @ v))[:5]]
        g = e["chunk_id"]
        for rank, rid in enumerate(ranked, 1):
            if rid == g:
                mrr += 1 / rank
                ndcg += 1 / log2(rank + 1)
                break
        if ranked and ranked[0] == g:
            h1 += 1
        if g in ranked:
            h5 += 1
    n = len(ev)
    return dict(mrr=round(mrr/n, 4), ndcg=round(ndcg/n, 4), hit1=round(h1/n, 3), hit5=round(h5/n, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "es"], default="en")
    ap.add_argument("--save", type=Path, default=None)
    args = ap.parse_args()
    cfg = CFG[args.lang]

    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader
    import torch

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    rows, text_by_id = load_corpus(cfg["corpus"])
    synth = [json.loads(l) for l in open(cfg["synth"], encoding="utf-8")]
    print(f"corpus={len(rows)} synth_queries={len(synth)}")

    base = SentenceTransformer(cfg["base"], device=dev)
    print("Mining hard negatives (base space)...")
    triplets = mine(synth, embed_corpus(base, rows), base, text_by_id)
    print(f"triplets={len(triplets)}")

    print("BASE eval (held-out):", evaluate(base, rows, cfg["evalset"]))

    print("Fine-tuning...")
    ex = [InputExample(texts=[a, p, n]) for a, p, n in triplets]
    model = SentenceTransformer(cfg["base"], device=dev)
    dl = DataLoader(ex, shuffle=True, batch_size=BATCH)
    out = str(args.save) if args.save else tempfile.mkdtemp()
    model.fit(train_objectives=[(dl, losses.MultipleNegativesRankingLoss(model))],
              epochs=EPOCHS, warmup_steps=int(len(dl) * EPOCHS * 0.1),
              output_path=out, show_progress_bar=False)
    print(f"FINE-TUNED eval (held-out): {evaluate(model, rows, cfg['evalset'])}")
    if args.save:
        print(f"saved -> {out}")


if __name__ == "__main__":
    main()

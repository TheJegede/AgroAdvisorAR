"""Generate synthetic training queries for retrieval fine-tuning (LOCAL GPU).

For each sampled corpus chunk, asks a local instruct model (Qwen2.5-3B-Instruct on
the GPU) for realistic, colloquial farmer questions answerable BY that chunk. No
API quotas. Output is a training set DISJOINT from the held-out eval sets (eval
gold chunk_ids excluded), so fine-tuning on it and evaluating on eval_set_v2 /
ar_agqa_es measures real generalization.

Usage:
    python evals/generate_synthetic_queries.py --lang en --sample-chunks 2000 --queries-per-chunk 2

Output: evals/synth_queries_<lang>.jsonl  {query, chunk_id, namespace, lang}
Corpus cached to ingestion/en_chunks/corpus_en.jsonl on first run.
"""
import argparse
import json
import re
import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "ingestion"))
from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document

RAW = ROOT / "ingestion" / "raw_pdfs"
CORPUS_CACHE = ROOT / "ingestion" / "en_chunks" / "corpus_en.jsonl"
CROP = {"rice", "soybeans", "soybean", "poultry", "general"}
EVAL_SETS = {
    "en": Path(__file__).parent / "eval_set_v2.jsonl",
}
MIN_CHUNK_CHARS = 200
SEED = 7
MODEL = "Qwen/Qwen2.5-3B-Instruct"

PROMPT = {
    "en": (
        "You are an Arkansas row-crop / poultry farmer. Read the extension passage "
        "below and write {n} short, natural questions a real farmer would type that "
        "THIS passage answers. Each question MUST be self-contained and specific — "
        "name the crop/topic, and NEVER refer to 'this list', 'this passage', "
        "'these', 'it', or table codes. Colloquial, no jargon labels. Vary phrasing. "
        "Return ONLY a JSON array of {n} strings, nothing else.\n\nPASSAGE:\n{chunk}"
    ),
}

_VAGUE = re.compile(r"\b(this list|this passage|this table|these|the passage|the list|the table|the chart|esta lista|este pasaje|esta tabla|estos|estas)\b", re.I)


def good_chunk(text: str) -> bool:
    """Reject table/number fragments unsuitable for question generation."""
    if len(text) < MIN_CHUNK_CHARS:
        return False
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    if letters / max(len(text), 1) < 0.55:   # mostly symbols/whitespace (tables)
        return False
    if digits / max(len(text), 1) > 0.18:     # number-heavy (cultivar tables)
        return False
    if len(text.split()) < 40:                # too short to ask a real question
        return False
    return True


def good_query(q: str) -> bool:
    q = q.strip()
    if not (15 <= len(q) <= 200) or "?" not in q:
        return False
    if "[" in q or "]" in q or "{" in q:      # parse artifacts
        return False
    if _VAGUE.search(q):                       # context-dependent, not retrievable
        return False
    if any(ch >= "぀" for ch in q):        # CJK / non-latin leakage from the LLM
        return False
    return True


def infer_crop(name):
    n = name.lower()
    for c in CROP:
        if n.startswith(c + "_") or n.startswith(c + "-"):
            return c
    return "general"


def load_corpus():
    if CORPUS_CACHE.exists():
        return [json.loads(l) for l in open(CORPUS_CACHE, encoding="utf-8")]
    print("Building corpus (re-chunk PDFs)...")
    chunks = []
    for pdf in sorted(RAW.glob("*.pdf")):
        try:
            text = extract_text(str(pdf))
            tbl = extract_tables_as_text(str(pdf))
            if tbl:
                text += "\n\n" + "\n\n".join(tbl)
            title = pdf.stem.replace("_", " ").replace("-", " ")
            for d in chunk_document(text, document_title=title, source_url=str(pdf),
                                    crop_type=infer_crop(pdf.name)):
                chunks.append({"chunk_id": d.metadata.get("chunk_id"),
                               "namespace": d.metadata.get("crop_type"),
                               "text": d.page_content})
        except Exception:
            pass
    CORPUS_CACHE.parent.mkdir(exist_ok=True)
    with open(CORPUS_CACHE, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Cached {len(chunks)} chunks -> {CORPUS_CACHE}")
    return chunks


def parse_questions(raw, n):
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            qs = [str(q).strip() for q in arr if str(q).strip()]
            if qs:
                return qs[:n]
        except Exception:
            pass
    out = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip().strip('",')
        if len(line) > 8 and "?" in line:
            out.append(line)
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en"], default="en")
    ap.add_argument("--sample-chunks", type=int, default=2000)
    ap.add_argument("--queries-per-chunk", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading {MODEL} on {device}...")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.float16 if device == "cuda" else torch.float32
    ).to(device)
    model.eval()
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"

    chunks = load_corpus()
    gold = {json.loads(l)["chunk_id"] for l in open(EVAL_SETS[args.lang], encoding="utf-8")}
    pool = [c for c in chunks if c["chunk_id"] not in gold and good_chunk(c["text"])]
    print(f"chunks={len(chunks)} eval-gold-excluded={len(gold)} eligible={len(pool)}")

    random.Random(SEED).shuffle(pool)
    sample = pool[: args.sample_chunks]
    out_path = args.out or (Path(__file__).parent / f"synth_queries_{args.lang}.jsonl")

    def gen_batch(batch):
        prompts = [
            tok.apply_chat_template(
                [{"role": "user",
                  "content": PROMPT[args.lang].format(n=args.queries_per_chunk, chunk=c["text"][:1500])}],
                tokenize=False, add_generation_prompt=True)
            for c in batch
        ]
        enc = tok(prompts, return_tensors="pt", padding=True, truncation=True, max_length=1024).to(device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=160, do_sample=True,
                                 temperature=0.8, top_p=0.9, pad_token_id=tok.pad_token_id)
        gen = out[:, enc["input_ids"].shape[1]:]
        return tok.batch_decode(gen, skip_special_tokens=True)

    n_written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(0, len(sample), args.batch_size):
            batch = sample[i:i + args.batch_size]
            try:
                texts = gen_batch(batch)
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                texts = []
                for c in batch:
                    texts.extend(gen_batch([c]))
            for c, raw in zip(batch, texts):
                for q in parse_questions(raw, args.queries_per_chunk):
                    if not good_query(q):
                        continue
                    f.write(json.dumps({"query": q, "chunk_id": c["chunk_id"],
                                        "namespace": c["namespace"], "lang": args.lang},
                                       ensure_ascii=False) + "\n")
                    n_written += 1
            print(f"  {min(i+args.batch_size, len(sample))}/{len(sample)} chunks, {n_written} queries")

    print(f"\nWrote {n_written} synthetic queries -> {out_path}")


if __name__ == "__main__":
    main()

"""Generate evals/ar_agqa_es.jsonl by MT-translating eval_set_v2.jsonl.

Usage:
    python evals/build_es_eval.py
    python evals/build_es_eval.py --input evals/eval_set_v2.jsonl --output evals/ar_agqa_es.jsonl

Schema preserved: {query, chunk_id, chunk_text, document_title, namespace} — same as EN eval set.
Extra fields added: source_query_en, translation_method.

Only the `query` field is translated (natural-language question).
chunk_id, chunk_text, document_title, and namespace are kept verbatim because
they reference Pinecone chunk IDs and metadata that must match the index exactly.

After generation, manually review ~30 entries with a bilingual reviewer for accuracy.
"""
import argparse
import json
from pathlib import Path


def build_es_eval(input_path: Path, output_path: Path, batch_size: int = 16) -> int:
    rows = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No rows in input file.")
        return 0

    from transformers import MarianMTModel, MarianTokenizer

    model_name = "Helsinki-NLP/opus-mt-en-es"
    print(f"Loading tokenizer and model: {model_name}")
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    mt_model = MarianMTModel.from_pretrained(model_name)

    queries = [r["query"] for r in rows]

    def translate_batch(texts: list[str]) -> list[str]:
        inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
        translated = mt_model.generate(**inputs, max_new_tokens=256)
        return [tokenizer.decode(t, skip_special_tokens=True) for t in translated]

    print(f"Translating {len(rows)} queries in batches of {batch_size}...")
    translated_queries: list[str] = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i : i + batch_size]
        translated_queries.extend(translate_batch(batch))
        if (i + batch_size) % 64 == 0 or i + batch_size >= len(queries):
            print(f"  {min(i + batch_size, len(queries))}/{len(queries)} translated")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        for row, es_q in zip(rows, translated_queries):
            record = {
                "query": es_q,
                "chunk_id": row["chunk_id"],
                "chunk_text": row["chunk_text"],
                "document_title": row["document_title"],
                "namespace": row["namespace"],
                "source_query_en": row["query"],
                "translation_method": "mt",
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} Spanish eval pairs to {output_path}")
    print("Next: manually review ~30 entries with a bilingual reviewer.")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evals/eval_set_v2.jsonl")
    parser.add_argument("--output", default="evals/ar_agqa_es.jsonl")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    build_es_eval(Path(args.input), Path(args.output), args.batch_size)

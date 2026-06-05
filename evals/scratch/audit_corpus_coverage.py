import json
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.parent.parent
EVAL_SET_PATH = ROOT / "evals" / "eval_set_v2.jsonl"
CORPUS_PATH = ROOT / "ingestion" / "en_chunks" / "corpus_en.jsonl"

def read_jsonl(path):
    items = []
    if not path.exists():
        print(f"Path does not exist: {path}")
        return items
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items

def main():
    print("Reading evaluation set...")
    eval_items = read_jsonl(EVAL_SET_PATH)
    print(f"Loaded {len(eval_items)} evaluation items.")

    print("Reading corpus chunks...")
    corpus_items = read_jsonl(CORPUS_PATH)
    print(f"Loaded {len(corpus_items)} corpus chunks.")

    # Index corpus by chunk_id
    corpus_by_id = {item["chunk_id"]: item for item in corpus_items}

    # Audit
    missing = []
    text_mismatches = []
    
    for i, eval_item in enumerate(eval_items, start=1):
        chunk_id = eval_item.get("chunk_id")
        gold_text = eval_item.get("chunk_text", "").strip()
        namespace = eval_item.get("namespace", "")
        
        if not chunk_id:
            print(f"Item {i} has no chunk_id: {eval_item}")
            continue

        if chunk_id not in corpus_by_id:
            missing.append({
                "item_index": i,
                "query": eval_item.get("query"),
                "chunk_id": chunk_id,
                "namespace": namespace,
            })
        else:
            corpus_item = corpus_by_id[chunk_id]
            corpus_text = corpus_item.get("text", "").strip()
            
            # Simple normalization of whitespace to check overlap/matches
            gold_norm = " ".join(gold_text.split())
            corpus_norm = " ".join(corpus_text.split())
            
            if gold_norm not in corpus_norm and corpus_norm not in gold_norm:
                # Let's check token overlap
                gold_tokens = set(gold_norm.lower().split())
                corpus_tokens = set(corpus_norm.lower().split())
                overlap = len(gold_tokens & corpus_tokens) / max(1, len(gold_tokens))
                if overlap < 0.8: # high threshold for mismatch
                    text_mismatches.append({
                        "item_index": i,
                        "query": eval_item.get("query"),
                        "chunk_id": chunk_id,
                        "gold_text": gold_text,
                        "corpus_text": corpus_text,
                        "overlap": round(overlap, 4)
                    })

    print("\n=== AUDIT RESULTS ===")
    print(f"Total gold queries checked: {len(eval_items)}")
    print(f"Missing from corpus: {len(missing)}")
    print(f"Text mismatches (overlap < 80%): {len(text_mismatches)}")

    if missing:
        print("\n--- Missing Chunks ---")
        for m in missing[:10]:
            print(f"Index {m['item_index']} | ID: {m['chunk_id']} | Namespace: {m['namespace']} | Q: {m['query']}")
        if len(missing) > 10:
            print(f"... and {len(missing) - 10} more.")

    if text_mismatches:
        print("\n--- Text Mismatches ---")
        for tm in text_mismatches[:5]:
            print(f"Index {tm['item_index']} | ID: {tm['chunk_id']} | Overlap: {tm['overlap']} | Q: {tm['query']}")
            print(f"  Gold:   {tm['gold_text'][:100]}...")
            print(f"  Corpus: {tm['corpus_text'][:100]}...")
        if len(text_mismatches) > 5:
            print(f"... and {len(text_mismatches) - 5} more.")

if __name__ == "__main__":
    main()

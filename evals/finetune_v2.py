"""
Round-2 fine-tuning: continue from v1 checkpoint.

Differences from finetune.py:
  - BASE_MODEL = models/agroar-embeddings-v1  (not all-MiniLM-L6-v2)
  - Reads evals/triplets_v2.jsonl (~600 triplets)
  - 5 epochs, batch 32 (GPU), warmup 10%
  - Saves to models/agroar-embeddings-v2

Run: python evals/finetune_v2.py
GPU auto-detected. CPU fallback works but takes ~60 min.
"""
import json
from pathlib import Path
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

TRIPLETS_PATH = Path(__file__).parent / "triplets_v2.jsonl"
BASE_MODEL = str(Path(__file__).parent.parent / "models" / "agroar-embeddings-v1")
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "agroar-embeddings-v2"

EPOCHS = 5
BATCH_SIZE = 32
WARMUP_RATIO = 0.1


def main():
    triplets = [json.loads(l) for l in open(TRIPLETS_PATH, encoding="utf-8")]
    print(f"Triplets:   {len(triplets)}")
    print(f"Base model: {BASE_MODEL}  (v1 checkpoint)")
    print(f"Output:     {OUTPUT_DIR}")

    examples = [
        InputExample(texts=[t["anchor"], t["positive"], t["negative"]])
        for t in triplets
    ]

    model = SentenceTransformer(BASE_MODEL)
    loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    loss = losses.MultipleNegativesRankingLoss(model)

    warmup_steps = int(len(loader) * EPOCHS * WARMUP_RATIO)
    print(f"Steps/epoch: {len(loader)}  Warmup steps: {warmup_steps}  Total steps: {len(loader) * EPOCHS}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_objectives=[(loader, loss)],
        epochs=EPOCHS,
        warmup_steps=warmup_steps,
        output_path=str(OUTPUT_DIR),
        show_progress_bar=True,
    )

    print(f"\nFine-tuned model saved -> {OUTPUT_DIR}")
    print("Next: EMBEDDING_MODEL_PATH=./models/agroar-embeddings-v2 python evals/eval_runner.py --eval-set evals/eval_set_v2.jsonl")


if __name__ == "__main__":
    main()

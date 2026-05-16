"""
Fine-tune all-MiniLM-L6-v2 on Arkansas ag triplets.

Uses MultipleNegativesRankingLoss (anchor, positive, hard_negative).
Reads evals/triplets.jsonl, saves to models/agroar-embeddings-v1/.

Run: python evals/finetune.py
GPU auto-detected. CPU fallback works but is slow (~30 min vs ~2 min on GPU).
"""
import json
from pathlib import Path
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

TRIPLETS_PATH = Path(__file__).parent / "triplets.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "agroar-embeddings-v1"
BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

EPOCHS = 3
BATCH_SIZE = 16
WARMUP_RATIO = 0.1


def main():
    triplets = [json.loads(l) for l in open(TRIPLETS_PATH, encoding="utf-8")]
    print(f"Triplets:   {len(triplets)}")
    print(f"Base model: {BASE_MODEL}")
    print(f"Output:     {OUTPUT_DIR}")

    examples = [
        InputExample(texts=[t["anchor"], t["positive"], t["negative"]])
        for t in triplets
    ]

    model = SentenceTransformer(BASE_MODEL)
    loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    loss = losses.MultipleNegativesRankingLoss(model)

    warmup_steps = int(len(loader) * EPOCHS * WARMUP_RATIO)
    print(f"Steps/epoch: {len(loader)}  Warmup steps: {warmup_steps}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_objectives=[(loader, loss)],
        epochs=EPOCHS,
        warmup_steps=warmup_steps,
        output_path=str(OUTPUT_DIR),
        show_progress_bar=True,
    )

    print(f"\nFine-tuned model saved -> {OUTPUT_DIR}")
    print("Next: set EMBEDDING_MODEL_PATH=./models/agroar-embeddings-v1 and run eval_runner.py")


if __name__ == "__main__":
    main()

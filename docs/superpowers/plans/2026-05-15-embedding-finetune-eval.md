# Embedding Fine-Tuning + Eval Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an eval pipeline (MRR@5), generate 500+ training triplets, fine-tune all-MiniLM-L6-v2 on AR agricultural queries, re-embed the Pinecone corpus, and confirm a ≥10% MRR@5 improvement — or document the result and keep the base model.

**Architecture:** Eval set first (100 farmer queries + ground-truth chunk IDs), baseline MRR@5 measured, triplets generated using base model top-k as hard negatives, MiniLM fine-tuned with MultipleNegativesRankingLoss, corpus re-embedded via existing pipeline --force, post-finetune MRR@5 compared. EMBEDDING_MODEL_PATH env var controls which model both the backend and ingestion pipeline use — swapping is one env var change, rollback is one pipeline run.

**Tech Stack:** sentence-transformers, PyTorch (GPU), Pinecone, Gemini 2.5 Flash Lite (query generation), LangChain Google GenAI, existing chunker/extractor from ingestion/

---

## Files Created / Modified

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `ingestion/embedder.py` | Read model path from EMBEDDING_MODEL_PATH env var |
| Modify | `backend/services/embedding.py` | Read model path from EMBEDDING_MODEL_PATH env var |
| Modify | `backend/config.py` | Add EMBEDDING_MODEL_PATH config var |
| Create | `evals/__init__.py` | Package marker |
| Create | `evals/generate_eval_set.py` | Re-chunks PDFs, calls Gemini for farmer queries, writes eval_set.jsonl |
| Create | `evals/eval_runner.py` | Embeds queries, queries Pinecone top-5, computes MRR@5 + NDCG@5 |
| Create | `evals/generate_triplets.py` | Generates 500+ (query, positive, hard_negatives) triplets |
| Create | `evals/finetune.py` | Fine-tunes MiniLM with MultipleNegativesRankingLoss |
| Create | `evals/eval_set.jsonl` | (generated) 100-item eval set |
| Create | `evals/training_triplets.jsonl` | (generated) 500+ training triplets |
| Create | `evals/results/` | Eval run JSON files (baseline + post-finetune) |
| Create | `models/agroar-embeddings-v1/` | (generated) Fine-tuned model output |

---

## Task 1: Add EMBEDDING_MODEL_PATH Config

**Files:**
- Modify: `ingestion/embedder.py`
- Modify: `backend/services/embedding.py`
- Modify: `backend/config.py`

- [ ] **Step 1: Update `ingestion/embedder.py` — read model path from env**

  Replace line 8 (`MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"`) with:

  ```python
  """Embed document chunks and upsert to Pinecone."""
  import os
  import time
  from dotenv import load_dotenv
  from pathlib import Path

  load_dotenv(Path(__file__).parent.parent / ".env")

  from sentence_transformers import SentenceTransformer
  from pinecone import Pinecone, ServerlessSpec
  from langchain_core.documents import Document

  MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")
  BATCH_SIZE = 64
  ```

  > The rest of `embedder.py` (functions `get_pinecone_index` and `embed_and_upsert`) stays unchanged.

- [ ] **Step 2: Update `backend/services/embedding.py` — read model path from env**

  Replace the file with:

  ```python
  """Singleton sentence-transformer embedder for query-time embedding."""
  import os
  from sentence_transformers import SentenceTransformer
  from langchain_core.embeddings import Embeddings

  _model: SentenceTransformer | None = None
  MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")


  def get_model() -> SentenceTransformer:
      global _model
      if _model is None:
          _model = SentenceTransformer(MODEL_NAME)
      return _model


  class MiniLMEmbeddings(Embeddings):
      """LangChain-compatible embeddings wrapper."""

      def embed_documents(self, texts: list[str]) -> list[list[float]]:
          model = get_model()
          return model.encode(texts, normalize_embeddings=True).tolist()

      def embed_query(self, text: str) -> list[float]:
          model = get_model()
          return model.encode(text, normalize_embeddings=True).tolist()
  ```

- [ ] **Step 3: Add EMBEDDING_MODEL_PATH to `backend/config.py`**

  Add after the `SENTRY_DSN` line:

  ```python
  EMBEDDING_MODEL_PATH = os.environ.get(
      "EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2"
  )
  ```

- [ ] **Step 4: Verify both paths load correctly**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor\backend
  python -c "from services.embedding import MODEL_NAME; print('backend model:', MODEL_NAME)"

  cd C:\Users\jeged\Downloads\AgroAdvisor\ingestion
  python -c "from embedder import MODEL_NAME; print('ingestion model:', MODEL_NAME)"
  ```

  Expected:
  ```
  backend model: sentence-transformers/all-MiniLM-L6-v2
  ingestion model: sentence-transformers/all-MiniLM-L6-v2
  ```

- [ ] **Step 5: Verify env var override works**

  ```powershell
  $env:EMBEDDING_MODEL_PATH = "./models/agroar-embeddings-v1"
  cd C:\Users\jeged\Downloads\AgroAdvisor\backend
  python -c "from services.embedding import MODEL_NAME; print('backend model:', MODEL_NAME)"
  Remove-Item Env:\EMBEDDING_MODEL_PATH
  ```

  Expected: `backend model: ./models/agroar-embeddings-v1`

---

## Task 2: Build Eval Set Generator

**Files:**
- Create: `evals/__init__.py`
- Create: `evals/generate_eval_set.py`

- [ ] **Step 1: Create `evals/__init__.py`**

  Empty file — just a package marker:
  ```python
  ```

- [ ] **Step 2: Create `evals/generate_eval_set.py`**

  ```python
  """
  Generate 100-item eval set: farmer queries + ground-truth chunk IDs.

  Samples chunks from raw_pdfs/, calls Gemini to generate realistic farmer
  queries, writes evals/eval_set.jsonl.

  Run: python evals/generate_eval_set.py
  """
  import sys, os, json, random
  from pathlib import Path
  from dotenv import load_dotenv

  load_dotenv(Path(__file__).parent.parent / ".env")

  sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))
  from extractor import extract_text
  from chunker import chunk_document

  from langchain_google_genai import ChatGoogleGenerativeAI
  from langchain_core.messages import HumanMessage

  GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
  RAW_PDFS_DIR = Path(__file__).parent.parent / "ingestion" / "raw_pdfs"
  OUTPUT_PATH = Path(__file__).parent / "eval_set.jsonl"

  # 100 total, proportional to corpus size
  TARGET_PER_NAMESPACE = {"rice": 55, "soybeans": 35, "poultry": 10}
  MIN_CHUNK_LEN = 200

  PROMPT = """You are simulating an Arkansas farmer asking for agricultural advice.
  Given this excerpt from a University of Arkansas Extension publication:

  {chunk_text}

  Write ONE question that a real farmer might ask that this text would help answer.
  Rules:
  - Write as a working farmer, not a researcher
  - Use plain language: describe symptoms, observations, field problems
  - Do NOT use the document's exact wording or scientific terminology
  - Keep it under 80 words

  Return only the question. Nothing else."""


  def _infer_namespace(filename: str) -> str:
      name = filename.lower()
      for crop in ["rice", "soybeans", "poultry"]:
          if name.startswith(crop):
              return crop
      return "general"


  def main():
      random.seed(42)

      llm = ChatGoogleGenerativeAI(
          model="gemini-2.5-flash-lite",
          google_api_key=GOOGLE_API_KEY,
          temperature=0.4,
      )

      chunks_by_ns: dict[str, list] = {"rice": [], "soybeans": [], "poultry": []}

      pdf_files = list(RAW_PDFS_DIR.glob("*.pdf"))
      print(f"Chunking {len(pdf_files)} PDFs...")

      for pdf_path in pdf_files:
          ns = _infer_namespace(pdf_path.name)
          if ns not in chunks_by_ns:
              continue
          try:
              text = extract_text(str(pdf_path))
              title = pdf_path.stem.replace("_", " ").replace("-", " ")
              docs = chunk_document(
                  text,
                  document_title=title,
                  source_url=f"file://{pdf_path.resolve()}",
                  crop_type=ns,
              )
              chunks_by_ns[ns].extend(
                  d for d in docs if len(d.page_content) >= MIN_CHUNK_LEN
              )
          except Exception as e:
              print(f"  Skip {pdf_path.name}: {e}")

      for ns, chunks in chunks_by_ns.items():
          print(f"  {ns}: {len(chunks)} valid chunks")

      sampled = []
      for ns, target in TARGET_PER_NAMESPACE.items():
          pool = chunks_by_ns[ns]
          sampled.extend(random.sample(pool, min(target, len(pool))))
      random.shuffle(sampled)

      print(f"Generating queries for {len(sampled)} chunks via Gemini...")
      results = []

      for i, doc in enumerate(sampled):
          try:
              resp = llm.invoke([HumanMessage(content=PROMPT.format(chunk_text=doc.page_content))])
              query = resp.content.strip()
              results.append({
                  "query": query,
                  "chunk_id": doc.metadata["chunk_id"],
                  "chunk_text": doc.page_content,
                  "document_title": doc.metadata["document_title"],
                  "namespace": doc.metadata["crop_type"],
              })
          except Exception as e:
              print(f"  Skip chunk {doc.metadata['chunk_id']}: {e}")

          if (i + 1) % 10 == 0:
              print(f"  {i+1}/{len(sampled)} done")

      OUTPUT_PATH.parent.mkdir(exist_ok=True)
      with open(OUTPUT_PATH, "w") as f:
          for item in results:
              f.write(json.dumps(item) + "\n")

      print(f"\nWrote {len(results)} items → {OUTPUT_PATH}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 3: Run the eval set generator**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python evals/generate_eval_set.py
  ```

  Expected (takes ~5-10 min due to Gemini calls):
  ```
  Chunking 154 PDFs...
    rice: XXXX valid chunks
    soybeans: XXXX valid chunks
    poultry: XXXX valid chunks
  Generating queries for 100 chunks via Gemini...
    10/100 done
    ...
    100/100 done
  Wrote 100 items → evals\eval_set.jsonl
  ```

- [ ] **Step 4: Spot-check output**

  ```powershell
  Get-Content "C:\Users\jeged\Downloads\AgroAdvisor\evals\eval_set.jsonl" | Select-Object -First 3 | ForEach-Object { $_ | ConvertFrom-Json | Select-Object query, namespace, document_title }
  ```

  Expected: 3 lines each with a farmer-language query, a namespace (rice/soybeans/poultry), and a document title.

---

## Task 3: Build MRR@5 Eval Runner

**Files:**
- Create: `evals/eval_runner.py`

- [ ] **Step 1: Create `evals/eval_runner.py`**

  ```python
  """
  MRR@5 + NDCG@5 eval runner.

  Loads evals/eval_set.jsonl, embeds each query with the current embedding model
  (read from EMBEDDING_MODEL_PATH env var), queries Pinecone top-5, and computes
  retrieval metrics. Saves results to evals/results/eval_TIMESTAMP.json.

  Run: python evals/eval_runner.py
  To test fine-tuned model: set EMBEDDING_MODEL_PATH=./models/agroar-embeddings-v1 first.
  """
  import os, json, math
  from pathlib import Path
  from datetime import datetime
  from dotenv import load_dotenv

  load_dotenv(Path(__file__).parent.parent / ".env")

  from sentence_transformers import SentenceTransformer
  from pinecone import Pinecone

  EMBEDDING_MODEL_PATH = os.environ.get(
      "EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2"
  )
  PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
  PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")

  EVAL_SET_PATH = Path(__file__).parent / "eval_set.jsonl"
  RESULTS_DIR = Path(__file__).parent / "results"
  TOP_K = 5


  def _mrr(retrieved: list[str], relevant: str, k: int = 5) -> float:
      for rank, rid in enumerate(retrieved[:k], start=1):
          if rid == relevant:
              return 1.0 / rank
      return 0.0


  def _ndcg(retrieved: list[str], relevant: str, k: int = 5) -> float:
      for rank, rid in enumerate(retrieved[:k], start=1):
          if rid == relevant:
              return 1.0 / math.log2(rank + 1)
      return 0.0


  def run_eval() -> dict:
      items = [json.loads(l) for l in open(EVAL_SET_PATH)]
      print(f"Eval items:      {len(items)}")
      print(f"Embedding model: {EMBEDDING_MODEL_PATH}")

      model = SentenceTransformer(EMBEDDING_MODEL_PATH)
      index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)

      mrr_scores, ndcg_scores = [], []
      hits1, hits5 = 0, 0

      for i, item in enumerate(items):
          vec = model.encode(item["query"], normalize_embeddings=True).tolist()
          result = index.query(
              vector=vec,
              top_k=TOP_K,
              namespace=item["namespace"],
              include_values=False,
          )
          ids = [m["id"] for m in result.get("matches", [])]
          mrr_scores.append(_mrr(ids, item["chunk_id"]))
          ndcg_scores.append(_ndcg(ids, item["chunk_id"]))
          if ids and ids[0] == item["chunk_id"]:
              hits1 += 1
          if item["chunk_id"] in ids:
              hits5 += 1
          if (i + 1) % 10 == 0:
              print(f"  {i+1}/{len(items)} evaluated")

      n = len(items)
      summary = {
          "model": EMBEDDING_MODEL_PATH,
          "timestamp": datetime.utcnow().isoformat(),
          "n_items": n,
          "mrr_at_5": round(sum(mrr_scores) / n, 4),
          "ndcg_at_5": round(sum(ndcg_scores) / n, 4),
          "hit_at_1": round(hits1 / n, 4),
          "hit_at_5": round(hits5 / n, 4),
      }

      print("\n=== EVAL RESULTS ===")
      for k, v in summary.items():
          print(f"  {k}: {v}")

      RESULTS_DIR.mkdir(exist_ok=True)
      ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
      out = RESULTS_DIR / f"eval_{ts}.json"
      out.write_text(json.dumps(summary, indent=2))
      print(f"\nSaved → {out}")
      return summary


  if __name__ == "__main__":
      run_eval()
  ```

- [ ] **Step 2: Verify import works**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python -c "from evals.eval_runner import run_eval; print('import OK')"
  ```

  Expected: `import OK`

---

## Task 4: Run Baseline Eval

**Files:** none — just running existing code.

- [ ] **Step 1: Run eval against Pinecone with base model**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python evals/eval_runner.py
  ```

  Expected output (values will vary):
  ```
  Eval items:      100
  Embedding model: sentence-transformers/all-MiniLM-L6-v2
    10/100 evaluated
    ...
    100/100 evaluated

  === EVAL RESULTS ===
    model: sentence-transformers/all-MiniLM-L6-v2
    mrr_at_5: 0.XXXX
    ndcg_at_5: 0.XXXX
    hit_at_1: 0.XXXX
    hit_at_5: 0.XXXX
  Saved → evals\results\eval_TIMESTAMP.json
  ```

- [ ] **Step 2: Record the baseline MRR@5**

  Open `evals/results/eval_TIMESTAMP.json` and note the `mrr_at_5` value.
  This is the number to beat. Target: fine-tuned model must exceed this by ≥0.10 (10 percentage points, e.g. 0.30 → 0.40).

  Write the baseline value here for reference: **baseline MRR@5 = `___`**

---

## Task 5: Build Training Triplet Generator

**Files:**
- Create: `evals/generate_triplets.py`

- [ ] **Step 1: Create `evals/generate_triplets.py`**

  ```python
  """
  Generate 500+ training triplets for fine-tuning.

  For each sampled chunk (excluded from eval set):
    1. Generate a farmer query via Gemini
    2. Retrieve top-5 from Pinecone using BASE model
    3. Hard negatives = retrieved chunks that are NOT the positive

  Writes evals/training_triplets.jsonl.
  Run: python evals/generate_triplets.py
  """
  import sys, os, json, random
  from pathlib import Path
  from dotenv import load_dotenv

  load_dotenv(Path(__file__).parent.parent / ".env")

  sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))
  from extractor import extract_text
  from chunker import chunk_document

  from langchain_google_genai import ChatGoogleGenerativeAI
  from langchain_core.messages import HumanMessage
  from sentence_transformers import SentenceTransformer
  from pinecone import Pinecone

  GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
  # Always use base model for generating hard negatives — fine-tuned model doesn't exist yet
  BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
  PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
  PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")

  RAW_PDFS_DIR = Path(__file__).parent.parent / "ingestion" / "raw_pdfs"
  EVAL_SET_PATH = Path(__file__).parent / "eval_set.jsonl"
  OUTPUT_PATH = Path(__file__).parent / "training_triplets.jsonl"

  TARGET_TRIPLETS = 500
  MIN_CHUNK_LEN = 200

  PROMPT = """You are simulating an Arkansas farmer asking for agricultural advice.
  Given this excerpt from a University of Arkansas Extension publication:

  {chunk_text}

  Write ONE question that a real farmer might ask that this text would help answer.
  Rules:
  - Write as a working farmer, not a researcher
  - Use plain language: describe symptoms, observations, field problems
  - Do NOT use the document's exact wording or scientific terminology
  - Keep it under 80 words

  Return only the question. Nothing else."""


  def _infer_namespace(filename: str) -> str:
      name = filename.lower()
      for crop in ["rice", "soybeans", "poultry"]:
          if name.startswith(crop):
              return crop
      return "general"


  def main():
      random.seed(99)

      # Load eval set chunk IDs — exclude these from training
      eval_ids = {json.loads(l)["chunk_id"] for l in open(EVAL_SET_PATH)}
      print(f"Excluding {len(eval_ids)} eval set chunks from training")

      # Collect all non-eval chunks
      all_chunks = []
      for pdf_path in RAW_PDFS_DIR.glob("*.pdf"):
          ns = _infer_namespace(pdf_path.name)
          if ns == "general":
              continue
          try:
              text = extract_text(str(pdf_path))
              title = pdf_path.stem.replace("_", " ").replace("-", " ")
              docs = chunk_document(
                  text,
                  document_title=title,
                  source_url=f"file://{pdf_path.resolve()}",
                  crop_type=ns,
              )
              all_chunks.extend(
                  d for d in docs
                  if len(d.page_content) >= MIN_CHUNK_LEN
                  and d.metadata["chunk_id"] not in eval_ids
              )
          except Exception as e:
              print(f"  Skip {pdf_path.name}: {e}")

      print(f"Available training chunks: {len(all_chunks)}")
      sampled = random.sample(all_chunks, min(TARGET_TRIPLETS + 100, len(all_chunks)))

      llm = ChatGoogleGenerativeAI(
          model="gemini-2.5-flash-lite",
          google_api_key=GOOGLE_API_KEY,
          temperature=0.4,
      )
      embed_model = SentenceTransformer(BASE_MODEL)
      index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)

      triplets = []

      for i, doc in enumerate(sampled):
          if len(triplets) >= TARGET_TRIPLETS:
              break

          chunk_id = doc.metadata["chunk_id"]
          ns = doc.metadata["crop_type"]

          # Generate farmer query
          try:
              resp = llm.invoke([HumanMessage(content=PROMPT.format(chunk_text=doc.page_content))])
              query = resp.content.strip()
          except Exception as e:
              print(f"  Skip {chunk_id} (query gen failed): {e}")
              continue

          # Retrieve top-5 → hard negatives are ranks that are NOT the positive
          vec = embed_model.encode(query, normalize_embeddings=True).tolist()
          result = index.query(
              vector=vec,
              top_k=6,
              namespace=ns,
              include_metadata=True,
          )
          matches = result.get("matches", [])
          hard_negs = [
              m for m in matches
              if m["id"] != chunk_id and m.get("metadata", {}).get("text")
          ][:3]

          if not hard_negs:
              continue

          triplets.append({
              "query": query,
              "positive_chunk_id": chunk_id,
              "positive_text": doc.page_content,
              "negatives": [
                  {"chunk_id": m["id"], "text": m["metadata"]["text"]}
                  for m in hard_negs
              ],
          })

          if len(triplets) % 50 == 0:
              print(f"  {len(triplets)}/{TARGET_TRIPLETS} triplets")

      with open(OUTPUT_PATH, "w") as f:
          for t in triplets:
              f.write(json.dumps(t) + "\n")

      print(f"\nWrote {len(triplets)} triplets → {OUTPUT_PATH}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Run the triplet generator**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python evals/generate_triplets.py
  ```

  Expected (~15-25 min — 500 Gemini calls + 500 Pinecone queries):
  ```
  Excluding 100 eval set chunks from training
  Available training chunks: XXXXX
    50/500 triplets
    100/500 triplets
    ...
    500/500 triplets
  Wrote 500 triplets → evals\training_triplets.jsonl
  ```

- [ ] **Step 3: Verify triplet structure**

  ```powershell
  Get-Content "C:\Users\jeged\Downloads\AgroAdvisor\evals\training_triplets.jsonl" | Select-Object -First 1 | ConvertFrom-Json | ConvertTo-Json -Depth 3
  ```

  Expected: JSON with `query`, `positive_chunk_id`, `positive_text`, and `negatives` array with at least 1 item each having `chunk_id` and `text`.

---

## Task 6: Fine-Tune MiniLM

**Files:**
- Create: `evals/finetune.py`

- [ ] **Step 1: Verify GPU is available to PyTorch**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
  ```

  Expected: `CUDA available: True` and your GPU name. If False, training will still work but takes 5-10x longer.

- [ ] **Step 2: Create `evals/finetune.py`**

  ```python
  """
  Fine-tune all-MiniLM-L6-v2 on agricultural query triplets.

  Loads evals/training_triplets.jsonl, trains with MultipleNegativesRankingLoss,
  saves fine-tuned model to models/agroar-embeddings-v1/.

  Run: python evals/finetune.py
  Expected time: ~20-40 min on GPU, ~2-3 hours on CPU.
  """
  import os, json
  from pathlib import Path
  from dotenv import load_dotenv

  load_dotenv(Path(__file__).parent.parent / ".env")

  from sentence_transformers import SentenceTransformer, InputExample, losses
  from torch.utils.data import DataLoader

  # Always fine-tune from the base model, not a previously fine-tuned version
  BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
  TRIPLETS_PATH = Path(__file__).parent / "training_triplets.jsonl"
  MODEL_OUTPUT_DIR = Path(__file__).parent.parent / "models" / "agroar-embeddings-v1"

  EPOCHS = 3
  BATCH_SIZE = 16


  def main():
      triplets = [json.loads(l) for l in open(TRIPLETS_PATH)]
      print(f"Loaded {len(triplets)} triplets")

      # InputExample: [query, positive, neg1, neg2, neg3]
      # MultipleNegativesRankingLoss treats first text as anchor, second as positive,
      # rest as explicit negatives (in addition to in-batch negatives)
      train_examples = []
      for t in triplets:
          texts = [t["query"], t["positive_text"]]
          for neg in t["negatives"]:
              texts.append(neg["text"])
          train_examples.append(InputExample(texts=texts))

      model = SentenceTransformer(BASE_MODEL)
      dataloader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
      loss_fn = losses.MultipleNegativesRankingLoss(model=model)

      warmup_steps = int(len(dataloader) * EPOCHS * 0.1)
      print(f"Training: {EPOCHS} epochs | batch={BATCH_SIZE} | warmup={warmup_steps} steps")
      print(f"Output:   {MODEL_OUTPUT_DIR}")

      model.fit(
          train_objectives=[(dataloader, loss_fn)],
          epochs=EPOCHS,
          warmup_steps=warmup_steps,
          show_progress_bar=True,
          output_path=str(MODEL_OUTPUT_DIR),
      )

      print(f"\nFine-tuned model saved → {MODEL_OUTPUT_DIR}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 3: Run fine-tuning**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python evals/finetune.py
  ```

  Expected:
  ```
  Loaded 500 triplets
  Training: 3 epochs | batch=16 | warmup=XX steps
  Output:   ...\models\agroar-embeddings-v1
  Epoch 1: 100%|████████| XX/XX [XX:XX<00:00]
  Epoch 2: 100%|████████| XX/XX [XX:XX<00:00]
  Epoch 3: 100%|████████| XX/XX [XX:XX<00:00]
  Fine-tuned model saved → ...\models\agroar-embeddings-v1
  ```

- [ ] **Step 4: Verify the saved model loads**

  ```powershell
  python -c "
  from sentence_transformers import SentenceTransformer
  m = SentenceTransformer('./models/agroar-embeddings-v1')
  v = m.encode('test query', normalize_embeddings=True)
  print('Model loaded. Embedding dim:', len(v))
  "
  ```

  Expected: `Model loaded. Embedding dim: 384`

---

## Task 7: Re-Embed Corpus + Eval + Decide

**Files:**
- No new files — uses existing `ingestion/pipeline.py` and `evals/eval_runner.py`

- [ ] **Step 1: Set EMBEDDING_MODEL_PATH to fine-tuned model**

  ```powershell
  $env:EMBEDDING_MODEL_PATH = ".\models\agroar-embeddings-v1"
  ```

  Verify it's picked up:
  ```powershell
  python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(os.environ.get('EMBEDDING_MODEL_PATH', 'NOT SET'))"
  ```

  Expected: `.\models\agroar-embeddings-v1`

  > **Note:** The env var set above only persists for this PowerShell session. All commands in Steps 2-4 must run in the same session.

- [ ] **Step 2: Re-embed the full corpus with fine-tuned model**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor\ingestion
  python pipeline.py --force
  ```

  Expected (~15-30 min — 154 PDFs × ~100 chunks each):
  ```
  Found 154 PDFs.
  Processing: rice_XXX.pdf
    Upserted XXX vectors (namespace: rice)
  ...
  Done. Processed: 154, Skipped: 0, Failed: 0, Total vectors: XXXXX
  ```

- [ ] **Step 3: Run eval with fine-tuned model**

  ```powershell
  cd C:\Users\jeged\Downloads\AgroAdvisor
  python evals/eval_runner.py
  ```

  Expected: same output format as Task 4, but with `model: .\models\agroar-embeddings-v1` and (hopefully) higher scores. Result saved to `evals/results/eval_TIMESTAMP.json`.

- [ ] **Step 4: Compare baseline vs fine-tuned**

  ```powershell
  Get-ChildItem "evals\results\" | Sort-Object LastWriteTime | ForEach-Object {
      $data = Get-Content $_.FullName | ConvertFrom-Json
      Write-Host "$($_.Name): MRR@5=$($data.mrr_at_5) Hit@5=$($data.hit_at_5) model=$($data.model.Split('\')[-1])"
  }
  ```

  Expected: two lines — one for baseline, one for fine-tuned. Compare `mrr_at_5` values.

- [ ] **Step 5a: IF fine-tuned MRR@5 ≥ baseline + 0.10 → KEEP**

  ```powershell
  # Add to .env permanently so future sessions use the fine-tuned model
  Add-Content "C:\Users\jeged\Downloads\AgroAdvisor\.env" "`nEMBEDDING_MODEL_PATH=./models/agroar-embeddings-v1"
  ```

  Then restart the backend server. The query endpoint will now embed with the fine-tuned model automatically.

- [ ] **Step 5b: IF fine-tuned MRR@5 < baseline + 0.10 → ROLLBACK**

  ```powershell
  # Revert env var
  Remove-Item Env:\EMBEDDING_MODEL_PATH

  # Re-embed corpus with base model
  cd C:\Users\jeged\Downloads\AgroAdvisor\ingestion
  python pipeline.py --force
  ```

  Expected: same pipeline run, re-upserts with base model embeddings (overwrites fine-tuned vectors in Pinecone). Document the result as a finding — negative result in methodology paper is still valid evidence.

- [ ] **Step 6: Document results in CLAUDE.md**

  Add under the `## Architecture` section in `CLAUDE.md`:
  ```
  **Embedding eval results (2026-05-15):**
  - Baseline MRR@5: 0.XXXX (sentence-transformers/all-MiniLM-L6-v2)
  - Fine-tuned MRR@5: 0.XXXX (agroar-embeddings-v1, 500 triplets, 3 epochs)
  - Decision: KEPT / ROLLED BACK
  ```

---

## Self-Review

**Spec coverage:**
- ✅ EMBEDDING_MODEL_PATH env var → Task 1
- ✅ Eval set (100 items, farmer queries, chunk IDs) → Task 2
- ✅ Baseline MRR@5 measured before fine-tuning → Task 4
- ✅ Hard negatives from base model top-k → Task 5
- ✅ Eval chunk IDs excluded from training → Task 5 (eval_ids set)
- ✅ MultipleNegativesRankingLoss, 3 epochs, GPU → Task 6
- ✅ Re-embed with `--force` → Task 7
- ✅ Decision: keep or rollback based on ≥10% delta → Task 7 Steps 5a/5b
- ✅ Document results in CLAUDE.md → Task 7 Step 6

**Placeholder scan:** None found.

**Type consistency:**
- `chunk_id` (str) used consistently across generate_eval_set.py, eval_runner.py, generate_triplets.py
- `namespace` field in eval_set.jsonl matches Pinecone namespace string used in queries
- `positive_text` / `negatives[].text` in triplets.jsonl correctly consumed by finetune.py as `InputExample.texts`

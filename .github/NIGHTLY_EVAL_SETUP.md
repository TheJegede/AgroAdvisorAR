# Nightly retrieval eval — setup

This workflow runs `evals/eval_runner.py` against Pinecone every night and
appends a row to the `eval_runs` Supabase table. The admin dashboard
(`/admin`) renders the time series as a line chart.

## What the workflow does

1. Checks out the repo
2. Installs Python 3.11 + `evals/requirements.txt` + `backend/requirements.txt`
3. **Retrieval eval (always runs):** embeds every query in
   `evals/eval_set_v2.jsonl` with `thenlper/gte-base`, queries
   Pinecone top-5, computes MRR@5 + NDCG@5 + Hit@1 + Hit@5
4. **Answer eval (when `RUN_ANSWER_EVAL=1`):** samples 20 items, runs the
   full RAG chain on each (Gemini → Groq fallback), then judges each
   advisory against the gold chunk with Groq llama-3.3-70b. Average ×100
   → `answer_correct_pct`
5. Writes a single row to `public.eval_runs` containing all metrics
6. Uploads the JSON result as a workflow artifact (retained 30 days)

Trigger:
- **Scheduled:** `cron: "0 8 * * *"` → 08:00 UTC = 02:00 CST (winter) /
  03:00 CDT (summer). GitHub Actions cron ignores DST.
- **Manual:** Actions tab → "Nightly retrieval eval" → "Run workflow".

## Required GitHub secrets

Add at GitHub → repo → Settings → Secrets and variables → Actions →
"New repository secret":

**Always required (retrieval eval):**

| Name                  | Value                                                  |
|-----------------------|--------------------------------------------------------|
| `PINECONE_API_KEY`    | Same as your `.env` value                              |
| `PINECONE_INDEX_NAME` | `agroar-prod-gte-v2`                                   |
| `SUPABASE_URL`        | `https://fxncwvrplzlhrmbxvrfu.supabase.co`             |
| `SUPABASE_SERVICE_KEY`| The `sb_secret_…` key (service role — bypasses RLS)    |

**Additional secrets for answer eval (`RUN_ANSWER_EVAL=1`):**

| Name                       | Value                                                  |
|----------------------------|--------------------------------------------------------|
| `GOOGLE_API_KEY`           | Google AI Studio key (Gemini)                          |
| `GROQ_API_KEY`             | Groq key (used by judge + Gemini fallback)             |
| `SUPABASE_ANON_KEY`        | The `sb_publishable_…` key                             |
| `SUPABASE_JWT_SECRET`      | JWT secret from your `.env`                            |
| `UPSTASH_REDIS_REST_URL`   | Upstash Redis REST URL (optional but recommended)      |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis REST token (optional)                    |

Secrets are encrypted at rest and injected into the runner only when the
job runs.

## Interpreting failures

If the job fails, open the Actions tab → click the failed run → expand
"Run retrieval eval". Common causes:

- **Empty rows / no matches:** Pinecone namespace or index name mismatch.
  Verify `PINECONE_INDEX_NAME` secret matches the live index.
- **`Supabase write failed: …`:** Service key is rotated or wrong. Re-paste
  from Supabase Dashboard → Settings → API → `service_role` key.
- **`No module named …`:** `evals/requirements.txt` missing a dep. Add it,
  push, re-run.

## Why the workflow uses gte-base, not the fine-tuned one

The fine-tuned model `models/agroar-embeddings-v2/` is `.gitignored`
(~60MB, too heavy for git). GitHub Actions runners don't have it on disk,
so the workflow uses the upstream HuggingFace gte-base model. Result: the
nightly metric reflects **corpus-side drift**, not model quality.

Numbers should be interpreted as retrieval-regression checks for the current
`agroar-prod-gte-v2` corpus, not as a final answer-quality score. The point is
to catch *regressions* — e.g. if someone
re-ingests the corpus and breaks retrieval, the metric drops vs yesterday.

The `model_version` column in `eval_runs` records the exact model path used
so you can filter base-model runs separately from local fine-tuned runs in
the dashboard.

## Upgrading to fine-tuned model in CI (Option B)

Run this when you want nightly numbers to match production.

1. **Upload the fine-tuned model to HuggingFace Hub (private repo):**

   ```bash
   pip install huggingface_hub
   huggingface-cli login                   # paste your HF write token
   huggingface-cli repo create agroar-embeddings-v2 --type model --private
   cd models/agroar-embeddings-v2
   git init && git lfs install
   huggingface-cli lfs-enable-largefiles .
   git remote add origin https://huggingface.co/<YOUR_HF_USER>/agroar-embeddings-v2
   git add . && git commit -m "v2 fine-tune"
   git push origin main
   ```

2. **Add a `HF_TOKEN` secret** in GitHub (Settings → Secrets → Actions),
   set to a HuggingFace read token (HF settings → Access Tokens → "New").

3. **Edit `.github/workflows/nightly-eval.yml`:**

   ```yaml
   env:
EMBEDDING_MODEL_PATH: <YOUR_HF_USER>/agroar-embeddings-v2
     HF_TOKEN: ${{ secrets.HF_TOKEN }}
     # … other env unchanged
   ```

   `sentence-transformers` auto-downloads from the Hub when given a `user/model`
   path. With `HF_TOKEN` set, private repos work.

4. Trigger workflow manually to confirm. Expected: `model_version` rows in
   `eval_runs` switch from the base path to the HF path, MRR@5 jumps to ~0.66.

5. (Optional) Cache the model between runs to save ~1 min per job:

   ```yaml
   - name: Cache HF model
     uses: actions/cache@v4
     with:
       path: ~/.cache/huggingface
       key: hf-model-${{ env.EMBEDDING_MODEL_PATH }}-v2
   ```

## Adding a regression gate (future)

The workflow currently always succeeds. To fail CI when retrieval regresses
> 5% from the previous run, extend `evals/eval_runner.py` to look up the
prior `eval_runs` row and exit non-zero if `mrr_at_5 < prior * 0.95`.

## Local equivalent

To replicate what CI does, set the same env vars and run:

```bash
EVAL_WRITE_TO_DB=1 \
RUN_ANSWER_EVAL=1 \
EMBEDDING_MODEL_PATH=thenlper/gte-base \
PINECONE_INDEX_NAME=agroar-prod-gte-v2 \
python evals/eval_runner.py --eval-set evals/eval_set_v2.jsonl
```

By default (`EVAL_WRITE_TO_DB` unset), local runs only write to
`evals/results/`. The `eval_runs` Supabase table is left alone.

To run only the answer-eval portion (skip retrieval), invoke the script
directly:

```bash
GROQ_API_KEY=... python evals/answer_eval.py --sample 20
```

This is useful for spot-checking judge behavior or tuning the rubric
without burning a full retrieval run.

## Tuning answer eval

- `ANSWER_EVAL_SAMPLE` env var (default 20): how many eval items to sample
  per run. Lower for cost, higher for tighter confidence intervals.
- `JUDGE_MODEL` env var (default `llama-3.3-70b-versatile`): change the
  Groq judge model. Use a smaller model for cheaper-but-noisier scoring.
- The score rubric (`evals/judge.py:JUDGE_USER_TEMPLATE`) hands out
  `1.0 / 0.5 / 0.0` only. Easy to widen to a finer scale; you would then
  multiply by 100 inside `score_corpus` to keep `answer_correct_pct` in
  the same numeric(4,1) range.

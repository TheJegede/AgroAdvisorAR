# Nightly retrieval eval — setup

This workflow runs `evals/eval_runner.py` against Pinecone every night and
appends a row to the `eval_runs` Supabase table. The admin dashboard
(`/admin`) renders the time series as a line chart.

## What the workflow does

1. Checks out the repo
2. Installs Python 3.11 + `evals/requirements.txt`
3. Embeds every query in `evals/eval_set_v2.jsonl` with the base
   `sentence-transformers/all-MiniLM-L6-v2` model
4. Queries Pinecone top-5 per query, computes MRR@5 + NDCG@5 + Hit@1 + Hit@5
5. Writes one row to `public.eval_runs` (service-role key, bypasses RLS)
6. Uploads the JSON result as a workflow artifact (retained 30 days)

Trigger:
- **Scheduled:** `cron: "0 8 * * *"` → 08:00 UTC = 02:00 CST (winter) /
  03:00 CDT (summer). GitHub Actions cron ignores DST.
- **Manual:** Actions tab → "Nightly retrieval eval" → "Run workflow".

## Required GitHub secrets

Add the following at GitHub → repo → Settings → Secrets and variables →
Actions → "New repository secret":

| Name                  | Value                                                 |
|-----------------------|-------------------------------------------------------|
| `PINECONE_API_KEY`    | Same as your `.env` value                              |
| `PINECONE_INDEX_NAME` | `agroar-prod`                                          |
| `SUPABASE_URL`        | `https://fxncwvrplzlhrmbxvrfu.supabase.co`             |
| `SUPABASE_SERVICE_KEY`| The `sb_secret_…` key (service role — bypasses RLS)    |

Do not paste these into the workflow file. Secrets are encrypted at rest and
injected into the runner only when the job runs.

## Interpreting failures

If the job fails, open the Actions tab → click the failed run → expand
"Run retrieval eval". Common causes:

- **Empty rows / no matches:** Pinecone namespace or index name mismatch.
  Verify `PINECONE_INDEX_NAME` secret matches the live index.
- **`Supabase write failed: …`:** Service key is rotated or wrong. Re-paste
  from Supabase Dashboard → Settings → API → `service_role` key.
- **`No module named …`:** `evals/requirements.txt` missing a dep. Add it,
  push, re-run.

## Why the workflow uses the base model, not the fine-tuned one

The fine-tuned model `models/agroar-embeddings-v2/` is `.gitignored`
(~60MB, too heavy for git). GitHub Actions runners don't have it on disk,
so the workflow falls back to the upstream HuggingFace model. Result: the
nightly metric reflects **corpus-side drift**, not model quality.

Numbers will look low compared to production (base MRR@5 ≈ 0.17 vs v2 ≈ 0.66).
That is expected. The point is to catch *regressions* — e.g. if someone
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
EMBEDDING_MODEL_PATH=sentence-transformers/all-MiniLM-L6-v2 \
python evals/eval_runner.py --eval-set evals/eval_set_v2.jsonl
```

By default (`EVAL_WRITE_TO_DB` unset), local runs only write to
`evals/results/`. The `eval_runs` Supabase table is left alone.

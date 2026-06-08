# AgroAdvisor AR — Project Summary

**A bilingual (English / Spanish) retrieval-augmented advisory system for Arkansas farmers.**
Rice, soybean, and poultry production guidance, grounded in University of Arkansas
Cooperative Extension publications, with explicit citation verification and confidence scoring.

- **Live frontend:** https://agroadvisor-eta.vercel.app (Vercel)
- **Live backend:** https://whoisluwah-agroadvisor-backend.hf.space (Hugging Face Spaces, Docker)
- **Status:** In production, smoke-tested. ~82% production readiness. MVP target Sept 2026.
- **Last updated:** 2026-06-08

---

## 1. Motivation

Arkansas is the #1 U.S. rice producer and a major soybean and poultry state. The people who
do the work — farmers and a large Spanish-speaking farm-labor population — need fast, accurate,
*locally grounded* agronomic answers (correct products, rates, and timing for **their** county,
soil, and weather). General-purpose chatbots hallucinate rates and cite nothing, which in
agriculture means wrong pesticide doses, mistimed applications, and crop loss.

AgroAdvisor exists to close that gap with three commitments that drive every design decision:

1. **Grounded, not generative-guessing.** Every answer is retrieved from real UA Extension
   documents and citation-checked before it reaches the user. If the system cannot ground a
   claim, it says so (lowers confidence or suppresses) rather than inventing a number.
2. **Bilingual by design.** Spanish-speaking farmworkers get the same answer quality as English
   speakers, transparently.
3. **Honest about its own limits.** Evaluation numbers are reported on held-out data, not
   contaminated train-on-test metrics — including when the honest number is unflattering. This
   matters both for user safety and because the project doubles as the technical evidence base
   for a National Interest Waiver (NIW) immigration petition, where integrity of claims is
   paramount.

---

## 2. What the system is (architecture)

**Stack:** React 19 + Vite + Tailwind SPA · FastAPI backend with SSE streaming · Supabase
(Postgres + auth, JWT HS256) · Pinecone vector DB · Upstash Redis cache.

**LLM strategy (provider-transparent to the user):**
- Generation: Groq `llama-3.3-70b-versatile` (free tier) → DeepInfra Llama-3.3-70B (prod, no
  daily quota) → Gemini `gemini-2.5-flash` fallback.
- Classifier / claim-decomposition: `llama-3.1-8b-instant`.
- `local` mode (dev): Qwen2.5-7B 4-bit on GPU.

**Query flow** (`POST /api/v1/query`):
```
auth → rate limit → sanitizer → (ES only: translate query to EN)
  → classifier (picks crop namespace)
  → RAG retrieval (Pinecone top-5; SSURGO soil + NOAA/Open-Meteo weather context)
  → prompt assembly → LLM (structured output: AdvisoryResponse)
  → citation guard (LLM-as-judge groundedness)
  → (ES only: translate user-facing prose back to ES)
  → persist to Supabase → SSE stream to client
```

**Retrieval:** ~20,500 vectors, `agroar-prod-gte-v2` index (gte-base, 768-dim, 512-character
chunks, with `document_title` + `section_heading` metadata). Namespaced by crop
(`rice` / `soybeans` / `poultry`); general/cross-crop queries fan out across all three.

**Spanish = translate-bridge.** Rather than maintain a separate multilingual index, a Spanish
query is translated to English, run through the all-English pipeline (retrieval + generation +
guard), and the advisory prose is translated back to Spanish — products, rates, and citations
preserved. Validated as behaviorally identical to English-direct.

**Additional features:**
- **F2 Citation Guard v2** — claim-level groundedness scoring + confidence labels + escalation UI.
- **F3 Alerts** — GDD-based pest/disease alert engine (Rice Water Weevil, Palmer amaranth).
- **F4 Dicamba Drift tool** — 3-step wizard, Open-Meteo weather auto-fill, ReportLab PDF,
  Arkansas county choropleth.
- **F5 AWD scheduler** — alternate-wetting-drying rice irrigation scheduling with USGS well data.
- Admin dashboard + human-eval scoring queue; high-contrast / accessibility mode (WCAG 2.1 AA) with shimmering skeleton screens replacing generic loading spinners.

---

## 3. The central technical story: the guard was the bug

The most important engineering finding of the project, because it reframes every earlier metric.

**The problem:** answer correctness sat around ~40% and confidence was permanently stuck on
"Low." The natural assumption was that retrieval or generation was weak.

**The finding (2026-05-31):** a live end-to-end trace proved otherwise. Retrieval returned the
gold document in the top-5 (6/6 on-topic), and the LLM generated a *correct, grounded* answer.
The failure was the **citation guard** — specifically an NLI model (`nli-MiniLM2-L6-H768`) that
was *confidently wrong*, labeling 7 of 8 true claims as `CONTRADICTED`. The guard then hard-zeroed
the entire advisory (`confidence_score = 0.0`) and forced "Low," blanking the body.

**Implication:** every ~40%-correctness / "Low"-floor number measured while the old guard was on
was **corrupted by the guard itself.**

**The overhaul (shipped 2026-05-31, branch `guard-overhaul`, Phases 1–6, TDD):**
1. Lexical-contradiction guard — never honor a `CONTRADICTED` label when the claim shares ≥0.6
   content-token overlap with a retrieved chunk.
2. **LLM-as-judge groundedness** replaces the broken NLI (which is retired to an offline fallback).
3. **Surgical, rate-safe suppression** — drop only the contradicted claim and keep the rest;
   full-suppress *only* when a contradiction is safety-critical (touches a rate / unit / number).
4. Env-overridable thresholds.
5. Cite retrieved docs by bracketed title; scrub `Document N:` scaffolding from displayed prose.
6. Config audit — fixed local `.env` from a legacy/contaminated index to `agroar-prod-gte`.

**Effect:** suppression dropped from ~67% to ~11%; faithfulness rose to 88.9%; confidence scores
moved from a 0.0 floor to a 0.64–1.00 mean. Full backend suite passing.

---

## 4. Honest evaluation

Two integrity guardrails govern all reported numbers:

- **Eval contamination is disclosed, not hidden.** The fine-tuned retriever's reported MRR of
  **0.6565 is invalid (train-on-test memorization)**. The honest 5-fold held-out figure is ~0.18
  (base ~0.12); relevance-judged retrieval with gte+reranker is ~0.63. The 0.6565 number is
  **never** used in NIW or arXiv claims.
- **Numbers measured through the broken guard are treated as void.**

**70B production eval** (DeepInfra Llama-3.3-70B generation + judge, `agroar-prod-gte-v2`,
LLM-as-judge guard on, n=20, seed=7):

| namespace | n | suppression | correctness | faithfulness |
|---|---|---|---|---|
| poultry  | 4  | 0%  | **50%** | 50% |
| rice     | 9  | 0%  | **11%** | 44% |
| soybeans | 7  | 43% | 14%     | 29% |
| **overall** | **20** | **15%** | **20%** | **40%** |

**Namespace audit + relabeled eval (2026-06-06):** an LLM audit found 40 of 70 "soybeans" items
were actually off-crop (pine seedlings, wheat, Clearfield rice, sprayer calibration) and relabeled
them to `general`. On the corrected set (`eval_set_v2_relabeled.jsonl`, n=41, seed=7): **correctness
22%, faithfulness 49%, suppression 10%.** Soybeans, restricted to genuine soybean queries, improved
to 25% correctness / 50% faithfulness / 0% suppression — confirming the guard had been correctly
flagging mismatched off-crop retrievals, not over-suppressing.

**Reading of the numbers:** 20–22% correctness is the *honest* signal at 70B with a reliable guard;
the prior ~40% was a guard artifact. ~49% faithfulness means the model grounds in retrieved passages
about half the time. The remaining ceiling is **corpus coverage** (the precise rate/product may not
be in the corpus) and generation quality — *not* retrieval mechanics.

**Retrieval is exhausted as a lever.** Five orthogonal techniques were tested and rejected:
token-chunking (regressed, reverted), hybrid BM25 (worse), query rewrite (wash), HyDE (worse),
ms-marco reranker (regressed). The 512-character dense `gte` config wins. These are not to be
re-proposed.

---

## 5. Production & engineering rigor

- **Deployed and smoke-tested in-browser (2026-05-30):** register/login, county/soil/weather
  context, persistence, an EN rice query returning a grounded cited advisory, and the Spanish
  round-trip all verified. Frontend auto-deploys on push (Vercel, GitHub-connected); backend
  redeploys via orphan-branch force-push to the HF git remote.
- **Security & quality review (2026-06-06):** all 15 findings from a full codebase logic review
  fixed via TDD (one commit per finding). Highlights: closed an **IDOR write** in message
  persistence; fixed a safety-guard regex that over-matched and wiped grounded answers; made the
  rate limiter **fail-closed** instead of fail-open on a Redis outage; pinned the JWT algorithm
  allowlist; stopped the SSE error frame from leaking raw exceptions. Backend 131 / frontend 29
  tests passing, lint clean.
- **Testing:** pytest (backend), Vitest (frontend unit), Playwright (E2E with mocked external
  APIs), nightly answer-eval CI, Locust load-test harness, axe-core WCAG audits.
- **Documentation discipline:** `CLAUDE.md` (working guidance), `PROGRESS.md` (single source of
  "what's been tried / what's a dead end"), `docs/status-bar.md` (progress rollup), and
  **`ERRORS.md`** (symptom → cause → fix → prevention log) keep the project honest about its
  own history and prevent re-litigating settled questions.

---

## 6. What's done vs. pending

**Done:** core RAG (93%), frontend UI (99% — recently replaced loading spinners with custom-shimmering skeleton screens), deployment (95%), security/testing (80%); citation
guard overhaul; informational-query routing; Spanish translate-bridge; F2/F3/F4/F5 features;
70B prod eval; namespace audit.

**Pending (Phase 4 — Test / Pilot / NIW, ~30%):**
- Pilot: 20 farmers, 500 real queries (the major remaining evidence gap — real users 0%).
- arXiv preprint (using the honest 20%/22% 70B numbers and the guard root-cause finding).
- UA Extension agent scoring in the human-eval queue.
- NIW evidence package assembly.
- Corpus-coverage audit to lift the generation ceiling (the real next lever, not retrieval).

---

*This summary is a living document. Detailed history lives in `PROGRESS.md`; bug forensics in
`ERRORS.md`; product spec in `AgroAdvisor_AR_PRD_v2.md`.*

# AgroAdvisor AR — Completion to Production

**Last updated:** 2026-05-16  
**MVP target:** September 2026  
**Overall:** 70%

```
Overall  [██████████████░░░░░░]  70%
```

---

## By Dimension

```
Core RAG system        [███████████████████░]  93%
Frontend UI            [███████████████████░]  96%
Security / testing     [████████████████░░░░]  79%
Deployment (prod URL)  [██░░░░░░░░░░░░░░░░░░]  10%
Real users / data      [░░░░░░░░░░░░░░░░░░░░]   0%
NIW evidence package   [█░░░░░░░░░░░░░░░░░░░]   5%
```

---

## Remaining Blockers

| # | Item | Dimension affected | Delta | Done? |
|---|---|---|---|---|
| 1 | Deploy to Vercel + Railway (prod URL live) | Deployment | +7% | ☐ |
| 2 | OWASP Top 10 review + Playwright E2E suite | Security/testing | +5% | ☑ |
| 3 | 20 pilot farmers recruited + 500 real queries | Real users / data | +12% | ☐ |
| 4 | arXiv preprint submitted | NIW evidence | +6% | ☐ |
| 5 | UA Extension agent scoring in eval queue | NIW evidence | +7% | ☐ |
| 6 | Add `GROQ_API_KEY` to GH secrets (answer_correct_pct CI) | Security/testing | +1% | ☐ |
| 7 | Full WCAG audit on auth-gated routes (Playwright + axe) | Security/testing | +1% | ☑ |
| 8 | Public GitHub README (arch diagram + eval results) | NIW evidence | +2% | ☐ |
| 9 | Locust load test (50 concurrent users) | Security/testing | +1% | ☐ |

**Check off items above → update bars + overall % → update "Last updated" date.**

---

## Completed (contributed to current 70%)

| Item | Dimension | Completed |
|---|---|---|
| OWASP Top 10 audit (1 critical fixed: A07 login rate limit) | Security/testing | 2026-05-16 |
| Playwright E2E suite (15 tests across 7 spec files + CI workflow) | Security/testing | 2026-05-16 |
| Locust load test file written (local + prod run commands ready) | Security/testing | 2026-05-16 |
| Full WCAG 2.1 AA audit on 4 auth-gated routes (0 violations: /, /profile, /admin, /admin/queue) | Security/testing | 2026-05-16 |
| Supabase schema + RLS (all 6 tables) | Core RAG | 2026-05-16 |
| Pinecone index (384-dim, 20,546 vectors) | Core RAG | 2026-05-16 |
| UA Extension scraper + 200+ PDFs ingested | Core RAG | 2026-05-16 |
| Auth endpoints + JWT (ES256 JWKS + HS256) | Core RAG | 2026-05-16 |
| SSURGO + NOAA context injection (6h Redis cache) | Core RAG | 2026-05-16 |
| RAG chain (k=5, namespace filter, citation guard) | Core RAG | 2026-05-16 |
| Query classifier (Gemini Flash Lite + Groq fallback) | Core RAG | 2026-05-16 |
| Fine-tuned embeddings v2 (MRR@5 0.6565 — target >0.60 ✓) | Core RAG | 2026-05-16 |
| Nightly eval CI + `eval_runs` table | Core RAG | 2026-05-16 |
| LLM-as-judge answer eval | Core RAG | 2026-05-16 |
| Rate limit 20q/hr (Redis) + prompt injection sanitizer | Security/testing | 2026-05-16 |
| JWT audience enforcement (`aud: "authenticated"`) | Security/testing | 2026-05-16 |
| CORS locked to `CORS_ORIGINS` env var | Security/testing | 2026-05-16 |
| Backend unit tests (5 pytest) + frontend (3 vitest) | Security/testing | 2026-05-16 |
| React 19 + Vite + Tailwind frontend | Frontend UI | 2026-05-16 |
| Multi-step register wizard (3-step, EN+ES) | Frontend UI | 2026-05-16 |
| Login + forgot/reset password flow | Frontend UI | 2026-05-16 |
| Sidebar + chat pane (mobile responsive) | Frontend UI | 2026-05-16 |
| Structured response accordion renderer | Frontend UI | 2026-05-16 |
| SSE consumer | Frontend UI | 2026-05-16 |
| High-contrast mode (HC toggle, localStorage persist) | Frontend UI | 2026-05-16 |
| WCAG fixes on /login + /register (axe-core 0 violations) | Frontend UI | 2026-05-16 |
| Feedback widget + `/feedback` endpoint | Frontend UI | 2026-05-16 |
| Admin dashboard + human eval queue + scoring UI | Frontend UI | 2026-05-16 |
| AR county choropleth (react-simple-maps) | Frontend UI | 2026-05-16 |
| Session persistence + conversation history | Frontend UI | 2026-05-16 |

---

## How to Update

1. Complete a blocker item above
2. Check its box ☑
3. Add it to the Completed table with date
4. Recalculate overall % (current 63% + item delta)
5. Recount filled blocks: `round(pct / 5)` blocks out of 20
6. Update "Last updated" date
7. Update relevant dimension bar

**Block scale:** each `█` = 5%. e.g. 70% = 14 filled blocks → `[██████████████░░░░░░]`

# Load Test Summary — AgroAdvisor AR

**Tool:** Locust  
**Users:** 50 concurrent  
**Spawn rate:** 5/s  
**Duration:** 3 minutes  
**PRD target:** P95 < 8s on /query (§6.1)

## Results

| Endpoint | Run | P50 (ms) | P95 (ms) | P99 (ms) | Failure % |
|---|---|---|---|---|---|
| POST /api/v1/query | Local | — | — | — | — |
| GET /api/v1/sessions | Local | — | — | — | — |
| GET /api/v1/profile | Local | — | — | — | — |
| POST /api/v1/feedback | Local | — | — | — | — |
| POST /api/v1/query | Prod | TBD post-deploy | | | |
| GET /api/v1/sessions | Prod | TBD post-deploy | | | |
| GET /api/v1/profile | Prod | TBD post-deploy | | | |
| POST /api/v1/feedback | Prod | TBD post-deploy | | | |

## How to Run

**Local baseline (backend on :8000):**
```bash
pip install -r backend/tests/requirements-test.txt

TEST_EMAIL=playwright-test@agroar.dev TEST_PASSWORD=TestPass123! locust \
  -f backend/tests/locustfile.py \
  --host=http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 3m --headless \
  --html docs/security/locust-local.html
```

Open `docs/security/locust-local.html` in browser → read P50/P95/P99 from Response Times chart → fill table above.

**Prod run (after Railway deploy):**
```bash
TEST_EMAIL=playwright-test@agroar.dev TEST_PASSWORD=TestPass123! locust \
  -f backend/tests/locustfile.py \
  --host=https://<railway-url> \
  --users 50 --spawn-rate 5 --run-time 3m --headless \
  --html docs/security/locust-prod.html
```

## Analysis

**Bottleneck:** (fill after local run — expected: LLM API latency on /query, not backend infra)  
**PRD §6.1 target met:** (fill — P95 /query < 8000ms?)  
**Failure rate at 50 users:** (fill %)

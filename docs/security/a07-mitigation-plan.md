# OWASP A07 Mitigation Plan — Login Rate Limiting

This document outlines the threat model, architectural design, and code implementation applied to mitigate **OWASP A07:2021 — Identification and Authentication Failures** in the AgroAdvisor AR application.

---

## 1. Threat Model & Finding

### The Vulnerability
During the security audit conducted on **2026-05-16**, the login endpoint (`POST /api/v1/auth/login`) was found to have no rate limiting or brute-force protection. 

### The Threat
An attacker could perform high-speed dictionary attacks or automated brute-force attempts against any farmer's or admin's email address to compromise accounts. Because the backend connects directly to Supabase Auth (GoTrue API), unthrottled brute-forcing could also exhaust the project's API quotas, causing service disruption.

---

## 2. Design & Mitigation Strategy

To resolve this issue without introducing user friction or security disclosures:

1. **IP vs. Email-Based Limiting**: Rather than rate limiting by IP (which can block whole farming cooperatives sharing a single cellular gateway or rural satellite connection), throttling is applied per-email.
2. **PII Protection**: To prevent storing plaintext emails in the Redis cache, the email address is normalized (lowercased, stripped) and hashed using SHA-256 before acting as the Redis key.
3. **Fail-Open Resilience**: If the Upstash Redis cache becomes temporarily unreachable, the rate limiter fails open. This ensures farmers do not lose access to their crop advisories due to cache service outages (consistent with existing query throttling).
4. **Clean Error Scaffolding**: Brute-force requests are rejected with a standard `HTTP 429 Too Many Requests` code, returning a generic message and a `Retry-After` header matching the lockout duration.

---

## 3. Technical Implementation

The mitigation is fully implemented in **[auth.py](file:///c:/Users/jeged/Downloads/AgroAdvisor/backend/routers/auth.py#L101-L127)**:

```python
# backend/routers/auth.py
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    # Hash email to avoid storing PII in Redis
    email_key = hashlib.sha256(body.email.lower().encode()).hexdigest()[:24]
    
    # 10 attempts allowed per 15 minutes (900 seconds)
    allowed, _ = rate_limit_hit(f"login_throttle:{email_key}", 10, LOGIN_RATE_WINDOW)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in 15 minutes.",
            headers={"Retry-After": str(LOGIN_RATE_WINDOW)},
        )

    client = _get_anon_client()
    try:
        auth_resp = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
    ...
```

### Redis Key Lifecycle
- **Key Schema**: `login_throttle:{sha256_hash}`
- **Window**: 15 minutes (900 seconds).
- **Limit**: 10 attempts per window.

---

## 4. Testing & Verification

The rate limit is tested under **[test_review_fixes.py](file:///c:/Users/jeged/Downloads/AgroAdvisor/backend/tests/test_review_fixes.py)** to prevent regression.

### Test Coverage
The automated test case simulates multiple failed login attempts against a mock endpoint and verifies that:
1. The first 10 login requests are passed to Supabase (returning authentication results).
2. The 11th request is rejected by the FastAPI router itself, returning `HTTP 429` with `Too many login attempts` without calling the database.
3. The response contains the correct `Retry-After: 900` headers.

To execute the test:
```bash
pytest backend/tests/test_review_fixes.py -k "test_login_rate_limit"
```

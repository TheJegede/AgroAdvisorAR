import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte-v2")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH", "thenlper/gte-base"
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]
JWT_ALGORITHM = "HS256"

GEMINI_PRIMARY_MODEL = "gemini-2.5-flash"
GEMINI_CLASSIFIER_MODEL = "gemini-2.5-flash-lite"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_CLASSIFIER_MODEL = "llama-3.3-70b-versatile"
# Provider order for all LLM calls. Default groq: Gemini free tier is 20 req/day,
# Groq free is far more generous and covers a pilot. Gemini stays as fallback.
# "local" runs Qwen on a CUDA GPU with zero quota — dev/testing only (no GPU in prod).
LLM_PRIMARY = os.environ.get("LLM_PRIMARY", "groq")  # "groq" | "deepinfra" | "gemini" | "local"
GROQ_PRIMARY_MODEL = os.environ.get("GROQ_PRIMARY_MODEL", "llama-3.3-70b-versatile")
GROQ_FAST_MODEL = os.environ.get("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
LOCAL_LLM_MODEL = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
DEEPINFRA_API_KEY = os.environ.get("DEEPINFRA_API_KEY", "")
DEEPINFRA_MODEL = os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct")


ADMIN_USER_IDS: set[str] = {
    uid.strip()
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
}

SSURGO_ENDPOINT = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
NOAA_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
NOAA_CONTACT_EMAIL = os.environ.get("NOAA_CONTACT_EMAIL", "jegedetaiwo95@gmail.com")
NOAA_USER_AGENT = f"AgroAdvisor AR ({NOAA_CONTACT_EMAIL})"

DEFAULT_COUNTY_FIPS = "05055"

# Context (SSURGO/NOAA) fetch bounds. On a cache MISS the context await blocks
# generation (rag.py awaits get_context before the prompt). Cap per-call httpx
# time AND the overall gather so a slow/hanging upstream degrades to
# "unavailable" instead of stalling the answer. Budget sits above the cached
# path (~0.1s) and below the ~6s worst case (NOAA = 2 sequential GETs).
CONTEXT_FETCH_TIMEOUT = float(os.environ.get("CONTEXT_FETCH_TIMEOUT", "1.5"))
CONTEXT_BUDGET_SECONDS = float(os.environ.get("CONTEXT_BUDGET_SECONDS", "2.5"))

REDIS_TTL_SECONDS = 6 * 60 * 60  # 6 hours
RATE_LIMIT_PER_HOUR = 20
TOP_K_RETRIEVAL = 5
MAX_HISTORY_EXCHANGES = 10

# Cross-encoder reranking over dense top-N. OFF by default: bge-reranker-v2-m3 is
# ~568M params (~2.3GB RAM) and adds latency, too heavy for a free-tier CPU host.
# Enable where resources allow (GPU box / paid backend). Lifts held-out EN MRR@5
# from ~0.14 (dense) to ~0.24 in offline eval.
RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "0") not in {"0", "false", "False"}
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_CANDIDATES = int(os.environ.get("RERANK_CANDIDATES", "30"))
NLI_CITATION_GUARD_ENABLED = os.environ.get("NLI_CITATION_GUARD_ENABLED", "1") not in {
    "0",
    "false",
    "False",
}

# Groundedness judge: "llm" (default) reuses the provider chain; "nli" keeps the
# legacy CrossEncoder for offline/no-API runs.
GROUNDEDNESS_JUDGE = os.environ.get("GROUNDEDNESS_JUDGE", "llm")

# When true, the citation guard does claim-extraction AND groundedness-judging
# in ONE LLM call (judge_answer_llm) instead of two serial calls
# (decompose_claims -> judge_claims_llm). Falls back to the two-step path on any
# failure. Set false to roll back instantly without a deploy.
GUARD_MERGED_JUDGE = os.environ.get("GUARD_MERGED_JUDGE", "1") not in {"0", "false", "False"}

# Citation-guard operating thresholds (recalibrated from per-namespace eval data).
# Below ESCALATION → attach an Extension-agent escalation; below SUPPRESSION → blank
# the body (force Low). Env-overridable so calibration doesn't need a code change.
GUARD_ESCALATION_THRESHOLD = float(os.environ.get("GUARD_ESCALATION_THRESHOLD", "0.4"))
GUARD_SUPPRESSION_THRESHOLD = float(os.environ.get("GUARD_SUPPRESSION_THRESHOLD", "0.2"))

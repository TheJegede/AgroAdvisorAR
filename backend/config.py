import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2"
)
MULTILINGUAL_EMBEDDING_MODEL_PATH = os.environ.get(
    "MULTILINGUAL_EMBEDDING_MODEL_PATH", "BAAI/bge-m3"
)
PINECONE_MULTILINGUAL_INDEX_NAME = os.environ.get(
    "PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual"
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

ADMIN_USER_IDS: set[str] = {
    uid.strip()
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
}

SSURGO_ENDPOINT = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
NOAA_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
NOAA_USER_AGENT = "AgroAdvisor AR (jegedetaiwo95@gmail.com)"

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

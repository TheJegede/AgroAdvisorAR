# Backend container for Hugging Face Spaces (Docker SDK).
FROM python:3.11-slim

# System deps some wheels need (torch, sentence-transformers, pinecone, reportlab).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# HF Spaces runs as a non-root user (uid 1000); cache dirs must be writable.
ENV HF_HOME=/tmp/hf \
    SENTENCE_TRANSFORMERS_HOME=/tmp/st \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

# Install backend deps first (layer caching: deps change less often than code).
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Pre-download the embedding + NLI models at build time so cold starts are fast
# (otherwise they download on first request). Placed BEFORE `COPY backend/` so a
# backend code change doesn't bust this ~500MB layer — only a requirements.txt
# change re-downloads. Depends solely on sentence-transformers + the cache ENV.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('thenlper/gte-base'); \
CrossEncoder('cross-encoder/nli-MiniLM2-L6-H768')"

# Copy the backend source (changes most often -> kept last to preserve caches above).
COPY backend/ /app/

EXPOSE 7860
# main.py defines `app` (FastAPI). Bind 0.0.0.0:7860 for HF.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]

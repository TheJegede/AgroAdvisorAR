import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import config
from routers.auth import router as auth_router
from routers.profile import router as profile_router
from routers.query import router as query_router
from routers.sessions import router as sessions_router
from routers.feedback import router as feedback_router
from routers.admin import router as admin_router

if config.SENTRY_DSN:
    sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=0.1)

app = FastAPI(
    title="AgroAdvisor AR API",
    version="0.1.0",
    description="Arkansas Agricultural AI Advisory System",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten when frontend domain is known
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

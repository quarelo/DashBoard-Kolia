from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_database
from core.upload_limit import ImportBodyLimitMiddleware
from routers.auth import router as auth_router
from routers.dashboard import router as dashboard_router
from routers.meetings import router as meetings_router


@asynccontextmanager
async def lifespan(_app):
    init_database()
    yield


app = FastAPI(title="KOLIA Backend", lifespan=lifespan)
app.add_middleware(ImportBodyLimitMiddleware, max_bytes=5 * 1024 * 1024 + 64 * 1024)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
app.include_router(auth_router)
app.include_router(meetings_router)
app.include_router(dashboard_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "kolia-backend"}

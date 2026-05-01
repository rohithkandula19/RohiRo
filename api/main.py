"""fastapi entry. mounts every route, sets up cors, lifespan."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.memory.db import db
from api.observability.logging import log, setup_logging
from api.routes import (
    approvals,
    calendar,
    chat,
    code,
    files,
    finance,
    health,
    inbox,
    jobs,
    memory,
    research,
    settings as settings_route,
    trace,
    voice,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    log.info("ro api booting", env=settings.env)
    try:
        # warm the pool, but don't crash if postgres isn't up yet.
        try:
            await db.pg()
        except Exception as e:
            log.warning("postgres not ready at boot", error=str(e))
        yield
    finally:
        await db.close()
        log.info("ro api shutdown")


app = FastAPI(title="ro api", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(trace.router, prefix="/api/trace", tags=["trace"])
app.include_router(inbox.router, prefix="/api/inbox", tags=["inbox"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(code.router, prefix="/api/code", tags=["code"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(finance.router, prefix="/api/finance", tags=["finance"])
app.include_router(settings_route.router, prefix="/api/settings", tags=["settings"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])

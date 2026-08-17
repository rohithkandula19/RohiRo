"""fastapi entry. mounts every route, sets up cors, lifespan."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import secrets, settings
from api.eval.voice_learner import learn_voice
from api.listeners import email as email_listener, imessage as imessage_listener, telegram as telegram_listener
from api.memory.autofetch import run_once as autofetch_run_once
from api.memory.db import db
from api.memory.entities import run_extraction as entities_run
from api.memory.tree import summarize_pending
from api.observability.logging import log, setup_logging
from api.scheduler import due_now as schedules_due, fire as schedule_fire
from api.routes import (
    approvals,
    calendar,
    chat,
    code,
    eval as eval_route,
    files,
    playbooks as playbooks_route,
    push,
    finance,
    health,
    inbox,
    install,
    jobs,
    memory,
    research,
    schedules,
    settings as settings_route,
    trace,
    voice,
    webhooks,
)


async def _memory_summarizer_loop():
    """run the tree summarizer every 15 min as a background task."""
    while True:
        try:
            res = await summarize_pending(limit_hours=24)
            if res.get("hours_processed"):
                log.info("memory tree rolled up", **res)
        except Exception:
            log.exception("memory tree summarizer failed")
        await asyncio.sleep(15 * 60)


async def _scheduler_loop():
    """fire due schedules every 30s. cheap when none are due."""
    await asyncio.sleep(15)
    while True:
        try:
            due = await schedules_due()
            for s in due:
                await schedule_fire(s)
                log.info("scheduled task fired", id=s.id, title=s.title)
        except Exception:
            log.exception("scheduler loop failed")
        await asyncio.sleep(30)


async def _entity_extractor_loop():
    """every 30 min: pull recent raw_events and extract entities."""
    await asyncio.sleep(45)
    while True:
        try:
            res = await entities_run(limit=80)
            if res.get("entities_created") or res.get("entities_updated"):
                log.info("entity extractor ran", **res)
        except Exception:
            log.exception("entity extractor failed")
        await asyncio.sleep(30 * 60)


async def _voice_learner_loop():
    """re-derive learned_voice every hour. cheap when no new edits."""
    await asyncio.sleep(60)  # let the api come up first
    while True:
        try:
            res = await learn_voice()
            if res:
                log.info("voice learner updated", **res)
        except Exception:
            log.exception("voice learner failed")
        await asyncio.sleep(60 * 60)


async def _autofetch_loop():
    """poll every configured integration every 15 min; write new things into the tree."""
    # small delay so api comes up first
    await asyncio.sleep(20)
    while True:
        try:
            counts = await autofetch_run_once()
            total = sum(counts.values())
            if total:
                log.info("autofetch wrote new events", total=total, **counts)
        except Exception:
            log.exception("autofetch loop failed")
        await asyncio.sleep(15 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    log.info("ro api booting", env=settings.env)
    tasks: list[asyncio.Task] = []
    try:
        try:
            await db.pg()
        except Exception as e:
            log.warning("postgres not ready at boot", error=str(e))
        tasks.append(asyncio.create_task(_memory_summarizer_loop()))
        tasks.append(asyncio.create_task(_autofetch_loop()))
        tasks.append(asyncio.create_task(_voice_learner_loop()))
        tasks.append(asyncio.create_task(_entity_extractor_loop()))
        tasks.append(asyncio.create_task(_scheduler_loop()))
        tasks.append(asyncio.create_task(imessage_listener.loop()))
        tasks.append(asyncio.create_task(telegram_listener.loop()))
        tasks.append(asyncio.create_task(email_listener.loop()))
        yield
    finally:
        for t in tasks:
            t.cancel()
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


# bearer auth on every /api/* route when remote_secret is configured.
# unconfigured means open mode, which is only sane bound to 127.0.0.1;
# setup_remote.sh sets the secret before suggesting a wider bind.
# /webhooks/* stays out (signature-validated), /install and /health stay open.
@app.middleware("http")
async def _bearer_auth(request, call_next):
    from fastapi.responses import JSONResponse

    path = request.url.path
    if request.method != "OPTIONS" and path.startswith("/api/"):
        expected = secrets.get("remote_secret")
        if expected:
            auth = request.headers.get("authorization", "")
            given = auth.split(None, 1)[1].strip() if auth.lower().startswith("bearer ") else ""
            if given != expected:
                return JSONResponse({"detail": "missing or bad bearer token"}, status_code=401)
    return await call_next(request)


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
app.include_router(eval_route.router, prefix="/api/eval", tags=["eval"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
app.include_router(playbooks_route.router, prefix="/api/playbooks", tags=["playbooks"])
app.include_router(push.router, prefix="/api/push", tags=["push"])
app.include_router(install.router, tags=["install"])  # mounted at root (/install/ios.html)
app.include_router(webhooks.router, tags=["webhooks"])  # /webhooks/whatsapp

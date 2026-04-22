"""FastAPI application."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from netstashd.cleanup import run_cleanup
from netstashd.codes import code_store
from netstashd.config import settings
from netstashd.db import engine, init_db
from netstashd.logging import get_logger, setup_logging
from netstashd.routers import api, dashboard, stash
from netstashd.secrets import get_session_secret

log = get_logger(__name__)

cleanup_task: asyncio.Task | None = None


async def cleanup_loop():
    """Background task that runs cleanup periodically."""
    interval_seconds = settings.cleanup_interval_hours * 3600
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            log.info("Running scheduled cleanup")
            with Session(engine) as session:
                result = run_cleanup(session)
                if result.deleted_count > 0:
                    log.info(
                        f"Scheduled cleanup complete: {result.deleted_count} stashes deleted, "
                        f"{result.freed_bytes} bytes freed"
                    )

            # Also clean up expired access codes
            codes_cleaned = code_store.cleanup_expired()
            if codes_cleaned > 0:
                log.info(f"Cleaned up {codes_cleaned} expired access codes")
        except Exception as e:
            log.error(f"Cleanup task error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    global cleanup_task

    setup_logging()
    log.info("Starting netstashd")
    log.info(f"Storage root: {settings.share_root}")
    log.info(f"Global quota: {settings.global_max_bytes / (1024**3):.1f} GB")
    init_db()
    log.info("Database initialized")

    # Run startup cleanup if enabled
    if settings.cleanup_on_startup:
        log.info("Running startup cleanup")
        with Session(engine) as session:
            result = run_cleanup(session)
            if result.deleted_count > 0:
                log.info(
                    f"Startup cleanup: {result.deleted_count} stashes deleted, "
                    f"{result.freed_bytes} bytes freed"
                )
            else:
                log.info("Startup cleanup: no stashes to clean up")

    # Start background cleanup task if interval > 0
    if settings.cleanup_interval_hours > 0:
        log.info(f"Starting cleanup task (interval: {settings.cleanup_interval_hours}h)")
        cleanup_task = asyncio.create_task(cleanup_loop())

    yield

    # Cancel background task on shutdown
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    log.info("Shutting down")


app = FastAPI(
    title="netstashd",
    description="A local file sharing application for LAN use",
    version="0.1.0",
    lifespan=lifespan,
)

# Session middleware for cookies
# Note: session_secret is read at startup; rotation requires server restart
app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret(),
    session_cookie="netstashd_session",
    max_age=60 * 60 * 24 * settings.session_max_age_days,
    same_site="lax",
    https_only=False,  # Allow HTTP for LAN use
)

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Routers
app.include_router(dashboard.router)
app.include_router(stash.router)
app.include_router(api.router)

"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from netstashd.config import settings
from netstashd.db import init_db
from netstashd.logging import get_logger, setup_logging
from netstashd.routers import api, dashboard, stash
from netstashd.secrets import get_session_secret

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    setup_logging()
    log.info("Starting netstashd")
    log.info(f"Storage root: {settings.share_root}")
    log.info(f"Global quota: {settings.global_max_bytes / (1024**3):.1f} GB")
    init_db()
    log.info("Database initialized")
    yield
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

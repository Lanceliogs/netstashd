"""Dashboard routes for stash management."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from netstashd.auth import AdminRequired, add_stash_to_session, get_my_stashes, hash_password
from netstashd.cleanup import get_expired_stashes
from netstashd.codes import code_store
from netstashd.config import settings
from netstashd.logging import get_logger
from netstashd.secrets import get_admin_secret
from netstashd.db import get_session
from netstashd.models import Stash, StashCreate, StashInfo, utc_now
from netstashd.storage import ensure_stash_dir, get_dir_size, get_remaining_global_space, get_stash_path
from netstashd.templates import templates

log = get_logger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: Session = Depends(get_session)):
    """Landing page with stash ID entry and user's stashes."""
    is_admin = request.session.get("is_admin", False)
    
    # Get stashes the user has created/accessed
    my_stash_ids = get_my_stashes(request)
    my_stashes = []
    if my_stash_ids:
        for stash_id in my_stash_ids:
            stash = session.get(Stash, stash_id)
            if stash and not stash.is_expired:
                my_stashes.append(StashInfo.from_stash(stash))
    
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "is_admin": is_admin,
            "my_stashes": my_stashes,
            "guest_max_stash_size_bytes": settings.guest_max_stash_size_bytes,
            "guest_max_ttl_days": settings.guest_max_ttl_days,
            "guest_require_ttl": settings.guest_require_ttl,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Admin login page."""
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    """Process admin login."""
    if secrets.compare_digest(password, get_admin_secret()):
        request.session["is_admin"] = True
        log.info("Admin login successful")
        return RedirectResponse(url="/dashboard", status_code=303)
    log.warning("Failed admin login attempt")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid password"},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    """Clear admin session."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.post("/go")
async def go_to_stash(
    request: Request,
    stash_id: str = Form(None),
    code: str = Form(None),
):
    """Navigate to a stash by ID or temporary code."""
    # Try code first if provided
    if code and code.strip():
        code = code.strip()
        entry = code_store.lookup(code, consume=True)
        if entry:
            return RedirectResponse(url=f"/s/{entry.stash_id}", status_code=303)
        # Invalid code - redirect back with error
        return RedirectResponse(url="/?error=invalid_code", status_code=303)

    # Try stash ID
    if stash_id and stash_id.strip():
        stash_id = stash_id.strip()
        return RedirectResponse(url=f"/s/{stash_id}", status_code=303)

    # Nothing provided
    return RedirectResponse(url="/", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    _: None = AdminRequired,
):
    """Admin dashboard showing all stashes."""
    all_stashes = session.exec(select(Stash).order_by(Stash.created_at.desc())).all()

    # Separate active and expired stashes
    active_stashes = []
    expired_stashes = []

    for stash in all_stashes:
        if stash.is_expired:
            # Calculate grace period info
            grace_remaining = stash.grace_remaining(settings.expired_grace_days)
            stash_path = get_stash_path(stash.id)
            disk_size = get_dir_size(stash_path) if stash_path.exists() else 0

            expired_stashes.append({
                "info": StashInfo.from_stash(stash),
                "grace_remaining": grace_remaining,
                "grace_days_remaining": grace_remaining.days if grace_remaining else 0,
                "grace_hours_remaining": int(grace_remaining.total_seconds() // 3600) if grace_remaining else 0,
                "disk_size": disk_size,
                "past_grace": grace_remaining is not None and grace_remaining.total_seconds() <= 0,
            })
        else:
            active_stashes.append(StashInfo.from_stash(stash))

    # Sort expired by expiration date (oldest first)
    expired_stashes.sort(key=lambda x: x["info"].expires_at or datetime.min)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stashes": active_stashes,
            "expired_stashes": expired_stashes,
            "max_stash_size_bytes": settings.max_stash_size_bytes,
            "max_ttl_days": settings.max_ttl_days,
            "remaining_global_bytes": get_remaining_global_space(),
            "expired_grace_days": settings.expired_grace_days,
        },
    )


def parse_size_from_form(size: float, unit: str) -> int:
    """Convert size + unit from form to bytes."""
    unit = unit.upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }
    if unit not in multipliers:
        raise HTTPException(400, f"Invalid size unit: {unit}")
    return int(size * multipliers[unit])


@router.post("/dashboard/stash")
async def create_stash(
    request: Request,
    session: Session = Depends(get_session),
    _: None = AdminRequired,
    name: str = Form(...),
    password: str | None = Form(None),
    max_size: float = Form(...),
    size_unit: str = Form("GB"),
    ttl_days: int | None = Form(None),
):
    """Create a new stash (admin only)."""
    max_size_bytes = parse_size_from_form(max_size, size_unit)

    # Validate limits
    if max_size_bytes > settings.max_stash_size_bytes:
        raise HTTPException(400, "Exceeds maximum stash size")

    if max_size_bytes > get_remaining_global_space():
        raise HTTPException(400, "Not enough global storage space")

    if ttl_days is not None:
        if ttl_days > settings.max_ttl_days:
            raise HTTPException(400, f"TTL exceeds maximum of {settings.max_ttl_days} days")
        expires_at = utc_now() + timedelta(days=ttl_days)
    else:
        expires_at = None

    stash = Stash(
        name=name,
        password_hash=hash_password(password) if password else None,
        max_size_bytes=max_size_bytes,
        expires_at=expires_at,
    )

    ensure_stash_dir(stash.id)
    session.add(stash)
    session.commit()
    session.refresh(stash)

    log.info(f"Stash created: {stash.id} ({name}, {max_size_bytes} bytes, admin)")

    return RedirectResponse(url=f"/s/{stash.id}", status_code=303)


@router.post("/stash")
async def create_stash_public(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    password: str | None = Form(None),
    max_size: float = Form(...),
    size_unit: str = Form("MB"),
    ttl_days: int = Form(...),
):
    """Create a new stash (public/guest endpoint with restricted limits)."""
    max_size_bytes = parse_size_from_form(max_size, size_unit)

    # Validate guest limits
    if max_size_bytes > settings.guest_max_stash_size_bytes:
        raise HTTPException(
            400,
            f"Exceeds maximum guest stash size",
        )

    if max_size_bytes > get_remaining_global_space():
        raise HTTPException(400, "Not enough global storage space")

    # Guests must set a TTL
    if settings.guest_require_ttl and ttl_days < 1:
        raise HTTPException(400, "TTL is required")

    if ttl_days > settings.guest_max_ttl_days:
        raise HTTPException(400, f"TTL exceeds maximum of {settings.guest_max_ttl_days} days")

    expires_at = utc_now() + timedelta(days=ttl_days)

    stash = Stash(
        name=name,
        password_hash=hash_password(password) if password else None,
        max_size_bytes=max_size_bytes,
        expires_at=expires_at,
    )

    ensure_stash_dir(stash.id)
    session.add(stash)
    session.commit()
    session.refresh(stash)

    # Add to user's session so they can find it later
    add_stash_to_session(request, stash.id)

    log.info(f"Stash created: {stash.id} ({name}, {max_size_bytes} bytes, guest)")

    return RedirectResponse(url=f"/s/{stash.id}", status_code=303)

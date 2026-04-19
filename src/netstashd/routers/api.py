"""JSON API endpoints for CLI and JS."""

import secrets

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlmodel import Session, select

from netstashd.auth import AdminRequired
from netstashd.config import settings
from netstashd.logging import get_logger
from netstashd.secrets import (
    get_admin_secret,
    is_using_file_secret,
    rotate_admin_secret,
    rotate_session_secret,
)
from netstashd.db import get_session
from netstashd.models import FileInfo, Stash, StashInfo
from netstashd.storage import (
    get_dir_size,
    get_remaining_global_space,
    get_stash_path,
    list_directory,
    resolve_path,
)

log = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.get("/stashes", dependencies=[AdminRequired])
async def list_stashes(session: Session = Depends(get_session)) -> list[StashInfo]:
    """List all stashes (admin only)."""
    stashes = session.exec(select(Stash).order_by(Stash.created_at.desc())).all()
    return [StashInfo.from_stash(s) for s in stashes]


@router.get("/stashes/{stash_id}")
async def get_stash(
    stash_id: str,
    session: Session = Depends(get_session),
) -> StashInfo:
    """Get stash info."""
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")
    return StashInfo.from_stash(stash)


@router.get("/stashes/{stash_id}/files")
async def list_files(
    request: Request,
    stash_id: str,
    path: str = "",
    session: Session = Depends(get_session),
) -> list[FileInfo]:
    """List files in a stash directory."""
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")

    # Basic access check
    api_key = request.headers.get("x-api-key")
    if stash.is_password_protected:
        if not request.session.get("is_admin"):
            if not (api_key and secrets.compare_digest(api_key, get_admin_secret())):
                if not request.session.get(f"stash_access_{stash_id}"):
                    raise HTTPException(401, "Access denied")

    return list_directory(stash_id, path)


@router.post("/stashes/{stash_id}/upload")
async def upload_file(
    request: Request,
    stash_id: str,
    file: UploadFile,
    path: str = "",
    session: Session = Depends(get_session),
):
    """Upload a file to a stash."""
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")

    if stash.is_expired:
        raise HTTPException(410, "Stash has expired")

    # Access check
    api_key = request.headers.get("x-api-key")
    has_access = False
    if request.session.get("is_admin"):
        has_access = True
    elif api_key and secrets.compare_digest(api_key, get_admin_secret()):
        has_access = True
    elif not stash.is_password_protected:
        has_access = True
    elif request.session.get(f"stash_access_{stash_id}"):
        has_access = True

    if not has_access:
        raise HTTPException(401, "Access denied")

    # Get file size (read content-length or read file)
    content = await file.read()
    file_size = len(content)

    # Check stash quota
    if stash.used_bytes + file_size > stash.max_size_bytes:
        raise HTTPException(413, "Stash quota exceeded")

    # Check global quota
    if file_size > get_remaining_global_space():
        raise HTTPException(413, "Server storage full")

    # Write file
    base = get_stash_path(stash_id)
    target_dir = base / path if path else base
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / file.filename

    # Security check
    try:
        target_file.resolve().relative_to(base.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid path")

    async with aiofiles.open(target_file, "wb") as f:
        await f.write(content)

    # Update used bytes
    stash.used_bytes = get_dir_size(base)
    session.add(stash)
    session.commit()

    log.info(f"Uploaded {file.filename} ({file_size} bytes) to stash {stash_id}")

    return {
        "status": "uploaded",
        "filename": file.filename,
        "size": file_size,
        "used_bytes": stash.used_bytes,
    }


@router.post("/stashes/{stash_id}/mkdir")
async def create_directory(
    request: Request,
    stash_id: str,
    path: str,
    session: Session = Depends(get_session),
):
    """Create a directory in a stash."""
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")

    if stash.is_expired:
        raise HTTPException(410, "Stash has expired")

    # Access check
    api_key = request.headers.get("x-api-key")
    has_access = False
    if request.session.get("is_admin"):
        has_access = True
    elif api_key and secrets.compare_digest(api_key, get_admin_secret()):
        has_access = True
    elif not stash.is_password_protected:
        has_access = True
    elif request.session.get(f"stash_access_{stash_id}"):
        has_access = True

    if not has_access:
        raise HTTPException(401, "Access denied")

    if not path:
        raise HTTPException(400, "Path is required")

    # Create directory
    base = get_stash_path(stash_id)
    target_dir = base / path
    
    # Security check
    try:
        target_dir.resolve().relative_to(base.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid path")

    already_existed = target_dir.exists()
    target_dir.mkdir(parents=True, exist_ok=True)
    
    if not already_existed:
        log.info(f"Created directory {path} in stash {stash_id}")

    return {"status": "exists" if already_existed else "created", "path": path}


@router.get("/status")
async def status():
    """Server status endpoint."""
    return {
        "status": "ok",
        "global_max_bytes": settings.global_max_bytes,
        "remaining_bytes": get_remaining_global_space(),
    }


@router.get("/secrets/status", dependencies=[AdminRequired])
async def secrets_status():
    """Check which secrets are using file storage vs env vars."""
    return {
        "admin_secret": {
            "source": "file" if is_using_file_secret("admin_secret") else "env",
        },
        "session_secret": {
            "source": "file" if is_using_file_secret("session_secret") else "env",
        },
    }


@router.post("/secrets/rotate-api-key", dependencies=[AdminRequired])
async def api_rotate_admin_secret():
    """Rotate the admin API key. Returns the new key.
    
    The new key takes effect immediately for API requests.
    Make sure to save the returned key!
    """
    new_secret = rotate_admin_secret()
    log.info("Admin API key rotated")
    return {
        "status": "rotated",
        "new_api_key": new_secret,
        "message": "API key rotated. Save this key - you won't see it again!",
    }


@router.post("/secrets/rotate-session-secret", dependencies=[AdminRequired])
async def api_rotate_session_secret():
    """Rotate the session secret.
    
    WARNING: This invalidates ALL existing browser sessions!
    Users will need to log in again and re-authenticate to stashes.
    The server must be restarted for this to take effect.
    """
    new_secret = rotate_session_secret()
    log.warning("Session secret rotated - server restart required")
    return {
        "status": "rotated",
        "message": "Session secret rotated. Restart the server to apply. All sessions will be invalidated.",
    }

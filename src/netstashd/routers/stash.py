"""Stash browsing and file operations."""

import secrets
import shutil
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from netstashd.auth import add_stash_to_session, verify_password
from netstashd.codes import code_store
from netstashd.config import settings
from netstashd.logging import get_logger
from netstashd.secrets import get_admin_secret
from netstashd.db import get_session
from netstashd.models import Stash, StashInfo
from netstashd.storage import (
    create_zip_from_folder,
    delete_stash_dir,
    get_dir_size,
    get_stash_path,
    list_directory,
    resolve_path,
)
from netstashd.templates import templates

log = get_logger(__name__)


class BatchDeleteRequest(BaseModel):
    path: str = ""
    names: list[str]


class RenameRequest(BaseModel):
    path: str = ""
    old_name: str
    new_name: str

router = APIRouter(prefix="/s")


def get_stash_or_404(stash_id: str, session: Session) -> Stash:
    """Get a stash by ID or raise 404."""
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")
    if stash.is_expired:
        raise HTTPException(410, "Stash has expired")
    return stash


def has_stash_access(request: Request, stash: Stash) -> bool:
    """Check if request has access to stash."""
    # Admin always has access
    if request.session.get("is_admin"):
        return True

    # API key check
    api_key = request.headers.get("x-api-key")
    if api_key and secrets.compare_digest(api_key, get_admin_secret()):
        return True

    # No password required
    if not stash.is_password_protected:
        return True

    # Check stash-specific session
    return request.session.get(f"stash_access_{stash.id}", False)


@router.get("/{stash_id}", response_class=HTMLResponse)
@router.get("/{stash_id}/fs/{path:path}", response_class=HTMLResponse)
async def view_stash(
    request: Request,
    stash_id: str,
    path: str = "",
    session: Session = Depends(get_session),
):
    """View stash contents."""
    stash = get_stash_or_404(stash_id, session)

    # Check access
    if not has_stash_access(request, stash):
        return templates.TemplateResponse(
            request,
            "stash_auth.html",
            {"stash": StashInfo.from_stash(stash), "path": path},
        )

    # Track this stash in user's session so it appears in "My Stashes"
    add_stash_to_session(request, stash_id)

    # List directory
    files = list_directory(stash_id, path)

    # Build breadcrumbs
    breadcrumbs = [{"name": stash.name, "path": ""}]
    if path:
        parts = path.split("/")
        for i, part in enumerate(parts):
            breadcrumbs.append({"name": part, "path": "/".join(parts[: i + 1])})

    return templates.TemplateResponse(
        request,
        "stash.html",
        {
            "stash": StashInfo.from_stash(stash),
            "files": files,
            "path": path,
            "breadcrumbs": breadcrumbs,
            "is_admin": request.session.get("is_admin", False),
        },
    )


@router.post("/{stash_id}/auth")
async def authenticate_stash(
    request: Request,
    stash_id: str,
    password: str = Form(...),
    path: str = Form(""),
    session: Session = Depends(get_session),
):
    """Authenticate to access a password-protected stash."""
    stash = get_stash_or_404(stash_id, session)

    if stash.password_hash and verify_password(password, stash.password_hash):
        request.session[f"stash_access_{stash_id}"] = True
        # Add to user's stash list so they can find it again
        add_stash_to_session(request, stash_id)
        redirect_url = f"/s/{stash_id}/fs/{path}" if path else f"/s/{stash_id}"
        return RedirectResponse(url=redirect_url, status_code=303)

    return templates.TemplateResponse(
        request,
        "stash_auth.html",
        {"stash": StashInfo.from_stash(stash), "path": path, "error": "Invalid password"},
        status_code=401,
    )


@router.get("/{stash_id}/download/{path:path}")
async def download_file(
    request: Request,
    stash_id: str,
    path: str,
    session: Session = Depends(get_session),
):
    """Download a file."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    resolved = resolve_path(stash_id, path)
    if not resolved or not resolved.exists():
        raise HTTPException(404, "File not found")

    if resolved.is_dir():
        # ZIP download for directories
        zip_buffer = create_zip_from_folder(stash_id, path)
        filename = f"{resolved.name}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return FileResponse(
        resolved,
        filename=resolved.name,
        media_type="application/octet-stream",
    )


@router.delete("/{stash_id}", dependencies=[Depends(get_session)])
async def delete_stash(
    request: Request,
    stash_id: str,
    session: Session = Depends(get_session),
):
    """Delete a stash (admin only). Works for both active and expired stashes."""
    if not request.session.get("is_admin"):
        api_key = request.headers.get("x-api-key")
        if not api_key or not secrets.compare_digest(api_key, get_admin_secret()):
            raise HTTPException(401, "Admin access required")

    # Don't use get_stash_or_404 since it rejects expired stashes
    stash = session.get(Stash, stash_id)
    if not stash:
        raise HTTPException(404, "Stash not found")

    delete_stash_dir(stash_id)
    session.delete(stash)
    session.commit()

    log.info(f"Stash deleted: {stash_id}")

    return {"status": "deleted"}


@router.delete("/{stash_id}/file/{path:path}")
async def delete_file(
    request: Request,
    stash_id: str,
    path: str,
    session: Session = Depends(get_session),
):
    """Delete a file or folder within a stash."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    resolved = resolve_path(stash_id, path)
    if not resolved or not resolved.exists():
        raise HTTPException(404, "File not found")

    # Calculate size before deletion
    size = get_dir_size(resolved)

    if resolved.is_dir():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()

    # Update used bytes
    stash.used_bytes = max(0, stash.used_bytes - size)
    session.add(stash)
    session.commit()

    log.info(f"Deleted {path} from stash {stash_id} ({size} bytes freed)")

    return {"status": "deleted", "freed_bytes": size}


@router.get("/{stash_id}/download-batch")
async def download_batch(
    request: Request,
    stash_id: str,
    path: str = "",
    names: list[str] = Query(...),
    session: Session = Depends(get_session),
):
    """Download multiple files/folders as a ZIP."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    base = get_stash_path(stash_id)
    target_dir = base / path if path else base

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        for name in names:
            item_path = target_dir / name
            resolved = resolve_path(stash_id, f"{path}/{name}" if path else name)

            if not resolved or not resolved.exists():
                continue

            if resolved.is_file():
                zf.write(resolved, name)
            else:
                for file_path in resolved.rglob("*"):
                    if file_path.is_file():
                        arcname = f"{name}/{file_path.relative_to(resolved)}"
                        zf.write(file_path, arcname)

    buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"localshare_{timestamp}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{stash_id}/delete-batch")
async def delete_batch(
    request: Request,
    stash_id: str,
    body: BatchDeleteRequest,
    session: Session = Depends(get_session),
):
    """Delete multiple files/folders."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    base = get_stash_path(stash_id)
    total_freed = 0

    for name in body.names:
        file_path = f"{body.path}/{name}" if body.path else name
        resolved = resolve_path(stash_id, file_path)

        if not resolved or not resolved.exists():
            continue

        size = get_dir_size(resolved)

        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()

        total_freed += size

    stash.used_bytes = max(0, stash.used_bytes - total_freed)
    session.add(stash)
    session.commit()

    return {"status": "deleted", "freed_bytes": total_freed, "count": len(body.names)}


@router.post("/{stash_id}/rename")
async def rename_file(
    request: Request,
    stash_id: str,
    body: RenameRequest,
    session: Session = Depends(get_session),
):
    """Rename a file or folder."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    base = get_stash_path(stash_id)
    old_path = base / body.path / body.old_name if body.path else base / body.old_name
    new_path = base / body.path / body.new_name if body.path else base / body.new_name

    # Security checks
    try:
        old_path.resolve().relative_to(base.resolve())
        new_path.resolve().relative_to(base.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid path")

    if not old_path.exists():
        raise HTTPException(404, "File not found")

    if new_path.exists():
        raise HTTPException(400, "A file with that name already exists")

    # Validate new name
    if "/" in body.new_name or "\\" in body.new_name:
        raise HTTPException(400, "Invalid file name")

    old_path.rename(new_path)

    return {"status": "renamed", "old_name": body.old_name, "new_name": body.new_name}


@router.get("/{stash_id}/meta/{path:path}")
async def get_file_metadata(
    request: Request,
    stash_id: str,
    path: str,
    session: Session = Depends(get_session),
):
    """Get metadata for a file or folder."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    resolved = resolve_path(stash_id, path)
    if not resolved or not resolved.exists():
        raise HTTPException(404, "File not found")

    stat = resolved.stat()
    is_dir = resolved.is_dir()

    return {
        "name": resolved.name,
        "is_dir": is_dir,
        "size": get_dir_size(resolved) if is_dir else stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


@router.post("/{stash_id}/code")
async def generate_access_code(
    request: Request,
    stash_id: str,
    session: Session = Depends(get_session),
):
    """Generate a temporary 6-digit access code for this stash."""
    stash = get_stash_or_404(stash_id, session)

    if not has_stash_access(request, stash):
        raise HTTPException(401, "Access denied")

    code, expires_at = code_store.generate(stash_id)

    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": settings.code_ttl_seconds,
    }

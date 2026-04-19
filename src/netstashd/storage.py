"""File storage utilities."""

import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from netstashd.config import settings
from netstashd.models import FileInfo


def get_stash_path(stash_id: str) -> Path:
    """Get the filesystem path for a stash."""
    return settings.share_root / stash_id


def ensure_stash_dir(stash_id: str) -> Path:
    """Create and return the stash directory."""
    path = get_stash_path(stash_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_stash_dir(stash_id: str) -> None:
    """Delete a stash directory and all contents."""
    path = get_stash_path(stash_id)
    if path.exists():
        shutil.rmtree(path)


def get_dir_size(path: Path) -> int:
    """Calculate total size of a directory."""
    total = 0
    if path.is_file():
        return path.stat().st_size
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def get_total_usage() -> int:
    """Calculate total disk usage across all stashes."""
    total = 0
    if not settings.share_root.exists():
        return 0
    for entry in settings.share_root.iterdir():
        if entry.is_dir() and entry.name != "stashes.db":
            total += get_dir_size(entry)
    return total


def get_remaining_global_space() -> int:
    """Get remaining space available globally."""
    used = get_total_usage()
    return max(0, settings.usable_bytes - used)


def list_directory(stash_id: str, subpath: str = "") -> list[FileInfo]:
    """List contents of a directory within a stash."""
    base = get_stash_path(stash_id)
    target = base / subpath if subpath else base

    if not target.exists() or not target.is_dir():
        return []

    # Security: ensure we're still within the stash
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return []

    items = []
    for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        stat = entry.stat()
        items.append(
            FileInfo(
                name=entry.name,
                is_dir=entry.is_dir(),
                size=get_dir_size(entry) if entry.is_dir() else stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime),
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return items


def resolve_path(stash_id: str, subpath: str) -> Path | None:
    """Resolve a path within a stash, returning None if invalid or outside stash."""
    base = get_stash_path(stash_id)
    target = base / subpath if subpath else base

    try:
        resolved = target.resolve()
        resolved.relative_to(base.resolve())
        return resolved
    except ValueError:
        return None


def create_zip_from_folder(stash_id: str, subpath: str = "") -> BytesIO:
    """Create a ZIP archive of a folder."""
    base = get_stash_path(stash_id)
    target = base / subpath if subpath else base

    if not target.exists() or not target.is_dir():
        raise FileNotFoundError("Directory not found")

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        for file_path in target.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(target)
                zf.write(file_path, arcname)

    buffer.seek(0)
    return buffer

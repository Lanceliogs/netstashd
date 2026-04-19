"""Jinja2 template configuration."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_dir)


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_bytes_short(size: int) -> str:
    """Format bytes as short string (no decimals for large values)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            if unit in ("B", "KB"):
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# Register filters
templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["format_bytes_short"] = format_bytes_short

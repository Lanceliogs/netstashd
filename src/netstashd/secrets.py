"""Secrets management for API key and session secret rotation."""

import secrets
from pathlib import Path

from netstashd.config import settings


def get_secrets_dir() -> Path:
    """Get the secrets directory, creating it if needed."""
    secrets_dir = settings.share_root / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    return secrets_dir


def _read_secret_file(name: str) -> str | None:
    """Read a secret from file, returning None if not found."""
    secret_file = get_secrets_dir() / name
    if secret_file.exists():
        return secret_file.read_text().strip()
    return None


def _write_secret_file(name: str, value: str) -> None:
    """Write a secret to file."""
    secret_file = get_secrets_dir() / name
    secret_file.write_text(value)
    # Restrict permissions (on Unix)
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically secure random secret."""
    return secrets.token_urlsafe(length)


def get_admin_secret() -> str:
    """Get the current admin secret (API key).
    
    Priority: file > env var
    """
    file_secret = _read_secret_file("admin_secret")
    if file_secret:
        return file_secret
    return settings.admin_secret


def get_session_secret() -> str:
    """Get the current session secret.
    
    Priority: file > env var
    """
    file_secret = _read_secret_file("session_secret")
    if file_secret:
        return file_secret
    return settings.session_secret


def rotate_admin_secret() -> str:
    """Generate and save a new admin secret. Returns the new secret."""
    new_secret = generate_secret()
    _write_secret_file("admin_secret", new_secret)
    return new_secret


def rotate_session_secret() -> str:
    """Generate and save a new session secret. Returns the new secret.
    
    WARNING: This invalidates all existing sessions!
    """
    new_secret = generate_secret()
    _write_secret_file("session_secret", new_secret)
    return new_secret


def is_using_file_secret(name: str) -> bool:
    """Check if a secret is being loaded from file (vs env var)."""
    return _read_secret_file(name) is not None

"""Authentication utilities."""

import secrets as stdlib_secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request

from netstashd.secrets import get_admin_secret

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def require_admin(
    request: Request,
    x_api_key: str | None = Header(None),
) -> None:
    """Dependency that requires admin authentication.

    Accepts either:
    - X-API-Key header (for CLI)
    - Session cookie (for browser)
    """
    # Check API key header (CLI)
    if x_api_key and stdlib_secrets.compare_digest(x_api_key, get_admin_secret()):
        return

    # Check session cookie (browser)
    if request.session.get("is_admin"):
        return

    raise HTTPException(status_code=401, detail="Unauthorized")


def check_stash_access(
    request: Request,
    stash_id: str,
    x_api_key: str | None = Header(None),
) -> None:
    """Check if the request has access to a stash.

    Admin always has access. Otherwise, check stash-specific session.
    """
    # Admin has access to everything
    if x_api_key and stdlib_secrets.compare_digest(x_api_key, get_admin_secret()):
        return
    if request.session.get("is_admin"):
        return

    # Check stash-specific access
    if request.session.get(f"stash_access_{stash_id}"):
        return

    raise HTTPException(status_code=401, detail="Stash access required")


def add_stash_to_session(request: Request, stash_id: str) -> None:
    """Add a stash ID to the user's 'my_stashes' session list.
    
    Called when a user creates a stash or successfully authenticates to one.
    """
    my_stashes: list[str] = request.session.get("my_stashes", [])
    if stash_id not in my_stashes:
        my_stashes.insert(0, stash_id)  # Most recent first
        # Keep a reasonable limit
        request.session["my_stashes"] = my_stashes[:50]


def get_my_stashes(request: Request) -> list[str]:
    """Get the list of stash IDs the user has created or accessed."""
    return request.session.get("my_stashes", [])


AdminRequired = Depends(require_admin)

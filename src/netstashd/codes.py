"""Temporary access codes for easy stash sharing between devices."""

import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from netstashd.config import settings
from netstashd.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class CodeEntry:
    """A temporary access code entry."""

    stash_id: str
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def seconds_remaining(self) -> int:
        return max(0, int((self.expires_at - datetime.now(timezone.utc)).total_seconds()))


class CodeStore:
    """Thread-safe in-memory store for temporary access codes."""

    def __init__(self):
        self._codes: dict[str, CodeEntry] = {}
        self._lock = threading.Lock()

    def generate(self, stash_id: str, ttl_seconds: int | None = None) -> tuple[str, datetime]:
        """
        Generate a new 6-digit code for a stash.

        Args:
            stash_id: The stash ID to associate with the code
            ttl_seconds: Override TTL (uses config default if None)

        Returns:
            Tuple of (code, expires_at)
        """
        if ttl_seconds is None:
            ttl_seconds = settings.code_ttl_seconds

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        with self._lock:
            # Generate unique code (retry if collision)
            for _ in range(10):
                code = f"{random.randint(0, 999999):06d}"
                if code not in self._codes or self._codes[code].is_expired:
                    break
            else:
                # Extremely unlikely, but clean up and try once more
                self._cleanup_expired_locked()
                code = f"{random.randint(0, 999999):06d}"

            entry = CodeEntry(stash_id=stash_id, expires_at=expires_at)
            self._codes[code] = entry

        log.info(f"Generated code {code} for stash {stash_id[:8]}... (TTL: {ttl_seconds}s)")
        return code, expires_at

    def lookup(self, code: str, consume: bool = True) -> CodeEntry | None:
        """
        Look up a stash ID from a code.

        Args:
            code: The 6-digit code
            consume: If True, invalidate the code after lookup (single-use)

        Returns:
            CodeEntry if valid and not expired, None otherwise
        """
        # Normalize code (strip whitespace, ensure 6 digits)
        code = code.strip()
        if not code.isdigit() or len(code) != 6:
            return None

        with self._lock:
            entry = self._codes.get(code)
            if entry is None:
                return None

            if entry.is_expired:
                # Lazy cleanup
                del self._codes[code]
                return None

            # Single-use: remove code after successful lookup
            if consume:
                del self._codes[code]
                log.info(f"Code {code} consumed (single-use)")

            return entry

    def cleanup_expired(self) -> int:
        """
        Remove all expired codes.

        Returns:
            Number of codes removed
        """
        with self._lock:
            return self._cleanup_expired_locked()

    def _cleanup_expired_locked(self) -> int:
        """Internal cleanup (must hold lock)."""
        expired_codes = [code for code, entry in self._codes.items() if entry.is_expired]
        for code in expired_codes:
            del self._codes[code]

        if expired_codes:
            log.debug(f"Cleaned up {len(expired_codes)} expired access codes")

        return len(expired_codes)

    def __len__(self) -> int:
        """Return number of codes (including potentially expired ones)."""
        return len(self._codes)


# Global code store instance
code_store = CodeStore()

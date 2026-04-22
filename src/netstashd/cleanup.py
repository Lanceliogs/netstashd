"""Cleanup utilities for expired stashes."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from netstashd.config import settings
from netstashd.logging import get_logger
from netstashd.models import Stash, ensure_utc_aware
from netstashd.storage import delete_stash_dir, get_dir_size, get_stash_path

log = get_logger(__name__)

# Timezone-aware minimum datetime for sorting (avoids mixing naive/aware)
_DATETIME_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    deleted_count: int
    freed_bytes: int
    stash_ids: list[str]


def get_expired_stashes(session: Session) -> list[Stash]:
    """Get all expired stashes (in grace period, not yet cleaned up)."""
    stashes = session.exec(select(Stash)).all()
    return [s for s in stashes if s.is_expired]


def get_stashes_ready_for_cleanup(session: Session) -> list[Stash]:
    """Get stashes that have passed the grace period and should be deleted."""
    stashes = session.exec(select(Stash)).all()
    return [s for s in stashes if s.should_cleanup(settings.expired_grace_days)]


def delete_stash_completely(stash: Stash, session: Session) -> int:
    """Delete a stash's files and database entry. Returns bytes freed."""
    stash_path = get_stash_path(stash.id)
    freed_bytes = 0

    if stash_path.exists():
        freed_bytes = get_dir_size(stash_path)
        delete_stash_dir(stash.id)

    session.delete(stash)
    return freed_bytes


def _sort_by_expiration(stashes: list[Stash]) -> None:
    """Sort stashes by expiration date (oldest first), in place."""
    stashes.sort(key=lambda s: ensure_utc_aware(s.expires_at) or _DATETIME_MIN_UTC)


def _delete_stashes(
    session: Session,
    stashes: list[Stash],
    dry_run: bool,
    log_action: str,
    stop_condition: Callable[[int], bool] | None = None,
) -> CleanupResult:
    """
    Common helper to delete a list of stashes.

    Args:
        session: Database session
        stashes: Stashes to delete (will be sorted by expiration)
        dry_run: If True, don't actually delete
        log_action: Action verb for log messages (e.g., "Cleaned up", "Purged")
        stop_condition: Optional callable(total_freed) -> bool to stop early

    Returns:
        CleanupResult with statistics
    """
    _sort_by_expiration(stashes)

    deleted_ids = []
    total_freed = 0

    for stash in stashes:
        if stop_condition and stop_condition(total_freed):
            break

        stash_path = get_stash_path(stash.id)
        size = get_dir_size(stash_path) if stash_path.exists() else 0

        if dry_run:
            log.info(f"[DRY RUN] Would delete stash {stash.id} ({stash.name}), freeing {size} bytes")
            total_freed += size
        else:
            freed = delete_stash_completely(stash, session)
            log.info(f"{log_action} stash {stash.id} ({stash.name}), freed {freed} bytes")
            total_freed += freed

        deleted_ids.append(stash.id)

    if not dry_run and deleted_ids:
        session.commit()

    return CleanupResult(
        deleted_count=len(deleted_ids),
        freed_bytes=total_freed,
        stash_ids=deleted_ids,
    )


def run_cleanup(session: Session, dry_run: bool = False) -> CleanupResult:
    """
    Run automatic cleanup of stashes past their grace period.

    Args:
        session: Database session
        dry_run: If True, don't actually delete anything

    Returns:
        CleanupResult with statistics
    """
    stashes = get_stashes_ready_for_cleanup(session)

    if not stashes:
        log.info("No stashes ready for cleanup")
        return CleanupResult(deleted_count=0, freed_bytes=0, stash_ids=[])

    return _delete_stashes(session, stashes, dry_run, log_action="Cleaned up")


def free_space(session: Session, target_bytes: int, dry_run: bool = False) -> CleanupResult:
    """
    Delete oldest expired stashes until target_bytes are freed.

    Only deletes stashes that are expired (in grace period or past it).
    Oldest expired stashes are deleted first.

    Args:
        session: Database session
        target_bytes: Minimum bytes to free
        dry_run: If True, don't actually delete anything

    Returns:
        CleanupResult with statistics
    """
    expired = get_expired_stashes(session)

    if not expired:
        log.info("No expired stashes available for space reclamation")
        return CleanupResult(deleted_count=0, freed_bytes=0, stash_ids=[])

    result = _delete_stashes(
        session,
        expired,
        dry_run,
        log_action="Freed space: deleted",
        stop_condition=lambda freed: freed >= target_bytes,
    )

    if result.freed_bytes < target_bytes:
        log.warning(
            f"Could only free {result.freed_bytes} bytes, target was {target_bytes} bytes. "
            f"No more expired stashes available."
        )

    return result


def purge_all_expired(session: Session, dry_run: bool = False) -> CleanupResult:
    """
    Delete ALL expired stashes immediately, ignoring grace period.

    Args:
        session: Database session
        dry_run: If True, don't actually delete anything

    Returns:
        CleanupResult with statistics
    """
    expired = get_expired_stashes(session)

    if not expired:
        log.info("No expired stashes to purge")
        return CleanupResult(deleted_count=0, freed_bytes=0, stash_ids=[])

    return _delete_stashes(session, expired, dry_run, log_action="Purged")

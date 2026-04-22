"""Database models using SQLModel."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import BaseModel, field_validator
from sqlmodel import Field, SQLModel


def generate_uuid() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def ensure_utc_aware(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware (UTC). Handles naive datetimes from SQLite."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Stash(SQLModel, table=True):
    """A stash is a shared folder with optional password protection."""

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str = Field(index=True)
    password_hash: str | None = None
    max_size_bytes: int
    used_bytes: int = Field(default=0)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("expires_at", "created_at", mode="before")
    @classmethod
    def make_timezone_aware(cls, v: datetime | None) -> datetime | None:
        return ensure_utc_aware(v)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        expires_at = ensure_utc_aware(self.expires_at)
        return utc_now() > expires_at

    @property
    def is_password_protected(self) -> bool:
        return self.password_hash is not None

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.max_size_bytes - self.used_bytes)

    def should_cleanup(self, grace_days: int) -> bool:
        """Check if this stash should be cleaned up (expired + grace period elapsed)."""
        if self.expires_at is None:
            return False
        expires_at = ensure_utc_aware(self.expires_at)
        cleanup_after = expires_at + timedelta(days=grace_days)
        return utc_now() > cleanup_after

    def grace_remaining(self, grace_days: int) -> timedelta | None:
        """Return time remaining in grace period, or None if not expired."""
        if not self.is_expired or self.expires_at is None:
            return None
        expires_at = ensure_utc_aware(self.expires_at)
        cleanup_after = expires_at + timedelta(days=grace_days)
        remaining = cleanup_after - utc_now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)


class StashCreate(BaseModel):
    """Schema for creating a new stash."""

    name: str
    password: str | None = None
    max_size_bytes: int
    ttl_days: int | None = None


class StashInfo(BaseModel):
    """Schema for stash info returned to clients."""

    id: str
    name: str
    is_password_protected: bool
    max_size_bytes: int
    used_bytes: int
    expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_stash(cls, stash: Stash) -> "StashInfo":
        return cls(
            id=stash.id,
            name=stash.name,
            is_password_protected=stash.is_password_protected,
            max_size_bytes=stash.max_size_bytes,
            used_bytes=stash.used_bytes,
            expires_at=stash.expires_at,
            created_at=stash.created_at,
        )


class FileInfo(BaseModel):
    """Schema for file/folder info."""

    name: str
    is_dir: bool
    size: int
    created_at: datetime
    modified_at: datetime

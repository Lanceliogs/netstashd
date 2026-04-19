"""Database models using SQLModel."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def generate_uuid() -> str:
    return uuid4().hex


class Stash(SQLModel, table=True):
    """A stash is a shared folder with optional password protection."""

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str = Field(index=True)
    password_hash: str | None = None
    max_size_bytes: int
    used_bytes: int = Field(default=0)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_password_protected(self) -> bool:
        return self.password_hash is not None

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.max_size_bytes - self.used_bytes)


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

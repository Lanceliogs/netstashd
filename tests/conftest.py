"""Pytest configuration and fixtures."""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Set test environment variables before importing app
_temp_dir = tempfile.mkdtemp()
os.environ["SHARE_ROOT"] = _temp_dir
os.environ["ADMIN_SECRET"] = "test-admin-secret"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["GUEST_MAX_STASH_SIZE_BYTES"] = str(10 * 1024 * 1024)  # 10 MB for tests
os.environ["GUEST_MAX_TTL_DAYS"] = "7"
os.environ["GUEST_REQUIRE_TTL"] = "true"

from netstashd.app import app
from netstashd.db import get_session
from netstashd.models import Stash


@pytest.fixture(scope="session")
def temp_share_root() -> Path:
    """Create a temporary directory for stash storage."""
    return Path(_temp_dir)


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    with Session(db_engine) as session:
        yield session


def _make_test_client(db_engine, temp_share_root: Path) -> TestClient:
    """Helper to create a test client with proper db override."""
    
    def get_test_session():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    return TestClient(app)


@pytest.fixture
def client(db_engine, temp_share_root: Path) -> Generator[TestClient, None, None]:
    """Create a test client with overridden database session."""
    test_client = _make_test_client(db_engine, temp_share_root)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_engine, temp_share_root: Path) -> Generator[TestClient, None, None]:
    """Create a test client logged in as admin."""
    test_client = _make_test_client(db_engine, temp_share_root)
    test_client.post("/login", data={"password": "test-admin-secret"})
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def sample_stash(db_engine, temp_share_root: Path) -> Stash:
    """Create a sample stash for testing."""
    from datetime import timedelta, timezone

    from netstashd.models import utc_now

    stash = Stash(
        id="test1234567890abcdef1234567890ab",
        name="Test Stash",
        max_size_bytes=100 * 1024 * 1024,
        expires_at=utc_now() + timedelta(days=7),
    )

    with Session(db_engine) as session:
        session.add(stash)
        session.commit()
        session.refresh(stash)

    stash_dir = temp_share_root / stash.id
    stash_dir.mkdir(parents=True, exist_ok=True)

    return stash


@pytest.fixture
def password_protected_stash(db_engine, temp_share_root: Path) -> Stash:
    """Create a password-protected stash for testing."""
    from datetime import timedelta, timezone

    from netstashd.auth import hash_password
    from netstashd.models import utc_now

    stash = Stash(
        id="protectedstash1234567890abcdef",
        name="Protected Stash",
        password_hash=hash_password("secret123"),
        max_size_bytes=50 * 1024 * 1024,
        expires_at=utc_now() + timedelta(days=3),
    )

    with Session(db_engine) as session:
        session.add(stash)
        session.commit()
        session.refresh(stash)

    stash_dir = temp_share_root / stash.id
    stash_dir.mkdir(parents=True, exist_ok=True)

    return stash


@pytest.fixture
def client_with_stash(db_engine, sample_stash: Stash, temp_share_root: Path) -> Generator[TestClient, None, None]:
    """Create a test client with a sample stash already in the database."""
    test_client = _make_test_client(db_engine, temp_share_root)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_protected_stash(db_engine, password_protected_stash: Stash, temp_share_root: Path) -> Generator[TestClient, None, None]:
    """Create a test client with a password-protected stash."""
    test_client = _make_test_client(db_engine, temp_share_root)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()

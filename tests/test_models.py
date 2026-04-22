"""Tests for database models."""

from datetime import timedelta, timezone

import pytest

from netstashd.models import Stash, StashCreate, StashInfo, utc_now


class TestStash:
    """Tests for Stash model."""

    def test_stash_creation(self):
        """Test basic stash creation."""
        stash = Stash(
            name="Test Stash",
            max_size_bytes=1024 * 1024,
        )

        assert stash.name == "Test Stash"
        assert stash.max_size_bytes == 1024 * 1024
        assert stash.used_bytes == 0
        assert stash.password_hash is None
        assert stash.expires_at is None

    def test_stash_id_generated(self):
        """Test that stash ID is auto-generated."""
        stash = Stash(name="Test", max_size_bytes=1024)
        assert stash.id is not None
        assert len(stash.id) == 32  # UUID hex without dashes

    def test_is_expired_no_expiry(self):
        """Test is_expired when no expiry is set."""
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=None)
        assert stash.is_expired is False

    def test_is_expired_future(self):
        """Test is_expired when expiry is in the future."""
        future = utc_now() + timedelta(days=7)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=future)
        assert stash.is_expired is False

    def test_is_expired_past(self):
        """Test is_expired when expiry is in the past."""
        past = utc_now() - timedelta(days=1)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=past)
        assert stash.is_expired is True

    def test_is_password_protected_no_password(self):
        """Test is_password_protected when no password is set."""
        stash = Stash(name="Test", max_size_bytes=1024, password_hash=None)
        assert stash.is_password_protected is False

    def test_is_password_protected_with_password(self):
        """Test is_password_protected when password is set."""
        stash = Stash(name="Test", max_size_bytes=1024, password_hash="somehash")
        assert stash.is_password_protected is True

    def test_remaining_bytes_empty(self):
        """Test remaining_bytes when stash is empty."""
        stash = Stash(name="Test", max_size_bytes=1024, used_bytes=0)
        assert stash.remaining_bytes == 1024

    def test_remaining_bytes_partial(self):
        """Test remaining_bytes when stash is partially used."""
        stash = Stash(name="Test", max_size_bytes=1024, used_bytes=300)
        assert stash.remaining_bytes == 724

    def test_remaining_bytes_full(self):
        """Test remaining_bytes when stash is full."""
        stash = Stash(name="Test", max_size_bytes=1024, used_bytes=1024)
        assert stash.remaining_bytes == 0

    def test_remaining_bytes_overflow(self):
        """Test remaining_bytes when used exceeds max (edge case)."""
        stash = Stash(name="Test", max_size_bytes=1024, used_bytes=2000)
        assert stash.remaining_bytes == 0

    def test_should_cleanup_not_expired(self):
        """Test should_cleanup when stash is not expired."""
        future = utc_now() + timedelta(days=7)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=future)
        assert stash.should_cleanup(grace_days=7) is False

    def test_should_cleanup_no_expiry(self):
        """Test should_cleanup when stash has no expiry."""
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=None)
        assert stash.should_cleanup(grace_days=7) is False

    def test_should_cleanup_within_grace(self):
        """Test should_cleanup when expired but within grace period."""
        # Expired 3 days ago, grace period is 7 days
        past = utc_now() - timedelta(days=3)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=past)
        assert stash.should_cleanup(grace_days=7) is False

    def test_should_cleanup_past_grace(self):
        """Test should_cleanup when past grace period."""
        # Expired 10 days ago, grace period is 7 days
        past = utc_now() - timedelta(days=10)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=past)
        assert stash.should_cleanup(grace_days=7) is True

    def test_grace_remaining_not_expired(self):
        """Test grace_remaining when stash is not expired."""
        future = utc_now() + timedelta(days=7)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=future)
        assert stash.grace_remaining(grace_days=7) is None

    def test_grace_remaining_no_expiry(self):
        """Test grace_remaining when stash has no expiry."""
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=None)
        assert stash.grace_remaining(grace_days=7) is None

    def test_grace_remaining_within_grace(self):
        """Test grace_remaining when within grace period."""
        # Expired 3 days ago, grace period is 7 days -> 4 days remaining
        past = utc_now() - timedelta(days=3)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=past)
        remaining = stash.grace_remaining(grace_days=7)

        assert remaining is not None
        # Should be approximately 4 days
        assert 3.9 <= remaining.total_seconds() / 86400 <= 4.1

    def test_grace_remaining_past_grace(self):
        """Test grace_remaining when past grace period."""
        # Expired 10 days ago, grace period is 7 days
        past = utc_now() - timedelta(days=10)
        stash = Stash(name="Test", max_size_bytes=1024, expires_at=past)
        remaining = stash.grace_remaining(grace_days=7)

        assert remaining is not None
        assert remaining.total_seconds() == 0


class TestStashCreate:
    """Tests for StashCreate schema."""

    def test_stash_create_minimal(self):
        """Test StashCreate with minimal fields."""
        data = StashCreate(name="Test", max_size_bytes=1024)
        assert data.name == "Test"
        assert data.max_size_bytes == 1024
        assert data.password is None
        assert data.ttl_days is None

    def test_stash_create_full(self):
        """Test StashCreate with all fields."""
        data = StashCreate(
            name="Full Test",
            password="secret",
            max_size_bytes=2048,
            ttl_days=7,
        )
        assert data.name == "Full Test"
        assert data.password == "secret"
        assert data.max_size_bytes == 2048
        assert data.ttl_days == 7


class TestStashInfo:
    """Tests for StashInfo schema."""

    def test_from_stash(self):
        """Test creating StashInfo from Stash."""
        stash = Stash(
            id="abc123",
            name="Test",
            max_size_bytes=1024,
            used_bytes=512,
            password_hash="somehash",
        )

        info = StashInfo.from_stash(stash)

        assert info.id == "abc123"
        assert info.name == "Test"
        assert info.max_size_bytes == 1024
        assert info.used_bytes == 512
        assert info.is_password_protected is True

    def test_from_stash_no_password(self):
        """Test creating StashInfo from Stash without password."""
        stash = Stash(
            id="xyz789",
            name="Public",
            max_size_bytes=2048,
            password_hash=None,
        )

        info = StashInfo.from_stash(stash)

        assert info.is_password_protected is False

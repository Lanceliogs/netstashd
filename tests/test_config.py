"""Tests for configuration module."""

import pytest

from netstashd.config import Settings, parse_size


class TestParseSize:
    """Tests for human-readable size parsing."""

    def test_parse_bytes_int(self):
        """Test parsing raw integer bytes."""
        assert parse_size(1024) == 1024
        assert parse_size(0) == 0

    def test_parse_bytes_string(self):
        """Test parsing numeric string."""
        assert parse_size("1024") == 1024

    def test_parse_kb(self):
        """Test parsing kilobytes."""
        assert parse_size("1KB") == 1024
        assert parse_size("1kb") == 1024
        assert parse_size("1 KB") == 1024
        assert parse_size("2KB") == 2048

    def test_parse_mb(self):
        """Test parsing megabytes."""
        assert parse_size("1MB") == 1024 * 1024
        assert parse_size("100MB") == 100 * 1024 * 1024
        assert parse_size("100 mb") == 100 * 1024 * 1024

    def test_parse_gb(self):
        """Test parsing gigabytes."""
        assert parse_size("1GB") == 1024 ** 3
        assert parse_size("5GB") == 5 * 1024 ** 3
        assert parse_size("10 GB") == 10 * 1024 ** 3

    def test_parse_tb(self):
        """Test parsing terabytes."""
        assert parse_size("1TB") == 1024 ** 4

    def test_parse_decimal(self):
        """Test parsing decimal values."""
        assert parse_size("1.5GB") == int(1.5 * 1024 ** 3)
        assert parse_size("0.5MB") == int(0.5 * 1024 ** 2)

    def test_parse_invalid(self):
        """Test invalid size strings raise ValueError."""
        with pytest.raises(ValueError):
            parse_size("invalid")
        with pytest.raises(ValueError):
            parse_size("10XB")
        with pytest.raises(ValueError):
            parse_size("GB10")


class TestSettings:
    """Tests for Settings class."""

    def test_default_settings(self):
        """Test default settings values."""
        s = Settings(
            admin_secret="test",
            session_secret="test-session",
        )

        assert s.global_max_bytes == 10 * 1024 * 1024 * 1024
        assert s.reserve_bytes == 500 * 1024 * 1024
        assert s.max_stash_size_bytes == 5 * 1024 * 1024 * 1024
        assert s.max_ttl_days == 30

    def test_human_readable_sizes(self):
        """Test settings accept human-readable sizes."""
        s = Settings(
            admin_secret="test",
            session_secret="test-session",
            global_max_bytes="20GB",
            reserve_bytes="1GB",
            max_stash_size_bytes="2.5GB",
            guest_max_stash_size_bytes="50MB",
        )

        assert s.global_max_bytes == 20 * 1024 ** 3
        assert s.reserve_bytes == 1024 ** 3
        assert s.max_stash_size_bytes == int(2.5 * 1024 ** 3)
        assert s.guest_max_stash_size_bytes == 50 * 1024 ** 2

    def test_guest_settings(self):
        """Test guest-specific settings with explicit values."""
        s = Settings(
            admin_secret="test",
            session_secret="test-session",
            guest_max_stash_size_bytes="100MB",
            guest_max_ttl_days=7,
            guest_require_ttl=True,
        )

        assert s.guest_max_stash_size_bytes == 100 * 1024 * 1024
        assert s.guest_max_ttl_days == 7
        assert s.guest_require_ttl is True

    def test_custom_guest_settings(self):
        """Test custom guest settings."""
        s = Settings(
            admin_secret="test",
            session_secret="test-session",
            guest_max_stash_size_bytes="50MB",
            guest_max_ttl_days=3,
            guest_require_ttl=False,
        )

        assert s.guest_max_stash_size_bytes == 50 * 1024 * 1024
        assert s.guest_max_ttl_days == 3
        assert s.guest_require_ttl is False

    def test_usable_bytes(self):
        """Test usable_bytes property."""
        s = Settings(
            admin_secret="test",
            session_secret="test-session",
            global_max_bytes="10GB",
            reserve_bytes="500MB",
        )

        expected = (10 * 1024 ** 3) - (500 * 1024 ** 2)
        assert s.usable_bytes == expected

    def test_db_path(self):
        """Test db_path property."""
        from pathlib import Path

        s = Settings(
            admin_secret="test",
            session_secret="test-session",
            share_root="/data/stashes",
        )

        expected = Path("/data/stashes") / "stashes.db"
        assert s.db_path == expected

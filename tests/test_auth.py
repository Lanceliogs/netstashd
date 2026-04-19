"""Tests for authentication module."""

from unittest.mock import MagicMock

import pytest

from netstashd.auth import (
    add_stash_to_session,
    get_my_stashes,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        result = hash_password("mypassword")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_password_different_each_time(self):
        """Test that same password produces different hashes (salted)."""
        hash1 = hash_password("mypassword")
        hash2 = hash_password("mypassword")
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test that correct password verifies."""
        password = "secretpassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test that incorrect password fails verification."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        """Test verification with empty password."""
        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False


class TestSessionHelpers:
    """Tests for session management helpers."""

    def test_get_my_stashes_empty(self):
        """Test getting stashes from empty session."""
        request = MagicMock()
        request.session = {}

        result = get_my_stashes(request)
        assert result == []

    def test_get_my_stashes_with_data(self):
        """Test getting stashes from session with data."""
        request = MagicMock()
        request.session = {"my_stashes": ["stash1", "stash2"]}

        result = get_my_stashes(request)
        assert result == ["stash1", "stash2"]

    def test_add_stash_to_session_new(self):
        """Test adding a stash to empty session."""
        request = MagicMock()
        request.session = {}

        add_stash_to_session(request, "newstash123")

        assert request.session["my_stashes"] == ["newstash123"]

    def test_add_stash_to_session_existing(self):
        """Test adding a stash to session with existing stashes."""
        request = MagicMock()
        request.session = {"my_stashes": ["oldstash"]}

        add_stash_to_session(request, "newstash")

        # New stash should be first (most recent)
        assert request.session["my_stashes"] == ["newstash", "oldstash"]

    def test_add_stash_to_session_no_duplicates(self):
        """Test that duplicate stash IDs are not added."""
        request = MagicMock()
        request.session = {"my_stashes": ["stash1", "stash2"]}

        add_stash_to_session(request, "stash1")

        # Should not duplicate
        assert request.session["my_stashes"] == ["stash1", "stash2"]

    def test_add_stash_to_session_limit(self):
        """Test that session list is limited to 50 stashes."""
        request = MagicMock()
        existing = [f"stash{i}" for i in range(50)]
        request.session = {"my_stashes": existing}

        add_stash_to_session(request, "newstash")

        # Should have 50 items with new one first
        assert len(request.session["my_stashes"]) == 50
        assert request.session["my_stashes"][0] == "newstash"
        assert "stash49" not in request.session["my_stashes"]

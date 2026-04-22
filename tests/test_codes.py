"""Tests for temporary access codes."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from netstashd.codes import CodeEntry, CodeStore


class TestCodeEntry:
    """Tests for CodeEntry dataclass."""

    def test_code_entry_creation(self):
        """Test basic CodeEntry creation."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        entry = CodeEntry(stash_id="abc123", expires_at=expires_at)

        assert entry.stash_id == "abc123"
        assert entry.expires_at == expires_at

    def test_code_entry_is_frozen(self):
        """Test that CodeEntry is immutable."""
        entry = CodeEntry(stash_id="abc123", expires_at=datetime.now(timezone.utc))

        with pytest.raises(AttributeError):
            entry.stash_id = "changed"

    def test_is_expired_future(self):
        """Test is_expired when expiry is in the future."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        entry = CodeEntry(stash_id="abc123", expires_at=expires_at)

        assert entry.is_expired is False

    def test_is_expired_past(self):
        """Test is_expired when expiry is in the past."""
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        entry = CodeEntry(stash_id="abc123", expires_at=expires_at)

        assert entry.is_expired is True

    def test_seconds_remaining_future(self):
        """Test seconds_remaining when time remains."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        entry = CodeEntry(stash_id="abc123", expires_at=expires_at)

        remaining = entry.seconds_remaining
        assert 28 <= remaining <= 30

    def test_seconds_remaining_past(self):
        """Test seconds_remaining when expired."""
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        entry = CodeEntry(stash_id="abc123", expires_at=expires_at)

        assert entry.seconds_remaining == 0


class TestCodeStore:
    """Tests for CodeStore class."""

    @pytest.fixture
    def store(self):
        """Create a fresh CodeStore for each test."""
        return CodeStore()

    def test_generate_returns_code_and_expiry(self, store: CodeStore):
        """Test that generate returns code and expiry time."""
        code, expires_at = store.generate("stash123", ttl_seconds=60)

        assert len(code) == 6
        assert code.isdigit()
        assert isinstance(expires_at, datetime)
        assert expires_at > datetime.now(timezone.utc)

    def test_generate_code_format(self, store: CodeStore):
        """Test that generated codes are 6 digits with leading zeros preserved."""
        codes = set()
        for _ in range(100):
            code, _ = store.generate("stash123", ttl_seconds=60)
            assert len(code) == 6
            assert code.isdigit()
            codes.add(code)

        # Should generate different codes (not all the same)
        assert len(codes) > 1

    def test_lookup_valid_code(self, store: CodeStore):
        """Test looking up a valid code."""
        code, _ = store.generate("stash123", ttl_seconds=60)

        entry = store.lookup(code)

        assert entry is not None
        assert entry.stash_id == "stash123"
        assert entry.is_expired is False

    def test_lookup_single_use(self, store: CodeStore):
        """Test that codes are single-use by default."""
        code, _ = store.generate("stash123", ttl_seconds=60)

        # First lookup succeeds
        entry1 = store.lookup(code)
        assert entry1 is not None

        # Second lookup fails (code consumed)
        entry2 = store.lookup(code)
        assert entry2 is None

    def test_lookup_without_consume(self, store: CodeStore):
        """Test lookup with consume=False keeps the code."""
        code, _ = store.generate("stash123", ttl_seconds=60)

        # Lookup without consuming
        entry1 = store.lookup(code, consume=False)
        assert entry1 is not None

        # Code should still work
        entry2 = store.lookup(code, consume=False)
        assert entry2 is not None

    def test_lookup_invalid_code(self, store: CodeStore):
        """Test looking up an invalid code."""
        entry = store.lookup("999999")

        assert entry is None

    def test_lookup_expired_code(self, store: CodeStore):
        """Test looking up an expired code."""
        code, _ = store.generate("stash123", ttl_seconds=1)

        # Wait for expiry
        time.sleep(1.1)

        entry = store.lookup(code)
        assert entry is None

    def test_lookup_normalizes_code(self, store: CodeStore):
        """Test that lookup handles whitespace."""
        code, _ = store.generate("stash123", ttl_seconds=60)

        # Lookup with whitespace
        entry = store.lookup(f"  {code}  ")
        assert entry is not None
        assert entry.stash_id == "stash123"

    def test_lookup_rejects_invalid_format(self, store: CodeStore):
        """Test that lookup rejects non-6-digit codes."""
        assert store.lookup("12345") is None  # Too short
        assert store.lookup("1234567") is None  # Too long
        assert store.lookup("abcdef") is None  # Not digits
        assert store.lookup("12345a") is None  # Contains letter

    def test_cleanup_expired_removes_old_codes(self, store: CodeStore):
        """Test that cleanup removes expired codes."""
        # Generate a code that expires immediately
        code, _ = store.generate("stash123", ttl_seconds=0)

        # Small sleep to ensure it's expired
        time.sleep(0.1)

        removed = store.cleanup_expired()

        assert removed >= 1
        assert store.lookup(code) is None

    def test_cleanup_expired_keeps_valid_codes(self, store: CodeStore):
        """Test that cleanup keeps non-expired codes."""
        code, _ = store.generate("stash123", ttl_seconds=60)

        removed = store.cleanup_expired()

        assert removed == 0
        # Use consume=False to just check existence without consuming
        assert store.lookup(code, consume=False) is not None

    def test_multiple_codes_same_stash(self, store: CodeStore):
        """Test generating multiple codes for the same stash."""
        code1, _ = store.generate("stash123", ttl_seconds=60)
        code2, _ = store.generate("stash123", ttl_seconds=60)

        assert code1 != code2  # Different codes

        # Both codes should work (lookup without consuming to test both)
        entry1 = store.lookup(code1, consume=False)
        entry2 = store.lookup(code2, consume=False)

        assert entry1 is not None
        assert entry2 is not None
        assert entry1.stash_id == entry2.stash_id == "stash123"

    def test_len(self, store: CodeStore):
        """Test that __len__ returns code count."""
        assert len(store) == 0

        store.generate("stash1", ttl_seconds=60)
        assert len(store) == 1

        store.generate("stash2", ttl_seconds=60)
        assert len(store) == 2


class TestCodeRoutes:
    """Tests for access code HTTP routes."""

    def test_generate_code_for_stash(self, client_with_stash, sample_stash):
        """Test generating a code for a stash."""
        response = client_with_stash.post(f"/s/{sample_stash.id}/code")

        assert response.status_code == 200
        data = response.json()
        assert "code" in data
        assert len(data["code"]) == 6
        assert data["code"].isdigit()
        assert "expires_at" in data
        assert "ttl_seconds" in data

    def test_generate_code_nonexistent_stash(self, client):
        """Test generating code for nonexistent stash."""
        response = client.post("/s/nonexistent1234567890abcdef12/code")
        assert response.status_code == 404

    def test_go_endpoint_with_code(self, client_with_stash, sample_stash):
        """Test the /go endpoint with a valid code."""
        # Generate a code
        gen_response = client_with_stash.post(f"/s/{sample_stash.id}/code")
        code = gen_response.json()["code"]

        # Use the /go endpoint
        response = client_with_stash.post(
            "/go",
            data={"code": code},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/s/{sample_stash.id}"

    def test_go_endpoint_with_invalid_code(self, client):
        """Test the /go endpoint with an invalid code."""
        response = client.post(
            "/go",
            data={"code": "999999"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=invalid_code" in response.headers["location"]

    def test_go_endpoint_with_stash_id(self, client_with_stash, sample_stash):
        """Test the /go endpoint with a stash ID."""
        response = client_with_stash.post(
            "/go",
            data={"stash_id": sample_stash.id},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/s/{sample_stash.id}"

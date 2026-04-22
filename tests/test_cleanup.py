"""Tests for stash cleanup functionality."""

from datetime import timedelta, timezone

import pytest
from sqlmodel import Session

from netstashd.cleanup import (
    CleanupResult,
    delete_stash_completely,
    free_space,
    get_expired_stashes,
    get_stashes_ready_for_cleanup,
    purge_all_expired,
    run_cleanup,
)
from netstashd.models import Stash, utc_now
from netstashd.storage import ensure_stash_dir, get_stash_path


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_cleanup_result_creation(self):
        """Test CleanupResult creation."""
        result = CleanupResult(
            deleted_count=5,
            freed_bytes=1024,
            stash_ids=["abc", "def"],
        )

        assert result.deleted_count == 5
        assert result.freed_bytes == 1024
        assert result.stash_ids == ["abc", "def"]


class TestGetExpiredStashes:
    """Tests for get_expired_stashes function."""

    def test_no_expired_stashes(self, db_session: Session):
        """Test when there are no expired stashes."""
        # Create a non-expired stash
        stash = Stash(
            name="Active",
            max_size_bytes=1024,
            expires_at=utc_now() + timedelta(days=7),
        )
        db_session.add(stash)
        db_session.commit()

        expired = get_expired_stashes(db_session)
        assert len(expired) == 0

    def test_finds_expired_stashes(self, db_session: Session):
        """Test finding expired stashes."""
        # Create an expired stash
        expired_stash = Stash(
            name="Expired",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=1),
        )
        # Create a non-expired stash
        active_stash = Stash(
            name="Active",
            max_size_bytes=1024,
            expires_at=utc_now() + timedelta(days=7),
        )
        db_session.add_all([expired_stash, active_stash])
        db_session.commit()

        expired = get_expired_stashes(db_session)

        assert len(expired) == 1
        assert expired[0].name == "Expired"

    def test_immortal_stash_not_expired(self, db_session: Session):
        """Test that stash with no expiry is not considered expired."""
        stash = Stash(
            name="Immortal",
            max_size_bytes=1024,
            expires_at=None,
        )
        db_session.add(stash)
        db_session.commit()

        expired = get_expired_stashes(db_session)
        assert len(expired) == 0


class TestGetStashesReadyForCleanup:
    """Tests for get_stashes_ready_for_cleanup function."""

    def test_expired_within_grace_period(self, db_session: Session):
        """Test that recently expired stashes are not ready for cleanup."""
        # Expired 1 day ago (within default 7-day grace)
        stash = Stash(
            name="Recently Expired",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=1),
        )
        db_session.add(stash)
        db_session.commit()

        ready = get_stashes_ready_for_cleanup(db_session)
        assert len(ready) == 0

    def test_expired_past_grace_period(self, db_session: Session):
        """Test that old expired stashes are ready for cleanup."""
        # Expired 10 days ago (past default 7-day grace)
        stash = Stash(
            name="Old Expired",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=10),
        )
        db_session.add(stash)
        db_session.commit()

        ready = get_stashes_ready_for_cleanup(db_session)
        assert len(ready) == 1
        assert ready[0].name == "Old Expired"


class TestDeleteStashCompletely:
    """Tests for delete_stash_completely function."""

    def test_deletes_stash_and_files(self, db_session: Session, temp_share_root):
        """Test that stash and files are deleted."""
        stash = Stash(
            name="To Delete",
            max_size_bytes=1024,
        )
        db_session.add(stash)
        db_session.commit()

        # Create the stash directory
        stash_dir = ensure_stash_dir(stash.id)
        (stash_dir / "test.txt").write_text("hello")

        assert stash_dir.exists()

        freed = delete_stash_completely(stash, db_session)
        db_session.commit()

        # Files should be gone
        assert not stash_dir.exists()
        # DB entry should be gone
        assert db_session.get(Stash, stash.id) is None
        # Should report freed bytes
        assert freed > 0

    def test_deletes_stash_without_files(self, db_session: Session):
        """Test deleting stash when directory doesn't exist."""
        stash = Stash(
            name="No Files",
            max_size_bytes=1024,
        )
        db_session.add(stash)
        db_session.commit()

        freed = delete_stash_completely(stash, db_session)
        db_session.commit()

        assert freed == 0
        assert db_session.get(Stash, stash.id) is None


class TestRunCleanup:
    """Tests for run_cleanup function."""

    def test_cleanup_deletes_old_expired(self, db_session: Session, temp_share_root):
        """Test that cleanup deletes stashes past grace period."""
        # Old expired stash (10 days past expiry)
        old_stash = Stash(
            name="Old",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=10),
        )
        db_session.add(old_stash)
        db_session.commit()
        ensure_stash_dir(old_stash.id)

        result = run_cleanup(db_session)

        assert result.deleted_count == 1
        assert old_stash.id in result.stash_ids
        assert db_session.get(Stash, old_stash.id) is None

    def test_cleanup_keeps_recent_expired(self, db_session: Session, temp_share_root):
        """Test that cleanup keeps recently expired stashes."""
        # Recently expired stash (1 day past expiry, within grace)
        recent_stash = Stash(
            name="Recent",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=1),
        )
        db_session.add(recent_stash)
        db_session.commit()
        ensure_stash_dir(recent_stash.id)

        result = run_cleanup(db_session)

        assert result.deleted_count == 0
        assert db_session.get(Stash, recent_stash.id) is not None

    def test_cleanup_dry_run(self, db_session: Session, temp_share_root):
        """Test cleanup dry run doesn't delete anything."""
        old_stash = Stash(
            name="Old",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=10),
        )
        db_session.add(old_stash)
        db_session.commit()
        stash_dir = ensure_stash_dir(old_stash.id)

        result = run_cleanup(db_session, dry_run=True)

        assert result.deleted_count == 1
        assert old_stash.id in result.stash_ids
        # But stash should still exist
        db_session.refresh(old_stash)
        assert db_session.get(Stash, old_stash.id) is not None
        assert stash_dir.exists()


class TestFreeSpace:
    """Tests for free_space function."""

    def test_frees_target_space(self, db_session: Session, temp_share_root):
        """Test that free_space deletes oldest expired stashes."""
        # Create expired stashes with files
        stash1 = Stash(
            name="Oldest",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=5),
        )
        stash2 = Stash(
            name="Newer",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=2),
        )
        db_session.add_all([stash1, stash2])
        db_session.commit()

        # Create files
        dir1 = ensure_stash_dir(stash1.id)
        (dir1 / "file.txt").write_bytes(b"x" * 100)

        dir2 = ensure_stash_dir(stash2.id)
        (dir2 / "file.txt").write_bytes(b"x" * 100)

        # Free 50 bytes - should delete oldest first
        result = free_space(db_session, target_bytes=50)

        assert result.deleted_count >= 1
        assert result.freed_bytes >= 50

    def test_free_space_no_expired(self, db_session: Session):
        """Test free_space when no expired stashes exist."""
        active_stash = Stash(
            name="Active",
            max_size_bytes=1024,
            expires_at=utc_now() + timedelta(days=7),
        )
        db_session.add(active_stash)
        db_session.commit()

        result = free_space(db_session, target_bytes=1000)

        assert result.deleted_count == 0
        assert result.freed_bytes == 0


class TestPurgeAllExpired:
    """Tests for purge_all_expired function."""

    def test_purges_all_expired(self, db_session: Session, temp_share_root):
        """Test that purge deletes all expired stashes."""
        # Create expired stashes (both recent and old)
        recent = Stash(
            name="Recent",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=1),
        )
        old = Stash(
            name="Old",
            max_size_bytes=1024,
            expires_at=utc_now() - timedelta(days=10),
        )
        active = Stash(
            name="Active",
            max_size_bytes=1024,
            expires_at=utc_now() + timedelta(days=7),
        )
        db_session.add_all([recent, old, active])
        db_session.commit()

        ensure_stash_dir(recent.id)
        ensure_stash_dir(old.id)
        ensure_stash_dir(active.id)

        result = purge_all_expired(db_session)

        assert result.deleted_count == 2
        assert db_session.get(Stash, recent.id) is None
        assert db_session.get(Stash, old.id) is None
        # Active should remain
        assert db_session.get(Stash, active.id) is not None


class TestCleanupRoutes:
    """Tests for cleanup HTTP routes."""

    def test_list_expired_requires_admin(self, client):
        """Test that listing expired stashes requires admin."""
        response = client.get("/api/stashes/expired")
        assert response.status_code == 401

    def test_list_expired_with_admin(self, admin_client):
        """Test listing expired stashes as admin."""
        response = admin_client.get("/api/stashes/expired")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_cleanup_endpoint_requires_admin(self, client):
        """Test that cleanup endpoint requires admin."""
        response = client.post("/api/cleanup")
        assert response.status_code == 401

    def test_cleanup_endpoint_with_admin(self, admin_client):
        """Test cleanup endpoint as admin."""
        response = admin_client.post("/api/cleanup")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert "freed_bytes" in data

    def test_cleanup_dry_run(self, admin_client):
        """Test cleanup endpoint with dry_run."""
        response = admin_client.post("/api/cleanup?dry_run=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dry_run"

    def test_purge_expired_endpoint(self, admin_client):
        """Test purge expired endpoint."""
        response = admin_client.post("/api/cleanup/purge-expired")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data

    def test_free_space_endpoint(self, admin_client):
        """Test free space endpoint."""
        response = admin_client.post(
            "/api/cleanup/free-space",
            json={"target_bytes": 1024},
        )
        assert response.status_code == 200
        data = response.json()
        assert "freed_bytes" in data
        assert data["target_bytes"] == 1024

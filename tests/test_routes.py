"""Tests for HTTP routes."""

import pytest
from fastapi.testclient import TestClient

from netstashd.models import Stash


class TestIndexRoutes:
    """Tests for index/home page routes."""

    def test_index_page(self, client: TestClient):
        """Test that index page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "netstashd" in response.text

    def test_index_shows_create_form_for_guest(self, client: TestClient):
        """Test that index shows create stash form for non-admin."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Create a Stash" in response.text
        assert 'action="/stash"' in response.text

    def test_index_shows_admin_link_for_admin(self, admin_client: TestClient):
        """Test that index shows dashboard link for admin."""
        response = admin_client.get("/")
        assert response.status_code == 200
        assert "Go to Dashboard" in response.text


class TestLoginRoutes:
    """Tests for login routes."""

    def test_login_page(self, client: TestClient):
        """Test that login page loads."""
        response = client.get("/login")
        assert response.status_code == 200

    def test_login_success(self, client: TestClient):
        """Test successful admin login."""
        response = client.post(
            "/login",
            data={"password": "test-admin-secret"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"

    def test_login_failure(self, client: TestClient):
        """Test failed admin login."""
        response = client.post(
            "/login",
            data={"password": "wrong-password"},
        )
        assert response.status_code == 401
        assert "Invalid password" in response.text

    def test_logout(self, admin_client: TestClient):
        """Test logout clears session."""
        response = admin_client.get("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"


class TestDashboardRoutes:
    """Tests for admin dashboard routes."""

    def test_dashboard_requires_auth(self, client: TestClient):
        """Test that dashboard requires admin auth."""
        response = client.get("/dashboard")
        assert response.status_code == 401

    def test_dashboard_accessible_by_admin(self, admin_client: TestClient):
        """Test that admin can access dashboard."""
        response = admin_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text

    def test_admin_create_stash(self, admin_client: TestClient):
        """Test admin creating a stash."""
        response = admin_client.post(
            "/dashboard/stash",
            data={
                "name": "Admin Stash",
                "max_size": "1",
                "size_unit": "GB",
                "ttl_days": "7",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/s/" in response.headers["location"]

    def test_admin_create_immortal_stash(self, admin_client: TestClient):
        """Test admin can create immortal stash (no TTL)."""
        response = admin_client.post(
            "/dashboard/stash",
            data={
                "name": "Immortal Stash",
                "max_size": "500",
                "size_unit": "MB",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303


class TestGuestStashCreation:
    """Tests for guest stash creation."""

    def test_guest_create_stash(self, client: TestClient):
        """Test guest creating a stash."""
        response = client.post(
            "/stash",
            data={
                "name": "Guest Stash",
                "max_size": "5",
                "size_unit": "MB",
                "ttl_days": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/s/" in response.headers["location"]

    def test_guest_create_stash_with_password(self, client: TestClient):
        """Test guest creating a password-protected stash."""
        response = client.post(
            "/stash",
            data={
                "name": "Protected Guest Stash",
                "password": "secret",
                "max_size": "5",
                "size_unit": "MB",
                "ttl_days": "2",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    def test_guest_cannot_exceed_size_limit(self, client: TestClient):
        """Test guest cannot create stash exceeding size limit."""
        response = client.post(
            "/stash",
            data={
                "name": "Too Big",
                "max_size": "500",
                "size_unit": "MB",  # 500 MB exceeds 10 MB test limit
                "ttl_days": "1",
            },
        )
        assert response.status_code == 400
        assert "Exceeds maximum" in response.text

    def test_guest_cannot_exceed_ttl_limit(self, client: TestClient):
        """Test guest cannot create stash exceeding TTL limit."""
        response = client.post(
            "/stash",
            data={
                "name": "Too Long",
                "max_size": "5",
                "size_unit": "MB",
                "ttl_days": "30",  # Exceeds 7 day test limit
            },
        )
        assert response.status_code == 400
        assert "TTL exceeds" in response.text

    def test_guest_stash_added_to_session(self, client: TestClient):
        """Test that created stash is added to user's session."""
        response = client.post(
            "/stash",
            data={
                "name": "Session Test",
                "max_size": "5",
                "size_unit": "MB",
                "ttl_days": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        # Check index shows "My Stashes" section
        index_response = client.get("/")
        assert "My Stashes" in index_response.text
        assert "Session Test" in index_response.text


class TestStashViewRoutes:
    """Tests for stash viewing routes."""

    def test_view_stash(self, client_with_stash: TestClient, sample_stash: Stash):
        """Test viewing a stash."""
        response = client_with_stash.get(f"/s/{sample_stash.id}")
        assert response.status_code == 200
        assert sample_stash.name in response.text

    def test_view_nonexistent_stash(self, client: TestClient):
        """Test viewing a stash that doesn't exist."""
        response = client.get("/s/nonexistent1234567890abcdef12")
        assert response.status_code == 404

    def test_view_password_protected_stash_requires_auth(
        self, client_with_protected_stash: TestClient, password_protected_stash: Stash
    ):
        """Test that password-protected stash requires authentication."""
        response = client_with_protected_stash.get(f"/s/{password_protected_stash.id}")
        assert response.status_code == 200
        assert "Password" in response.text or "password" in response.text

    def test_authenticate_to_stash(
        self, client_with_protected_stash: TestClient, password_protected_stash: Stash
    ):
        """Test authenticating to a password-protected stash."""
        response = client_with_protected_stash.post(
            f"/s/{password_protected_stash.id}/auth",
            data={"password": "secret123"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        # Should now be able to view stash
        view_response = client_with_protected_stash.get(f"/s/{password_protected_stash.id}")
        assert password_protected_stash.name in view_response.text

    def test_authenticate_wrong_password(
        self, client_with_protected_stash: TestClient, password_protected_stash: Stash
    ):
        """Test authentication with wrong password."""
        response = client_with_protected_stash.post(
            f"/s/{password_protected_stash.id}/auth",
            data={"password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "Invalid password" in response.text


class TestStashDeleteRoutes:
    """Tests for stash deletion routes."""

    def test_delete_stash_requires_admin(self, client_with_stash: TestClient, sample_stash: Stash):
        """Test that deleting stash requires admin."""
        response = client_with_stash.delete(f"/s/{sample_stash.id}")
        assert response.status_code == 401

    def test_admin_can_delete_stash(self, admin_client: TestClient):
        """Test that admin can delete a stash (creates its own stash)."""
        # Admin creates a stash first
        response = admin_client.post(
            "/dashboard/stash",
            data={"name": "To Delete", "max_size": "100", "size_unit": "MB", "ttl_days": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        stash_url = response.headers["location"]
        stash_id = stash_url.split("/s/")[1]

        # Now delete it
        delete_response = admin_client.delete(f"/s/{stash_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"


class TestAPIRoutes:
    """Tests for JSON API routes."""

    def test_api_status(self, client: TestClient):
        """Test API status endpoint."""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_api_list_stashes_requires_admin(self, client: TestClient):
        """Test that listing stashes requires admin."""
        response = client.get("/api/stashes")
        assert response.status_code == 401

    def test_api_list_stashes_with_api_key(self, client_with_stash: TestClient, sample_stash: Stash):
        """Test listing stashes with API key."""
        response = client_with_stash.get(
            "/api/stashes",
            headers={"X-API-Key": "test-admin-secret"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_api_get_stash(self, client_with_stash: TestClient, sample_stash: Stash):
        """Test getting stash info via API."""
        response = client_with_stash.get(f"/api/stashes/{sample_stash.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_stash.id
        assert data["name"] == sample_stash.name

    def test_api_get_nonexistent_stash(self, client: TestClient):
        """Test getting nonexistent stash via API."""
        response = client.get("/api/stashes/nonexistent")
        assert response.status_code == 404

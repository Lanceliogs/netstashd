"""Tests for secrets management module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSecretsModule:
    """Tests for secrets generation and storage."""

    def test_generate_secret(self):
        """Test that generate_secret returns a random string."""
        from netstashd.secrets import generate_secret
        
        secret1 = generate_secret()
        secret2 = generate_secret()
        
        assert isinstance(secret1, str)
        assert len(secret1) > 20
        assert secret1 != secret2

    def test_generate_secret_length(self):
        """Test generate_secret with custom length."""
        from netstashd.secrets import generate_secret
        
        short = generate_secret(16)
        long = generate_secret(64)
        
        assert len(short) < len(long)

    def test_get_admin_secret_from_env(self, temp_share_root: Path):
        """Test getting admin secret falls back to env var."""
        from netstashd.secrets import get_admin_secret
        
        # Make sure no file exists
        secrets_dir = temp_share_root / ".secrets"
        admin_file = secrets_dir / "admin_secret"
        if admin_file.exists():
            admin_file.unlink()
        
        # Should return env var value
        secret = get_admin_secret()
        assert secret == "test-admin-secret"

    def test_get_admin_secret_from_file(self, temp_share_root: Path):
        """Test getting admin secret from file takes priority."""
        from netstashd.secrets import get_admin_secret, get_secrets_dir
        
        # Create secret file
        secrets_dir = get_secrets_dir()
        admin_file = secrets_dir / "admin_secret"
        admin_file.write_text("file-based-secret")
        
        try:
            secret = get_admin_secret()
            assert secret == "file-based-secret"
        finally:
            admin_file.unlink()

    def test_rotate_admin_secret(self, temp_share_root: Path):
        """Test rotating admin secret creates a new one."""
        from netstashd.secrets import get_secrets_dir, rotate_admin_secret
        
        new_secret = rotate_admin_secret()
        
        # Verify file was created
        admin_file = get_secrets_dir() / "admin_secret"
        assert admin_file.exists()
        assert admin_file.read_text().strip() == new_secret
        
        # Clean up
        admin_file.unlink()

    def test_rotate_session_secret(self, temp_share_root: Path):
        """Test rotating session secret creates a new one."""
        from netstashd.secrets import get_secrets_dir, rotate_session_secret
        
        new_secret = rotate_session_secret()
        
        # Verify file was created
        session_file = get_secrets_dir() / "session_secret"
        assert session_file.exists()
        assert session_file.read_text().strip() == new_secret
        
        # Clean up
        session_file.unlink()

    def test_is_using_file_secret(self, temp_share_root: Path):
        """Test checking if secret is from file."""
        from netstashd.secrets import get_secrets_dir, is_using_file_secret
        
        secrets_dir = get_secrets_dir()
        test_file = secrets_dir / "test_secret"
        
        # Should be False when no file
        assert is_using_file_secret("test_secret") is False
        
        # Create file
        test_file.write_text("test")
        assert is_using_file_secret("test_secret") is True
        
        # Clean up
        test_file.unlink()

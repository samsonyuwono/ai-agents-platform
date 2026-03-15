"""Unit tests for utils/credential_store.py."""

import os
import sqlite3
import tempfile

import pytest

from utils.credential_store import CredentialStore


@pytest.fixture
def store(tmp_path):
    """Create a CredentialStore backed by a temp database."""
    db_path = str(tmp_path / "test_creds.db")
    with CredentialStore(db_path=db_path, secret="test-secret") as s:
        yield s


class TestCredentialStore:
    """Test encrypted credential storage."""

    def test_round_trip_save_get(self, store):
        """Save credentials and verify decryption matches original."""
        store.save_credentials("user@example.com", "my-password", auth_token="tok-123")
        creds = store.get_credentials("user@example.com")

        assert creds is not None
        assert creds["resy_email"] == "user@example.com"
        assert creds["password"] == "my-password"
        assert creds["resy_auth_token"] == "tok-123"
        assert creds["token_refreshed_at"] is not None

    def test_get_nonexistent_returns_none(self, store):
        """get_credentials returns None for unknown email."""
        assert store.get_credentials("nobody@example.com") is None

    def test_save_overwrites_existing(self, store):
        """Saving with same email updates the record."""
        store.save_credentials("user@example.com", "old-password")
        store.save_credentials("user@example.com", "new-password", auth_token="tok-new")

        creds = store.get_credentials("user@example.com")
        assert creds["password"] == "new-password"
        assert creds["resy_auth_token"] == "tok-new"

    def test_delete_credentials(self, store):
        """delete_credentials removes the row."""
        store.save_credentials("user@example.com", "pass")
        assert store.delete_credentials("user@example.com") is True
        assert store.get_credentials("user@example.com") is None

    def test_delete_nonexistent_returns_false(self, store):
        """delete_credentials returns False if not found."""
        assert store.delete_credentials("nobody@example.com") is False

    def test_has_credentials(self, store):
        """has_credentials reflects presence of row."""
        assert store.has_credentials("user@example.com") is False
        store.save_credentials("user@example.com", "pass")
        assert store.has_credentials("user@example.com") is True

    def test_update_auth_token(self, store):
        """update_auth_token updates token and refreshed_at."""
        store.save_credentials("user@example.com", "pass", auth_token="old-tok")
        assert store.update_auth_token("user@example.com", "new-tok") is True

        creds = store.get_credentials("user@example.com")
        assert creds["resy_auth_token"] == "new-tok"

    def test_update_auth_token_nonexistent(self, store):
        """update_auth_token returns False for unknown email."""
        assert store.update_auth_token("nobody@example.com", "tok") is False

    def test_encrypted_password_not_plaintext_in_db(self, store):
        """Verify the raw DB column is not plaintext."""
        store.save_credentials("user@example.com", "super-secret-password")

        # Read raw bytes from the database
        cursor = store.conn.cursor()
        cursor.execute("SELECT encrypted_password FROM user_credentials WHERE resy_email = ?",
                        ("user@example.com",))
        raw = cursor.fetchone()["encrypted_password"]

        # Raw value should be bytes, not the plaintext password
        assert isinstance(raw, bytes)
        assert b"super-secret-password" not in raw

    def test_context_manager(self, tmp_path):
        """Test context manager opens and closes cleanly."""
        db_path = str(tmp_path / "ctx.db")
        with CredentialStore(db_path=db_path, secret="s") as s:
            s.save_credentials("a@b.com", "p")
            assert s.has_credentials("a@b.com")

    def test_save_without_auth_token(self, store):
        """Save credentials without an auth token."""
        store.save_credentials("user@example.com", "pass")
        creds = store.get_credentials("user@example.com")
        assert creds["resy_auth_token"] is None
        assert creds["token_refreshed_at"] is None

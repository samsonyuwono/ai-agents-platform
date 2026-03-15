"""Unit tests for api/resy_credentials.py."""

import time

import jwt
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_token(secret="test-jwt-secret", resy_email=None):
    payload = {"sub": "user", "iat": int(time.time()), "exp": int(time.time()) + 3600}
    if resy_email:
        payload["resy_email"] = resy_email
    return jwt.encode(payload, secret, algorithm="HS256")


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestResyLink:
    """Test POST /api/resy/link."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.resy_credentials._get_credential_store')
    @patch('api.resy_credentials.ResyClient')
    @patch('api.auth.Settings')
    def test_link_success(self, mock_auth_settings, mock_resy_cls, mock_get_store, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()

        # Mock Resy auth success
        mock_client = MagicMock()
        mock_client.refresh_auth_token.return_value = "resy-tok-123"
        mock_resy_cls.return_value = mock_client

        # Mock credential store (context manager returns itself)
        mock_store = MagicMock()
        mock_store.__enter__ = MagicMock(return_value=mock_store)
        mock_store.__exit__ = MagicMock(return_value=False)
        mock_get_store.return_value = mock_store

        client = self._get_client()
        resp = client.post(
            "/api/resy/link",
            json={"email": "user@resy.com", "password": "resypass"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["resy_email"] == "user@resy.com"
        assert "token" in data

        # Verify new JWT contains resy_email
        new_payload = jwt.decode(data["token"], "test-jwt-secret", algorithms=["HS256"])
        assert new_payload["resy_email"] == "user@resy.com"

        # Verify credentials were stored
        mock_store.save_credentials.assert_called_once_with(
            "user@resy.com", "resypass", auth_token="resy-tok-123"
        )

    @patch('api.resy_credentials.ResyClient')
    @patch('api.auth.Settings')
    def test_link_bad_creds_returns_401(self, mock_auth_settings, mock_resy_cls, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()

        mock_client = MagicMock()
        mock_client.refresh_auth_token.side_effect = Exception("Auth failed: 401")
        mock_resy_cls.return_value = mock_client

        client = self._get_client()
        resp = client.post(
            "/api/resy/link",
            json={"email": "bad@resy.com", "password": "wrong"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 401
        assert "Invalid Resy credentials" in resp.json()["detail"]


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestResyStatus:
    """Test GET /api/resy/status."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.resy_credentials._get_credential_store')
    @patch('api.auth.Settings')
    def test_status_linked(self, mock_auth_settings, mock_get_store, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token(resy_email="user@resy.com")

        mock_store = MagicMock()
        mock_store.__enter__ = MagicMock(return_value=mock_store)
        mock_store.__exit__ = MagicMock(return_value=False)
        mock_store.has_credentials.return_value = True
        mock_get_store.return_value = mock_store

        client = self._get_client()
        resp = client.get(
            "/api/resy/status",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] is True
        assert data["resy_email"] == "user@resy.com"

    @patch('api.auth.Settings')
    def test_status_not_linked(self, mock_auth_settings, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token(resy_email=None)

        client = self._get_client()
        resp = client.get(
            "/api/resy/status",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] is False
        assert data["resy_email"] is None


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestResyUnlink:
    """Test DELETE /api/resy/unlink."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.resy_credentials._get_credential_store')
    @patch('api.auth.Settings')
    def test_unlink_deletes_and_reissues_token(self, mock_auth_settings, mock_get_store, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token(resy_email="user@resy.com")

        mock_store = MagicMock()
        mock_store.__enter__ = MagicMock(return_value=mock_store)
        mock_store.__exit__ = MagicMock(return_value=False)
        mock_get_store.return_value = mock_store

        client = self._get_client()
        resp = client.delete(
            "/api/resy/unlink",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify new JWT has no resy_email
        new_payload = jwt.decode(data["token"], "test-jwt-secret", algorithms=["HS256"])
        assert "resy_email" not in new_payload

        # Verify credentials were deleted
        mock_store.delete_credentials.assert_called_once_with("user@resy.com")

    @patch('api.auth.Settings')
    def test_unlink_without_linked_account(self, mock_auth_settings, _validate):
        """Unlink when no resy_email in JWT is a no-op."""
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token(resy_email=None)

        client = self._get_client()
        resp = client.delete(
            "/api/resy/unlink",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

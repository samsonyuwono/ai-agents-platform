"""Unit tests for api/auth.py."""

import time

import jwt
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestAuthEndpoints:
    """Test login and token validation."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.auth.Settings')
    def test_login_success(self, mock_settings, _validate):
        mock_settings.WEB_AUTH_PASSWORD = "secret123"
        mock_settings.WEB_JWT_SECRET = "test-jwt-secret"
        client = self._get_client()

        resp = client.post("/api/auth/login", json={"password": "secret123"})

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        # Verify the token is valid JWT
        payload = jwt.decode(data["token"], "test-jwt-secret", algorithms=["HS256"])
        assert payload["sub"] == "user"

    @patch('api.auth.Settings')
    def test_login_wrong_password(self, mock_settings, _validate):
        mock_settings.WEB_AUTH_PASSWORD = "secret123"
        client = self._get_client()

        resp = client.post("/api/auth/login", json={"password": "wrong"})

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid password"

    @patch('api.auth.Settings')
    def test_login_no_password_configured(self, mock_settings, _validate):
        mock_settings.WEB_AUTH_PASSWORD = None
        client = self._get_client()

        resp = client.post("/api/auth/login", json={"password": "anything"})

        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"]

    def test_protected_route_no_token(self, _validate):
        client = self._get_client()

        resp = client.get("/api/chat/history/some-id")

        assert resp.status_code in (401, 403)  # Depends on FastAPI/Starlette version

    @patch('api.auth.Settings')
    def test_protected_route_invalid_token(self, mock_settings, _validate):
        mock_settings.WEB_JWT_SECRET = "test-jwt-secret"
        client = self._get_client()

        resp = client.get(
            "/api/chat/history/some-id",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert resp.status_code == 401

    @patch('api.auth.Settings')
    def test_protected_route_expired_token(self, mock_settings, _validate):
        mock_settings.WEB_JWT_SECRET = "test-jwt-secret"
        client = self._get_client()

        # Create an expired token
        payload = {"sub": "user", "iat": int(time.time()) - 3600, "exp": int(time.time()) - 1}
        expired_token = jwt.encode(payload, "test-jwt-secret", algorithm="HS256")

        resp = client.get(
            "/api/chat/history/some-id",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token expired"

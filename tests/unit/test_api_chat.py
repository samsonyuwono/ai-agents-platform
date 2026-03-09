"""Unit tests for api/chat.py."""

import json

import jwt
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_token(secret="test-jwt-secret"):
    import time
    payload = {"sub": "user", "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, secret, algorithm="HS256")


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestChatEndpoint:
    """Test POST /api/chat SSE streaming."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_chat_streams_sse_events(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()

        # Create a mock agent that emits events via callback
        mock_agent = MagicMock()
        def fake_run(message, event_callback=None):
            event_callback("thinking", {"iteration": 1})
            event_callback("tool_call", {"tool": "search_resy_restaurants", "input": {"query": "Le Gratin"}})
            event_callback("tool_result", {"tool": "search_resy_restaurants", "result": {"success": True}})
            event_callback("message", {"text": "Found Le Gratin!"})
            event_callback("done", {})
            return "Found Le Gratin!"

        mock_agent.run = fake_run
        mock_session_mgr.get_or_create.return_value = ("test-session-123", mock_agent)

        client = self._get_client()
        resp = client.post(
            "/api/chat",
            json={"message": "Find Le Gratin"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        # Parse SSE events from the response body
        events = []
        for line in resp.text.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
                events.append((event_type, data))

        event_types = [e[0] for e in events]
        assert "session" in event_types
        assert "thinking" in event_types
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "message" in event_types
        assert "done" in event_types

        # Verify session_id is emitted
        session_event = next(e for e in events if e[0] == "session")
        assert session_event[1]["session_id"] == "test-session-123"

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_chat_handles_agent_error(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()

        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("Resy API down")
        mock_session_mgr.get_or_create.return_value = ("err-session", mock_agent)

        client = self._get_client()
        resp = client.post(
            "/api/chat",
            json={"message": "Find something"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200  # SSE always returns 200, errors come as events
        assert "error" in resp.text
        assert "Resy API down" in resp.text

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_chat_passes_session_id(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()

        mock_agent = MagicMock()
        def fake_run(message, event_callback=None):
            event_callback("message", {"text": "hi"})
            event_callback("done", {})
            return "hi"
        mock_agent.run = fake_run
        mock_session_mgr.get_or_create.return_value = ("existing-session", mock_agent)

        client = self._get_client()
        resp = client.post(
            "/api/chat",
            json={"message": "hello", "session_id": "existing-session"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        mock_session_mgr.get_or_create.assert_called_with("existing-session")


@patch('config.settings.Settings.validate', return_value=True)
@patch('config.settings.Settings.ANTHROPIC_API_KEY', 'test-key')
class TestSessionEndpoints:
    """Test history and delete endpoints."""

    def _get_client(self):
        from api.main import app
        return TestClient(app)

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_get_history(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()
        mock_session_mgr.get_history.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        client = self._get_client()
        resp = client.get(
            "/api/chat/history/test-session",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-session"
        assert len(data["history"]) == 2

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_delete_session(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()
        mock_session_mgr.delete.return_value = True

        client = self._get_client()
        resp = client.delete(
            "/api/chat/session/test-session",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    @patch('api.chat.session_manager')
    @patch('api.auth.Settings')
    def test_delete_session_not_found(self, mock_auth_settings, mock_session_mgr, _validate):
        mock_auth_settings.WEB_JWT_SECRET = "test-jwt-secret"
        token = _make_token()
        mock_session_mgr.delete.return_value = False

        client = self._get_client()
        resp = client.delete(
            "/api/chat/session/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 404

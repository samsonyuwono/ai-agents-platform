"""Unit tests for Resy session export (storage state persistence)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


class TestGetStorageStatePath:
    """Test ResyBrowserClient._get_storage_state_path()."""

    def _make_client(self, storage_state_file):
        """Create a minimal client with patched storage_state_file."""
        with patch('utils.resy_browser_client.Settings') as mock_settings:
            mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
            mock_settings.RESY_BROWSER_PASSWORD = 'password'
            mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
            mock_settings.RESY_PROXY_SERVER = None
            mock_settings.RESY_PROXY_USERNAME = None
            mock_settings.RESY_PROXY_PASSWORD = None
            from utils.resy_browser_client import ResyBrowserClient
            client = ResyBrowserClient.__new__(ResyBrowserClient)
            client.storage_state_file = storage_state_file
        return client

    def test_returns_path_when_valid_json_exists(self, tmp_path):
        """Valid JSON file returns its path as a string."""
        state_file = tmp_path / '.resy_storage_state.json'
        state_file.write_text(json.dumps({"cookies": [], "origins": []}))
        client = self._make_client(state_file)
        assert client._get_storage_state_path() == str(state_file)

    def test_returns_none_when_file_missing(self, tmp_path):
        """Missing file returns None."""
        state_file = tmp_path / '.resy_storage_state.json'
        client = self._make_client(state_file)
        assert client._get_storage_state_path() is None

    def test_returns_none_when_invalid_json(self, tmp_path):
        """Corrupt JSON file returns None."""
        state_file = tmp_path / '.resy_storage_state.json'
        state_file.write_text("not valid json {{{")
        client = self._make_client(state_file)
        assert client._get_storage_state_path() is None


class TestSaveSession:
    """Test ResyBrowserClient._save_session()."""

    def test_calls_storage_state_on_context(self):
        """_save_session calls context.storage_state(path=...) and writes cookies."""
        with patch('utils.resy_browser_client.Settings') as mock_settings:
            mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
            mock_settings.RESY_BROWSER_PASSWORD = 'password'
            mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
            mock_settings.RESY_PROXY_SERVER = None
            mock_settings.RESY_PROXY_USERNAME = None
            mock_settings.RESY_PROXY_PASSWORD = None
            from utils.resy_browser_client import ResyBrowserClient
            client = ResyBrowserClient.__new__(ResyBrowserClient)

        client.storage_state_file = Path('/tmp/test_storage_state.json')
        client.cookie_file = Path('/tmp/test_cookies.json')
        client.context = MagicMock()
        client.context.cookies.return_value = [{"name": "tok", "value": "123"}]

        with patch('builtins.open', MagicMock()):
            client._save_session()

        client.context.storage_state.assert_called_once_with(
            path=str(client.storage_state_file)
        )


class TestLaunchBrowserStorageState:
    """Test that _launch_browser passes storage_state to new_context."""

    @patch('utils.resy_browser_client.sync_playwright')
    @patch('utils.resy_browser_client.Settings')
    def test_passes_storage_state_to_new_context(self, mock_settings, mock_pw):
        """new_context receives storage_state path when file exists."""
        mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
        mock_settings.RESY_BROWSER_PASSWORD = 'password'
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
        mock_settings.RESY_PROXY_SERVER = None
        mock_settings.RESY_PROXY_USERNAME = None
        mock_settings.RESY_PROXY_PASSWORD = None
        mock_settings.has_proxy_configured.return_value = False

        from utils.resy_browser_client import ResyBrowserClient
        client = ResyBrowserClient.__new__(ResyBrowserClient)
        client.headless = True
        client.storage_state_file = Path('/tmp/fake_state.json')
        client.cookie_file = Path('/tmp/fake_cookies.json')
        client.playwright = None
        client.browser = None
        client.context = None
        client.page = None

        # Mock _get_storage_state_path to return a path
        with patch.object(client, '_get_storage_state_path', return_value='/tmp/fake_state.json'):
            mock_browser = MagicMock()
            mock_pw.return_value.start.return_value.chromium.launch.return_value = mock_browser
            mock_context = MagicMock()
            mock_browser.new_context.return_value = mock_context
            mock_page = MagicMock()
            mock_context.new_page.return_value = mock_page

            client._launch_browser()

        # Verify storage_state was passed
        new_context_kwargs = mock_browser.new_context.call_args
        assert new_context_kwargs.kwargs.get('storage_state') == '/tmp/fake_state.json'

    @patch('utils.resy_browser_client.sync_playwright')
    @patch('utils.resy_browser_client.Settings')
    def test_passes_none_when_no_storage_state(self, mock_settings, mock_pw):
        """new_context receives storage_state=None when no file exists."""
        mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
        mock_settings.RESY_BROWSER_PASSWORD = 'password'
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
        mock_settings.RESY_PROXY_SERVER = None
        mock_settings.RESY_PROXY_USERNAME = None
        mock_settings.RESY_PROXY_PASSWORD = None
        mock_settings.has_proxy_configured.return_value = False

        from utils.resy_browser_client import ResyBrowserClient
        client = ResyBrowserClient.__new__(ResyBrowserClient)
        client.headless = True
        client.storage_state_file = Path('/tmp/fake_state.json')
        client.cookie_file = Path('/tmp/fake_cookies.json')
        client.playwright = None
        client.browser = None
        client.context = None
        client.page = None

        with patch.object(client, '_get_storage_state_path', return_value=None):
            mock_browser = MagicMock()
            mock_pw.return_value.start.return_value.chromium.launch.return_value = mock_browser
            mock_context = MagicMock()
            mock_browser.new_context.return_value = mock_context
            mock_page = MagicMock()
            mock_context.new_page.return_value = mock_page

            client._launch_browser()

        new_context_kwargs = mock_browser.new_context.call_args
        assert new_context_kwargs.kwargs.get('storage_state') is None


class TestEnsureAuthenticatedPrefersStorageState:
    """Test that _ensure_authenticated prefers storage state over cookies."""

    def test_skips_cookie_loading_when_storage_state_exists(self):
        """When storage state file exists, cookie loading is skipped."""
        with patch('utils.resy_browser_client.Settings') as mock_settings:
            mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
            mock_settings.RESY_BROWSER_PASSWORD = 'password'
            mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
            mock_settings.RESY_PROXY_SERVER = None
            mock_settings.RESY_PROXY_USERNAME = None
            mock_settings.RESY_PROXY_PASSWORD = None
            from utils.resy_browser_client import ResyBrowserClient
            client = ResyBrowserClient.__new__(ResyBrowserClient)

        client.is_authenticated = False
        client.page = MagicMock()  # Already launched
        client.context = MagicMock()
        client.storage_state_file = Path('/tmp/fake_state.json')
        client.cookie_file = Path('/tmp/fake_cookies.json')

        with patch.object(client, '_get_storage_state_path', return_value='/tmp/fake_state.json'):
            with patch.object(client, '_is_session_valid', return_value=True):
                with patch.object(client, '_load_cookies') as mock_load:
                    with patch.object(client, '_login') as mock_login:
                        client._ensure_authenticated()

        assert client.is_authenticated is True
        mock_load.assert_not_called()
        mock_login.assert_not_called()

    def test_falls_back_to_cookies_when_no_storage_state(self):
        """When no storage state, falls back to cookie loading."""
        with patch('utils.resy_browser_client.Settings') as mock_settings:
            mock_settings.RESY_BROWSER_EMAIL = 'test@test.com'
            mock_settings.RESY_BROWSER_PASSWORD = 'password'
            mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6
            mock_settings.RESY_PROXY_SERVER = None
            mock_settings.RESY_PROXY_USERNAME = None
            mock_settings.RESY_PROXY_PASSWORD = None
            from utils.resy_browser_client import ResyBrowserClient
            client = ResyBrowserClient.__new__(ResyBrowserClient)

        client.is_authenticated = False
        client.page = MagicMock()
        client.context = MagicMock()
        client.storage_state_file = Path('/tmp/fake_state.json')
        client.cookie_file = Path('/tmp/fake_cookies.json')

        with patch.object(client, '_get_storage_state_path', return_value=None):
            with patch.object(client, '_load_cookies', return_value=True) as mock_load:
                with patch.object(client, '_is_session_valid', return_value=True):
                    with patch.object(client, '_login') as mock_login:
                        client._ensure_authenticated()

        assert client.is_authenticated is True
        mock_load.assert_called_once()
        mock_login.assert_not_called()

"""Tests for ResyClient API client."""

import pytest
from unittest.mock import patch, MagicMock


def _make_client(**overrides):
    """Create a ResyClient with mocked settings, skipping real HTTP."""
    with patch('utils.resy_client.Settings') as mock_settings:
        mock_settings.RESY_API_KEY = 'test-api-key'
        mock_settings.RESY_AUTH_TOKEN = 'test-auth-token'
        mock_settings.RESY_EMAIL = 'test@example.com'
        mock_settings.RESY_PASSWORD = 'password123'
        mock_settings.RESY_PAYMENT_METHOD_ID = 'pm_123'

        from utils.resy_client import ResyClient
        client = ResyClient.__new__(ResyClient)
        client.api_key = 'test-api-key'
        client.auth_token = 'test-auth-token'
        client.base_url = 'https://api.resy.com'
        client.last_request_time = 0
        client.min_delay_seconds = 0  # No delay in tests
        client.session = MagicMock()

        for key, val in overrides.items():
            setattr(client, key, val)

        return client, mock_settings


class TestInit:
    """Test ResyClient initialization."""

    @patch('utils.resy_client.Settings')
    def test_init_with_api_key_only(self, mock_settings):
        """API key alone is enough — auth token can be acquired later."""
        mock_settings.RESY_API_KEY = 'key123'
        mock_settings.RESY_AUTH_TOKEN = None
        from utils.resy_client import ResyClient
        client = ResyClient(api_key='key123', auth_token=None)
        assert client.api_key == 'key123'
        assert client.auth_token is None

    @patch('utils.resy_client.Settings')
    def test_init_no_api_key_raises(self, mock_settings):
        """Missing API key should raise ValueError."""
        mock_settings.RESY_API_KEY = None
        mock_settings.RESY_AUTH_TOKEN = None
        from utils.resy_client import ResyClient
        with pytest.raises(ValueError, match="API key is required"):
            ResyClient(api_key=None, auth_token=None)

    @patch('utils.resy_client.Settings')
    def test_rate_limit_default(self, mock_settings):
        """Default rate limit should be 1 second."""
        mock_settings.RESY_API_KEY = 'key'
        mock_settings.RESY_AUTH_TOKEN = 'tok'
        from utils.resy_client import ResyClient
        client = ResyClient(api_key='key', auth_token='tok')
        assert client.min_delay_seconds == 1


class TestRefreshAuthToken:
    """Test auth token refresh via password endpoint."""

    def test_refresh_success(self):
        client, mock_settings = _make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'token': 'new-token-123'}
        mock_response.raise_for_status = MagicMock()
        client.session.post.return_value = mock_response

        token = client.refresh_auth_token(email='test@example.com', password='pass')

        assert token == 'new-token-123'
        assert client.auth_token == 'new-token-123'
        client.session.post.assert_called_once()
        call_args = client.session.post.call_args
        assert '/3/auth/password' in call_args[0][0]

    def test_refresh_no_credentials_raises(self):
        client, _ = _make_client()

        with patch('utils.resy_client.Settings') as mock_settings:
            mock_settings.RESY_EMAIL = None
            mock_settings.RESY_PASSWORD = None
            with pytest.raises(ValueError, match="Email and password required"):
                client.refresh_auth_token(email=None, password=None)

    def test_refresh_no_token_in_response(self):
        client, _ = _make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        client.session.post.return_value = mock_response

        with pytest.raises(Exception, match="No token"):
            client.refresh_auth_token(email='a@b.com', password='p')


class TestMakeRequestAutoRefresh:
    """Test that _make_request auto-refreshes token on 401."""

    def test_401_triggers_refresh_and_retry(self):
        client, mock_settings = _make_client()

        # First response: 401, second (after refresh): 200
        resp_401 = MagicMock()
        resp_401.status_code = 401

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {'data': 'ok'}
        resp_200.raise_for_status = MagicMock()

        # refresh_auth_token post response
        refresh_resp = MagicMock()
        refresh_resp.status_code = 200
        refresh_resp.json.return_value = {'token': 'refreshed'}
        refresh_resp.raise_for_status = MagicMock()

        client.session.request.side_effect = [resp_401, resp_200]
        client.session.post.return_value = refresh_resp

        result = client._make_request('GET', '/3/test')
        assert result == {'data': 'ok'}
        assert client.auth_token == 'refreshed'
        assert client.session.request.call_count == 2


class TestGetAvailabilitySlugResolution:
    """Test that get_availability resolves slugs to numeric IDs."""

    def test_numeric_id_skips_resolution(self):
        client, _ = _make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [{
                'venue': {'name': 'Test'},
                'configs': [{'id': 'cfg1', 'token': 't1', 'time_slot': '19:00',
                             'type': 'Dining Room', 'name': 'Table for 2'}]
            }]
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request.return_value = mock_response

        slots = client.get_availability('12345', '2026-03-15', 2)
        assert len(slots) == 1
        assert slots[0]['config_id'] == 'cfg1'
        # Should NOT have called get_venue_by_slug
        call_args = client.session.request.call_args
        assert 'venue_id' in str(call_args)

    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'get_venue_by_slug')
    def test_slug_resolved_to_id(self, mock_get_venue):
        client, _ = _make_client()
        mock_get_venue.return_value = {'id': 99999, 'name': 'Fish Cheeks'}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'results': []}
        mock_response.raise_for_status = MagicMock()
        client.session.request.return_value = mock_response

        client.get_availability('fish-cheeks', '2026-03-15', 2)
        mock_get_venue.assert_called_once_with('fish-cheeks')

    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'get_venue_by_slug')
    def test_slug_resolution_failure_returns_empty(self, mock_get_venue):
        client, _ = _make_client()
        mock_get_venue.return_value = None

        result = client.get_availability('nonexistent-place', '2026-03-15', 2)
        assert result == []


class TestResolveReservationConflict:
    """Test API-mode conflict resolution."""

    def test_keep_existing(self):
        client, _ = _make_client()
        result = client.resolve_reservation_conflict(
            'keep_existing', 'cfg1', '2026-03-15', 2)
        assert result == {'success': True, 'status': 'kept_existing'}

    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'get_reservations')
    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'cancel_reservation')
    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'make_reservation')
    def test_rebook_cancels_and_books(self, mock_book, mock_cancel, mock_get_res):
        client, _ = _make_client()
        mock_get_res.return_value = [
            {'id': 'tok_old', 'date': '2026-03-15', 'venue_name': 'Old Place'}
        ]
        mock_cancel.return_value = True
        mock_book.return_value = {'success': True, 'reservation_id': 'new123'}

        result = client.resolve_reservation_conflict(
            'replace', 'cfg_new', '2026-03-15', 2)

        mock_cancel.assert_called_once_with('tok_old')
        mock_book.assert_called_once_with('cfg_new', '2026-03-15', 2)
        assert result['success'] is True

    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'get_reservations')
    @patch.object(__import__('utils.resy_client', fromlist=['ResyClient']).ResyClient,
                  'make_reservation')
    def test_rebook_no_conflict_still_books(self, mock_book, mock_get_res):
        client, _ = _make_client()
        mock_get_res.return_value = []  # No existing reservations
        mock_book.return_value = {'success': True}

        result = client.resolve_reservation_conflict(
            'replace', 'cfg1', '2026-03-20', 2)

        mock_book.assert_called_once()
        assert result['success'] is True

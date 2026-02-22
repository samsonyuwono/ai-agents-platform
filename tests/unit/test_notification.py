"""Unit tests for SniperNotifier."""

import pytest
from unittest.mock import patch, MagicMock
from utils.notification import SniperNotifier, _format_success, _format_failure


class TestSniperNotifier:
    """Test SniperNotifier email notifications."""

    @pytest.fixture
    def mock_sender(self):
        """Create a mock EmailSender."""
        sender = MagicMock()
        sender.send.return_value = True
        return sender

    @pytest.fixture
    def notifier(self, mock_sender):
        """Create a SniperNotifier with mock sender."""
        n = SniperNotifier(email_sender=mock_sender)
        n._to_email = "test@example.com"
        return n

    @pytest.fixture
    def sample_job(self):
        return {
            'venue_slug': 'fish-cheeks',
            'date': '2026-03-01',
            'preferred_times': ['7:00 PM', '7:30 PM'],
            'party_size': 2,
            'poll_count': 5,
            'max_attempts': 60,
        }

    @pytest.fixture
    def sample_reservation(self):
        return {
            'time_slot': '7:00 PM',
            'reservation_id': 'RES123',
        }

    def test_is_configured(self, notifier):
        assert notifier.is_configured is True

    def test_not_configured_without_sender(self):
        n = SniperNotifier.__new__(SniperNotifier)
        n._sender = None
        n._to_email = "test@example.com"
        assert n.is_configured is False

    def test_not_configured_without_email(self, mock_sender):
        n = SniperNotifier.__new__(SniperNotifier)
        n._sender = mock_sender
        n._to_email = None
        assert n.is_configured is False

    def test_notify_success_sends_email(self, notifier, mock_sender, sample_job, sample_reservation):
        result = notifier.notify_success(sample_job, sample_reservation)

        assert result is True
        mock_sender.send.assert_called_once()
        call_args = mock_sender.send.call_args
        assert "fish-cheeks" in call_args[0][1]  # subject
        assert "2026-03-01" in call_args[0][1]

    def test_notify_success_unconfigured_returns_false(self, sample_job, sample_reservation):
        n = SniperNotifier.__new__(SniperNotifier)
        n._sender = None
        n._to_email = None
        assert n.notify_success(sample_job, sample_reservation) is False

    def test_notify_failure_sends_email(self, notifier, mock_sender, sample_job):
        result = notifier.notify_failure(sample_job, "Max attempts reached")

        assert result is True
        mock_sender.send.assert_called_once()
        call_args = mock_sender.send.call_args
        assert "Failed" in call_args[0][1]

    def test_notify_failure_unconfigured_returns_false(self, sample_job):
        n = SniperNotifier.__new__(SniperNotifier)
        n._sender = None
        n._to_email = None
        assert n.notify_failure(sample_job, "No slots") is False


class TestFormatting:
    """Test notification formatting functions."""

    def test_format_success_contains_details(self):
        job = {
            'venue_slug': 'temple-court',
            'date': '2026-03-15',
            'preferred_times': ['8:00 PM'],
            'party_size': 4,
            'poll_count': 3,
            'max_attempts': 60,
        }
        reservation = {
            'time_slot': '8:00 PM',
            'reservation_id': 'RES456',
        }
        body = _format_success(job, reservation)

        assert 'temple-court' in body
        assert '2026-03-15' in body
        assert '8:00 PM' in body
        assert 'RES456' in body
        assert '4' in body

    def test_format_failure_contains_reason(self):
        job = {
            'venue_slug': 'fish-cheeks',
            'date': '2026-03-01',
            'preferred_times': ['7:00 PM'],
            'party_size': 2,
            'poll_count': 60,
            'max_attempts': 60,
        }
        body = _format_failure(job, "No availability found after 60 attempts")

        assert 'fish-cheeks' in body
        assert 'No availability found' in body
        assert '60 / 60' in body

    def test_format_success_handles_missing_fields(self):
        job = {'venue_slug': 'test', 'date': '2026-01-01'}
        reservation = {}
        body = _format_success(job, reservation)
        assert 'test' in body
        assert 'N/A' in body  # Missing time_slot and reservation_id


class TestNotificationSendFailures:
    """Test notification behavior when sender.send returns False."""

    @pytest.fixture
    def failing_sender(self):
        sender = MagicMock()
        sender.send.return_value = False
        return sender

    @pytest.fixture
    def sample_job(self):
        return {
            'venue_slug': 'fish-cheeks',
            'date': '2026-03-01',
            'preferred_times': ['7:00 PM'],
            'party_size': 2,
            'poll_count': 5,
            'max_attempts': 60,
        }

    def test_notify_success_send_fails(self, failing_sender, sample_job):
        """Test notify_success returns False when send fails."""
        n = SniperNotifier(email_sender=failing_sender)
        n._to_email = "test@example.com"

        result = n.notify_success(sample_job, {'time_slot': '7:00 PM', 'reservation_id': 'R1'})
        assert result is False

    def test_notify_failure_send_fails(self, failing_sender, sample_job):
        """Test notify_failure returns False when send fails."""
        n = SniperNotifier(email_sender=failing_sender)
        n._to_email = "test@example.com"

        result = n.notify_failure(sample_job, "Max attempts reached")
        assert result is False

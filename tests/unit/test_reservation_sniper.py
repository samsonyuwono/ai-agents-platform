"""Unit tests for ReservationSniper."""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch
from utils.reservation_sniper import ReservationSniper
from utils.reservation_store import ReservationStore


class TestReservationSniper:
    """Test ReservationSniper core functionality."""

    @pytest.fixture
    def store(self):
        """Create a temporary ReservationStore."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        store = ReservationStore(db_path=db_path)
        yield store
        store.close()
        os.unlink(db_path)

    @pytest.fixture
    def mock_client(self):
        """Create a mock Resy client."""
        return MagicMock()

    @pytest.fixture
    def mock_notifier(self):
        """Create a mock SniperNotifier."""
        notifier = MagicMock()
        notifier.notify_success.return_value = True
        notifier.notify_failure.return_value = True
        return notifier

    @pytest.fixture
    def sniper(self, mock_client, store, mock_notifier):
        """Create a ReservationSniper with mocked deps."""
        return ReservationSniper(
            client=mock_client,
            store=store,
            notifier=mock_notifier,
        )

    def test_create_job(self, sniper, store):
        """Test creating a sniper job persists correctly."""
        job_id = sniper.create_job(
            venue_slug='fish-cheeks',
            date='2026-03-01',
            preferred_times=['7:00 PM'],
            party_size=2,
            scheduled_at='2026-02-22T09:00:00',
        )

        assert job_id > 0
        job = store.get_sniper_job(job_id)
        assert job['venue_slug'] == 'fish-cheeks'
        assert job['date'] == '2026-03-01'
        assert job['preferred_times'] == ['7:00 PM']
        assert job['status'] == 'pending'

    def test_create_job_defaults(self, sniper, store):
        """Test that defaults are applied correctly."""
        job_id = sniper.create_job(
            venue_slug='test',
            date='2026-03-01',
            preferred_times=['8:00 PM'],
        )

        job = store.get_sniper_job(job_id)
        assert job['party_size'] == 2
        assert job['time_window_minutes'] == 60
        assert job['max_attempts'] == 60
        assert job['auto_resolve_conflicts'] is True

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_no_availability(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once when no slots are available."""
        mock_client.get_availability.return_value = []

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is False
        assert 'No slots' in result['error']

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_books_preferred_time(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once books the preferred time when available."""
        mock_client.get_availability.return_value = [
            {'time': '6:00 PM', 'config_id': 'test|||2026-03-01|||6:00 PM'},
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
            {'time': '8:00 PM', 'config_id': 'test|||2026-03-01|||8:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES123',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is True
        assert result['time'] == '7:00 PM'
        assert result['reservation_id'] == 'RES123'
        # Verify make_reservation was called with the 7:00 PM config_id
        mock_client.make_reservation.assert_called_once_with(
            config_id='test|||2026-03-01|||7:00 PM',
            date='2026-03-01',
            party_size=2,
        )

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_falls_back_to_closest(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once falls back to closest slot when preferred is unavailable."""
        mock_client.get_availability.return_value = [
            {'time': '6:00 PM', 'config_id': 'test|||2026-03-01|||6:00 PM'},
            {'time': '7:30 PM', 'config_id': 'test|||2026-03-01|||7:30 PM'},
            {'time': '9:00 PM', 'config_id': 'test|||2026-03-01|||9:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES456',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is True
        assert result['time'] == '7:30 PM'  # Closest to 7:00 PM

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_conflict_auto_resolves(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once resolves conflicts when auto_resolve is enabled."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        # First booking returns conflict, then resolve succeeds
        mock_client.make_reservation.return_value = {
            'success': False,
            'status': 'conflict',
        }
        mock_client.resolve_reservation_conflict.return_value = {
            'success': True,
            'reservation_id': 'RES789',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            auto_resolve_conflicts=True, scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is True
        assert result['reservation_id'] == 'RES789'
        mock_client.resolve_reservation_conflict.assert_called_once()

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_booking_fails(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once when booking fails (non-conflict)."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': False,
            'error': 'Slot taken',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is False
        assert 'Slot taken' in result['error']

    @patch('utils.reservation_sniper.time.sleep')
    def test_run_job_max_attempts(self, mock_sleep, sniper, store, mock_client, mock_notifier):
        """Test run_job stops after max attempts and notifies failure."""
        mock_client.get_availability.return_value = []

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            max_attempts=3, scheduled_at='2020-01-01T00:00:00',
        )

        result = sniper.run_job(job_id)

        assert result['outcome'] == 'failed'
        assert 'Max attempts' in result['reason']
        mock_notifier.notify_failure.assert_called_once()

        job = store.get_sniper_job(job_id)
        assert job['status'] == 'failed'

    @patch('utils.reservation_sniper.time.sleep')
    def test_run_job_success_notifies(self, mock_sleep, sniper, store, mock_client, mock_notifier):
        """Test run_job sends success notification on booking."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES999',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )

        result = sniper.run_job(job_id)

        assert result['outcome'] == 'booked'
        assert result['time'] == '7:00 PM'
        mock_notifier.notify_success.assert_called_once()

        job = store.get_sniper_job(job_id)
        assert job['status'] == 'completed'
        assert job['reservation_id'] is not None

    @patch('utils.reservation_sniper.time.sleep')
    def test_run_job_not_found(self, mock_sleep, sniper):
        """Test run_job with invalid job ID."""
        result = sniper.run_job(999)
        assert result['outcome'] == 'failed'
        assert 'not found' in result['reason']

    @patch('utils.reservation_sniper.time.sleep')
    def test_run_scheduled_jobs_picks_up_due_jobs(self, mock_sleep, sniper, store, mock_client, mock_notifier):
        """Test run_scheduled_jobs only runs jobs past scheduled_at."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES100',
        }

        # Past job — should run
        sniper.create_job(
            venue_slug='test-past', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        # Future job — should NOT run
        sniper.create_job(
            venue_slug='test-future', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2099-01-01T00:00:00',
        )

        result = sniper.run_scheduled_jobs()

        assert result['jobs_run'] == 1
        # The future job should still be pending
        future_jobs = [j for j in store.get_all_sniper_jobs() if j['venue_slug'] == 'test-future']
        assert future_jobs[0]['status'] == 'pending'

    @patch('utils.reservation_sniper.time.sleep')
    def test_run_scheduled_jobs_no_pending(self, mock_sleep, sniper):
        """Test run_scheduled_jobs with no pending jobs."""
        result = sniper.run_scheduled_jobs()
        assert result['jobs_run'] == 0

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_availability_exception(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once handles exceptions from get_availability."""
        mock_client.get_availability.side_effect = Exception("Connection timeout")

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is False
        assert 'Connection timeout' in result['error']

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_booking_exception(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once handles exceptions from make_reservation."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        mock_client.make_reservation.side_effect = Exception("Network error")

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is False
        assert 'Network error' in result['error']

    @patch('utils.reservation_sniper.time.sleep')
    def test_shutdown_pauses_job(self, mock_sleep, sniper, store, mock_client):
        """Test run_job returns 'shutdown' and reverts status when shutdown is set."""
        mock_client.get_availability.return_value = []

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            scheduled_at='2020-01-01T00:00:00',
        )
        # Set shutdown flag before running so the loop exits immediately
        sniper._shutdown = True

        result = sniper.run_job(job_id)

        assert result['outcome'] == 'shutdown'
        job = store.get_sniper_job(job_id)
        assert job['status'] == 'pending'

    def test_close_cleans_up_resources(self, store, mock_notifier):
        """Test close() calls _cleanup on client and close on store."""
        mock_client = MagicMock()
        mock_client._cleanup = MagicMock()
        mock_store = MagicMock()

        sniper = ReservationSniper(
            client=mock_client, store=mock_store, notifier=mock_notifier,
        )
        sniper.close()

        mock_client._cleanup.assert_called_once()
        mock_store.close.assert_called_once()

    def test_context_manager_calls_close(self, store, mock_notifier):
        """Test that using 'with' block calls close on exit."""
        mock_client = MagicMock()
        mock_client._cleanup = MagicMock()
        mock_store = MagicMock()

        with ReservationSniper(
            client=mock_client, store=mock_store, notifier=mock_notifier,
        ) as sniper:
            assert sniper is not None

        mock_client._cleanup.assert_called_once()
        mock_store.close.assert_called_once()

    def test_create_job_invalid_scheduled_at(self, sniper):
        """Test create_job raises ValueError for invalid scheduled_at."""
        with pytest.raises(ValueError, match="Invalid scheduled_at"):
            sniper.create_job(
                venue_slug='test',
                date='2026-03-01',
                preferred_times=['7:00 PM'],
                scheduled_at='not-a-date',
            )

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_conflict_no_auto_resolve(self, mock_sleep, sniper, store, mock_client):
        """Test _poll_once returns error on conflict when auto_resolve is off."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'test|||2026-03-01|||7:00 PM'},
        ]
        mock_client.make_reservation.return_value = {
            'success': False,
            'status': 'conflict',
        }

        job_id = sniper.create_job(
            venue_slug='test', date='2026-03-01', preferred_times=['7:00 PM'],
            auto_resolve_conflicts=False, scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is False
        mock_client.resolve_reservation_conflict.assert_not_called()

    @patch('utils.reservation_sniper.time.sleep')
    def test_poll_once_conflict_resolve_parse_failure(self, mock_sleep, sniper, store, mock_client):
        """Test conflict resolution falls back to job venue_slug when config_id parse fails."""
        mock_client.get_availability.return_value = [
            {'time': '7:00 PM', 'config_id': 'bad-config-id'},
        ]
        mock_client.make_reservation.return_value = {
            'success': False,
            'status': 'conflict',
        }
        mock_client.resolve_reservation_conflict.return_value = {
            'success': True,
            'reservation_id': 'RES999',
        }

        job_id = sniper.create_job(
            venue_slug='test-venue', date='2026-03-01', preferred_times=['7:00 PM'],
            auto_resolve_conflicts=True, scheduled_at='2020-01-01T00:00:00',
        )
        job = store.get_sniper_job(job_id)
        result = sniper._poll_once(job)

        assert result['booked'] is True
        # Verify fallback used job's venue_slug
        call_kwargs = mock_client.resolve_reservation_conflict.call_args[1]
        assert call_kwargs['venue_slug'] == 'test-venue'

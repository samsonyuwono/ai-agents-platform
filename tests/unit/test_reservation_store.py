"""Unit tests for ReservationStore."""

import pytest
import os
import tempfile
from datetime import datetime, timedelta
from utils.reservation_store import ReservationStore


class TestReservationStore:
    """Test ReservationStore CRUD operations."""

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
    def sample_reservation(self):
        """Sample reservation data."""
        return {
            'platform': 'resy',
            'restaurant_name': 'Test Restaurant',
            'date': '2026-03-01',
            'time': '7:00 PM',
            'party_size': 2,
            'confirmation_number': 'CONF123',
            'confirmation_token': 'TOKEN456',
            'status': 'confirmed',
        }

    def test_add_reservation(self, store, sample_reservation):
        """Test adding a reservation."""
        res_id = store.add_reservation(sample_reservation)

        assert res_id is not None
        assert res_id > 0

    def test_get_reservation_by_id(self, store, sample_reservation):
        """Test retrieving a reservation by ID."""
        res_id = store.add_reservation(sample_reservation)

        result = store.get_reservation_by_id(res_id)

        assert result is not None
        assert result['restaurant_name'] == 'Test Restaurant'
        assert result['platform'] == 'resy'
        assert result['party_size'] == 2
        assert result['confirmation_number'] == 'CONF123'

    def test_get_reservation_not_found(self, store):
        """Test retrieving a non-existent reservation."""
        result = store.get_reservation_by_id(999)
        assert result is None

    def test_get_reservations_no_filter(self, store, sample_reservation):
        """Test getting all reservations."""
        store.add_reservation(sample_reservation)
        store.add_reservation({**sample_reservation, 'restaurant_name': 'Another Restaurant'})

        results = store.get_reservations()

        assert len(results) == 2

    def test_get_reservations_with_platform_filter(self, store, sample_reservation):
        """Test filtering reservations by platform."""
        store.add_reservation(sample_reservation)
        store.add_reservation({**sample_reservation, 'platform': 'opentable'})

        results = store.get_reservations({'platform': 'resy'})

        assert len(results) == 1
        assert results[0]['platform'] == 'resy'

    def test_get_reservations_with_status_filter(self, store, sample_reservation):
        """Test filtering reservations by status."""
        store.add_reservation(sample_reservation)
        store.add_reservation({**sample_reservation, 'status': 'cancelled'})

        results = store.get_reservations({'status': 'confirmed'})

        assert len(results) == 1
        assert results[0]['status'] == 'confirmed'

    def test_update_reservation_status(self, store, sample_reservation):
        """Test updating reservation status."""
        res_id = store.add_reservation(sample_reservation)

        success = store.update_reservation_status(res_id, 'cancelled')

        assert success is True
        result = store.get_reservation_by_id(res_id)
        assert result['status'] == 'cancelled'

    def test_update_reservation_status_with_notes(self, store, sample_reservation):
        """Test updating reservation status with notes."""
        res_id = store.add_reservation(sample_reservation)

        success = store.update_reservation_status(res_id, 'cancelled', notes='Changed plans')

        assert success is True
        result = store.get_reservation_by_id(res_id)
        assert result['status'] == 'cancelled'
        assert result['notes'] == 'Changed plans'

    def test_update_nonexistent_reservation(self, store):
        """Test updating a non-existent reservation returns False."""
        success = store.update_reservation_status(999, 'cancelled')
        assert success is False

    def test_delete_reservation(self, store, sample_reservation):
        """Test deleting a reservation."""
        res_id = store.add_reservation(sample_reservation)

        success = store.delete_reservation(res_id)

        assert success is True
        result = store.get_reservation_by_id(res_id)
        assert result is None

    def test_delete_nonexistent_reservation(self, store):
        """Test deleting a non-existent reservation returns False."""
        success = store.delete_reservation(999)
        assert success is False

    def test_context_manager(self, sample_reservation):
        """Test context manager usage."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            with ReservationStore(db_path=db_path) as store:
                res_id = store.add_reservation(sample_reservation)
                assert res_id > 0

            # Verify connection was closed (store.conn should be closed)
            # Re-open to verify data persisted
            store2 = ReservationStore(db_path=db_path)
            result = store2.get_reservation_by_id(res_id)
            assert result is not None
            store2.close()
        finally:
            os.unlink(db_path)

    def test_timestamps_set(self, store, sample_reservation):
        """Test that created_at and updated_at are set."""
        res_id = store.add_reservation(sample_reservation)

        result = store.get_reservation_by_id(res_id)

        assert result['created_at'] is not None
        assert result['updated_at'] is not None


class TestSniperJobs:
    """Test sniper_jobs table operations."""

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
    def sample_job(self):
        """Sample sniper job data."""
        return {
            'venue_slug': 'fish-cheeks',
            'date': '2026-03-01',
            'preferred_times': ['7:00 PM', '7:30 PM'],
            'party_size': 2,
            'time_window_minutes': 60,
            'max_attempts': 60,
            'scheduled_at': '2026-02-22T09:00:00',
            'auto_resolve_conflicts': True,
            'notes': 'Test sniper job',
        }

    def test_add_sniper_job(self, store, sample_job):
        """Test creating a sniper job."""
        job_id = store.add_sniper_job(sample_job)

        assert job_id is not None
        assert job_id > 0

    def test_get_sniper_job(self, store, sample_job):
        """Test retrieving a sniper job by ID."""
        job_id = store.add_sniper_job(sample_job)
        job = store.get_sniper_job(job_id)

        assert job is not None
        assert job['venue_slug'] == 'fish-cheeks'
        assert job['date'] == '2026-03-01'
        assert job['preferred_times'] == ['7:00 PM', '7:30 PM']
        assert job['party_size'] == 2
        assert job['status'] == 'pending'
        assert job['poll_count'] == 0
        assert job['auto_resolve_conflicts'] is True
        assert job['notes'] == 'Test sniper job'

    def test_get_sniper_job_not_found(self, store):
        """Test retrieving a non-existent sniper job."""
        assert store.get_sniper_job(999) is None

    def test_get_pending_sniper_jobs(self, store, sample_job):
        """Test getting pending jobs whose scheduled_at has passed."""
        # Past job — should be returned
        past_job = {**sample_job, 'scheduled_at': '2020-01-01T09:00:00'}
        past_id = store.add_sniper_job(past_job)

        # Future job — should NOT be returned
        future_job = {**sample_job, 'scheduled_at': '2099-01-01T09:00:00'}
        store.add_sniper_job(future_job)

        pending = store.get_pending_sniper_jobs()
        assert len(pending) == 1
        assert pending[0]['id'] == past_id

    def test_get_pending_excludes_non_pending(self, store, sample_job):
        """Test that completed/failed jobs are excluded."""
        past_job = {**sample_job, 'scheduled_at': '2020-01-01T09:00:00'}
        job_id = store.add_sniper_job(past_job)
        store.update_sniper_job(job_id, {'status': 'completed'})

        pending = store.get_pending_sniper_jobs()
        assert len(pending) == 0

    def test_update_sniper_job(self, store, sample_job):
        """Test updating sniper job fields."""
        job_id = store.add_sniper_job(sample_job)

        success = store.update_sniper_job(job_id, {'status': 'active', 'notes': 'Running'})
        assert success is True

        job = store.get_sniper_job(job_id)
        assert job['status'] == 'active'
        assert job['notes'] == 'Running'

    def test_update_sniper_job_not_found(self, store):
        """Test updating a non-existent job returns False."""
        assert store.update_sniper_job(999, {'status': 'active'}) is False

    def test_update_sniper_job_empty_updates(self, store, sample_job):
        """Test updating with empty dict returns False."""
        job_id = store.add_sniper_job(sample_job)
        assert store.update_sniper_job(job_id, {}) is False

    def test_increment_poll_count(self, store, sample_job):
        """Test incrementing poll count."""
        job_id = store.add_sniper_job(sample_job)

        store.increment_poll_count(job_id)
        store.increment_poll_count(job_id)
        store.increment_poll_count(job_id)

        job = store.get_sniper_job(job_id)
        assert job['poll_count'] == 3

    def test_get_all_sniper_jobs(self, store, sample_job):
        """Test listing all sniper jobs."""
        store.add_sniper_job(sample_job)
        store.add_sniper_job({**sample_job, 'venue_slug': 'temple-court'})

        jobs = store.get_all_sniper_jobs()
        assert len(jobs) == 2

    def test_sniper_job_reservation_link(self, store, sample_job):
        """Test linking a sniper job to a reservation."""
        job_id = store.add_sniper_job(sample_job)

        res_id = store.add_reservation({
            'platform': 'resy',
            'restaurant_name': 'Fish Cheeks',
            'date': '2026-03-01',
            'time': '7:00 PM',
            'party_size': 2,
        })

        store.update_sniper_job(job_id, {
            'status': 'completed',
            'reservation_id': res_id,
        })

        job = store.get_sniper_job(job_id)
        assert job['status'] == 'completed'
        assert job['reservation_id'] == res_id

    def test_claim_next_sniper_job_returns_due_job(self, store, sample_job):
        """Test claiming a pending job whose scheduled_at has passed."""
        past_job = {**sample_job, 'scheduled_at': '2020-01-01T09:00:00'}
        job_id = store.add_sniper_job(past_job)

        claimed = store.claim_next_sniper_job()

        assert claimed is not None
        assert claimed['id'] == job_id
        assert claimed['status'] == 'active'

    def test_claim_next_sniper_job_skips_future(self, store, sample_job):
        """Test that future jobs are not claimed."""
        future_job = {**sample_job, 'scheduled_at': '2099-01-01T09:00:00'}
        store.add_sniper_job(future_job)

        claimed = store.claim_next_sniper_job()
        assert claimed is None

    def test_claim_next_sniper_job_skips_already_active(self, store, sample_job):
        """Test that already-active jobs are not claimed."""
        past_job = {**sample_job, 'scheduled_at': '2020-01-01T09:00:00'}
        job_id = store.add_sniper_job(past_job)
        store.update_sniper_job(job_id, {'status': 'active'})

        claimed = store.claim_next_sniper_job()
        assert claimed is None

    def test_increment_poll_count_nonexistent(self, store):
        """Test incrementing poll count for a nonexistent job returns False."""
        result = store.increment_poll_count(99999)
        assert result is False

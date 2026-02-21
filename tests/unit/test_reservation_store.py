"""Unit tests for ReservationStore."""

import pytest
import os
import tempfile
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

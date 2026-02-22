"""Unit tests for availability_filter module."""

import pytest
from utils.availability_filter import parse_time, filter_slots_by_time, pick_best_slot


class TestParseTime:
    """Test time string parsing."""

    def test_parse_standard_format(self):
        result = parse_time("7:00 PM")
        assert result is not None
        assert result.hour == 19
        assert result.minute == 0

    def test_parse_morning_time(self):
        result = parse_time("10:30 AM")
        assert result is not None
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_no_space(self):
        result = parse_time("7:00PM")
        assert result is not None
        assert result.hour == 19

    def test_parse_with_whitespace(self):
        result = parse_time("  7:00 PM  ")
        assert result is not None
        assert result.hour == 19

    def test_parse_invalid_returns_none(self):
        assert parse_time("invalid") is None
        assert parse_time("") is None
        assert parse_time("25:00 PM") is None


class TestFilterSlotsByTime:
    """Test slot filtering and sorting."""

    @pytest.fixture
    def sample_slots(self):
        return [
            {'time': '6:00 PM', 'config_id': 'a'},
            {'time': '7:00 PM', 'config_id': 'b'},
            {'time': '7:30 PM', 'config_id': 'c'},
            {'time': '8:00 PM', 'config_id': 'd'},
            {'time': '9:00 PM', 'config_id': 'e'},
        ]

    def test_filters_within_window(self, sample_slots):
        result = filter_slots_by_time(sample_slots, ["7:00 PM"], window_minutes=30)
        times = [s['time'] for s in result]
        assert '7:00 PM' in times
        assert '7:30 PM' in times
        assert '9:00 PM' not in times

    def test_sorted_by_closeness(self, sample_slots):
        result = filter_slots_by_time(sample_slots, ["7:15 PM"], window_minutes=60)
        # 7:00 PM (15 min), 7:30 PM (15 min), 6:00 PM (75 min outside), 8:00 PM (45 min)
        assert result[0]['time'] in ('7:00 PM', '7:30 PM')  # Both 15 min away

    def test_empty_slots_returns_empty(self):
        assert filter_slots_by_time([], ["7:00 PM"]) == []

    def test_no_preferred_times_returns_all(self, sample_slots):
        result = filter_slots_by_time(sample_slots, [])
        assert len(result) == len(sample_slots)

    def test_no_matching_slots(self):
        slots = [{'time': '11:00 AM', 'config_id': 'a'}]
        result = filter_slots_by_time(slots, ["7:00 PM"], window_minutes=30)
        assert len(result) == 0


class TestPickBestSlot:
    """Test best slot selection."""

    @pytest.fixture
    def sample_slots(self):
        return [
            {'time': '6:00 PM', 'config_id': 'a'},
            {'time': '7:00 PM', 'config_id': 'b'},
            {'time': '7:30 PM', 'config_id': 'c'},
            {'time': '8:00 PM', 'config_id': 'd'},
        ]

    def test_exact_match_preferred(self, sample_slots):
        result = pick_best_slot(sample_slots, ["7:00 PM"])
        assert result['time'] == '7:00 PM'

    def test_falls_back_to_closest(self, sample_slots):
        result = pick_best_slot(sample_slots, ["7:15 PM"], window_minutes=60)
        assert result['time'] in ('7:00 PM', '7:30 PM')

    def test_no_preferred_returns_first(self, sample_slots):
        result = pick_best_slot(sample_slots, [])
        assert result == sample_slots[0]

    def test_empty_slots_returns_none(self):
        result = pick_best_slot([], ["7:00 PM"])
        assert result is None

    def test_outside_window_still_returns_closest(self):
        slots = [{'time': '11:00 AM', 'config_id': 'a'}, {'time': '12:00 PM', 'config_id': 'b'}]
        result = pick_best_slot(slots, ["7:00 PM"], window_minutes=30)
        # Outside window, but still returns closest overall
        assert result['time'] == '12:00 PM'

    def test_multiple_preferred_times(self, sample_slots):
        result = pick_best_slot(sample_slots, ["7:00 PM", "8:00 PM"])
        assert result['time'] == '7:00 PM'  # First preferred, exact match


class TestEdgeCases:
    """Test edge cases in filtering."""

    def test_filter_slots_unparseable_time_skipped(self):
        """Test that a slot with an unparseable time is silently dropped."""
        slots = [
            {'time': 'invalid', 'config_id': 'a'},
            {'time': '7:00 PM', 'config_id': 'b'},
        ]
        result = filter_slots_by_time(slots, ["7:00 PM"], window_minutes=60)
        assert len(result) == 1
        assert result[0]['time'] == '7:00 PM'

    def test_filter_all_preferred_unparseable_returns_all(self):
        """Test that if all preferred times are unparseable, all slots are returned."""
        slots = [
            {'time': '6:00 PM', 'config_id': 'a'},
            {'time': '7:00 PM', 'config_id': 'b'},
        ]
        result = filter_slots_by_time(slots, ["bad", "also_bad"], window_minutes=60)
        assert len(result) == 2

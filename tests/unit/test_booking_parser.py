"""Unit tests for booking request parsing."""

import pytest
from freezegun import freeze_time
from utils.booking_parser import BookingRequestParser, parse_booking_request


@freeze_time("2026-02-15")
class TestBookingRequestParser:
    """Test booking request parsing."""

    def test_parse_valid_request(self):
        """Test parsing a valid booking request."""
        result = parse_booking_request("Temple Court on Feb 18 at 6pm for 2 people")

        assert result['restaurant_name'] == 'Temple Court'
        assert result['restaurant_slug'] == 'temple-court'
        assert result['date'] == '2026-02-18'
        assert result['time'] == '6:00 PM'
        assert result['party_size'] == 2

    def test_parse_with_explicit_year(self):
        """Test parsing with explicit YYYY-MM-DD format."""
        result = parse_booking_request("Carbone on 2026-02-25 at 7:30pm for 4")

        assert result['restaurant_name'] == 'Carbone'
        assert result['date'] == '2026-02-25'
        assert result['time'] == '7:30 PM'
        assert result['party_size'] == 4

    def test_parse_party_of_format(self):
        """Test parsing 'party of X' format."""
        result = parse_booking_request("Don Angie on Feb 20 at 8pm party of 2")

        assert result['party_size'] == 2

    def test_parse_default_party_size(self):
        """Test default party size when not specified."""
        result = parse_booking_request("Le Bernardin on Feb 18 at 6pm")

        assert result['party_size'] == 2

    def test_parse_time_without_minutes(self):
        """Test parsing time without minutes (6pm vs 6:00pm)."""
        result = parse_booking_request("Temple Court on Feb 18 at 6pm for 2")

        assert result['time'] == '6:00 PM'

    def test_parse_time_with_minutes(self):
        """Test parsing time with minutes."""
        result = parse_booking_request("Temple Court on Feb 18 at 6:30pm for 2")

        assert result['time'] == '6:30 PM'

    def test_parse_noon(self):
        """Test parsing noon (12pm)."""
        result = parse_booking_request("Temple Court on Feb 18 at 12pm for 2")

        assert result['time'] == '12:00 PM'

    def test_parse_midnight(self):
        """Test parsing midnight (12am)."""
        result = parse_booking_request("Temple Court on Feb 18 at 12am for 2")

        assert result['time'] == '12:00 AM'

    def test_parse_missing_restaurant_name(self):
        """Test error handling for missing restaurant name."""
        with pytest.raises(ValueError, match="Could not find restaurant name"):
            parse_booking_request("on Feb 18 at 6pm for 2")

    def test_parse_missing_date(self):
        """Test error handling for missing date."""
        with pytest.raises(ValueError, match="Could not find date"):
            parse_booking_request("Temple Court on at 6pm for 2")

    def test_parse_missing_time(self):
        """Test error handling for missing time."""
        with pytest.raises(ValueError, match="Could not find time"):
            parse_booking_request("Temple Court on Feb 18 for 2")

    @pytest.mark.parametrize("month_name,expected_month,expected_year", [
        ("Jan", "01", "2027"),  # Past month, uses next year
        ("January", "01", "2027"),  # Past month, uses next year
        ("Feb", "02", "2026"),  # Current month, day 18 is in the future
        ("February", "02", "2026"),  # Current month, day 18 is in the future
        ("Dec", "12", "2026"),  # Future month
        ("December", "12", "2026"),  # Future month
    ])
    def test_parse_month_variations(self, month_name, expected_month, expected_year):
        """Test parsing different month name formats."""
        result = parse_booking_request(f"Temple Court on {month_name} 18 at 6pm for 2")

        assert result['date'].startswith(f"{expected_year}-{expected_month}")

    def test_parse_past_date_rolls_to_next_year(self):
        """Test that a date earlier in the current month rolls to next year."""
        # Feb 10 is in the past (frozen at Feb 15), should roll to 2027
        result = parse_booking_request("Temple Court on Feb 10 at 6pm for 2")
        assert result['date'] == '2027-02-10'

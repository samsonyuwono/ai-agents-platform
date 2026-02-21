"""Parse natural language booking requests."""

import re
from datetime import datetime
from typing import Dict, Optional
from utils.slug_utils import normalize_slug


class BookingRequestParser:
    """Parse natural language booking requests."""

    MONTH_MAP = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }

    @staticmethod
    def parse(request_text: str) -> Dict:
        """
        Parse a natural language booking request.

        Args:
            request_text: Natural language request like
                "Temple Court on Feb 18 at 6pm for 2 people"

        Returns:
            Dictionary with:
                - restaurant_name: str
                - restaurant_slug: str
                - date: str (YYYY-MM-DD)
                - time: str (12-hour format with AM/PM)
                - party_size: int

        Raises:
            ValueError: If required fields cannot be parsed

        Examples:
            >>> parse("Temple Court on Feb 18 at 6pm for 2")
            {
                'restaurant_name': 'Temple Court',
                'restaurant_slug': 'temple-court',
                'date': '2026-02-18',
                'time': '6:00 PM',
                'party_size': 2
            }
        """
        request_lower = request_text.lower()

        # Extract restaurant name
        restaurant_match = re.search(r'^(.+?)\s+on\s+', request_text, re.IGNORECASE)
        if not restaurant_match:
            raise ValueError("Could not find restaurant name (use format: 'Restaurant on date at time')")

        restaurant_name = restaurant_match.group(1).strip()
        restaurant_slug = normalize_slug(restaurant_name)

        # Extract date
        date = BookingRequestParser._parse_date(request_text, request_lower)

        # Extract time
        time = BookingRequestParser._parse_time(request_lower)

        # Extract party size
        party_size = BookingRequestParser._parse_party_size(request_lower)

        return {
            'restaurant_name': restaurant_name,
            'restaurant_slug': restaurant_slug,
            'date': date,
            'time': time,
            'party_size': party_size
        }

    @staticmethod
    def _parse_date(request_text: str, request_lower: str) -> str:
        """Parse date from request text."""
        # Try YYYY-MM-DD format first
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', request_text)
        if date_match:
            return date_match.group(0)

        # Try "Feb 18" or "February 18" format
        month_match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})', request_lower)
        if month_match:
            month_name = month_match.group(1)
            day = month_match.group(2).zfill(2)
            month = BookingRequestParser.MONTH_MAP.get(month_name[:3])

            # Assume current or next year
            current_year = datetime.now().year
            date = f"{current_year}-{month}-{day}"

            # Check if date is in the past, if so use next year
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                if date_obj < datetime.now():
                    date = f"{current_year + 1}-{month}-{day}"
            except:
                pass

            return date

        raise ValueError("Could not find date (use format: 'Feb 18' or '2026-02-18')")

    @staticmethod
    def _parse_time(request_lower: str) -> str:
        """Parse time from request text."""
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', request_lower)
        if not time_match:
            raise ValueError("Could not find time (use format: '6pm' or '7:30pm')")

        hour = int(time_match.group(1))
        minute = time_match.group(2) or '00'
        meridiem = time_match.group(3).upper()

        # Convert to 12-hour format
        if meridiem == 'PM' and hour != 12:
            hour_12 = hour
        elif meridiem == 'AM' and hour == 12:
            hour_12 = 12
        else:
            hour_12 = hour

        return f"{hour_12}:{minute} {meridiem}"

    @staticmethod
    def _parse_party_size(request_lower: str) -> int:
        """Parse party size from request text."""
        party_match = re.search(r'for\s+(\d+)', request_lower)
        if party_match:
            return int(party_match.group(1))

        party_match = re.search(r'party\s+of\s+(\d+)', request_lower)
        if party_match:
            return int(party_match.group(1))

        return 2  # Default to 2


def parse_booking_request(request_text: str) -> Dict:
    """Convenience function for parsing booking requests."""
    return BookingRequestParser.parse(request_text)

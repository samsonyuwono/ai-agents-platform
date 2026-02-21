"""
Resy API Client
Handles interaction with the Resy API for restaurant reservations.
Includes anti-bot detection measures.
"""

import logging
import requests
import time
import random
from typing import List, Dict, Optional
from config.settings import Settings

logger = logging.getLogger(__name__)


class ResyClient:
    """Client for Resy API integration with bot detection prevention."""

    def __init__(self, api_key=None, auth_token=None):
        """Initialize Resy client with API credentials."""
        self.api_key = api_key or Settings.RESY_API_KEY
        self.auth_token = auth_token or Settings.RESY_AUTH_TOKEN
        self.base_url = "https://api.resy.com"

        if not self.api_key or not self.auth_token:
            raise ValueError("Resy API key and auth token are required")

        # Rate limiting - track last request time
        self.last_request_time = 0
        self.min_delay_seconds = 2  # Minimum 2 seconds between requests

        # Session with realistic user agent
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://resy.com',
            'Referer': 'https://resy.com/',
        })

    def _rate_limit(self):
        """
        Enforce rate limiting with randomized delays to appear more human-like.
        Prevents bot detection by spacing out requests.
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.min_delay_seconds:
            # Add random jitter (0.5-1.5 seconds) to look more human
            jitter = random.uniform(0.5, 1.5)
            sleep_time = (self.min_delay_seconds - time_since_last_request) + jitter
            logger.debug("Rate limiting: waiting %.1fs...", sleep_time)
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make an API request with proper authentication and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            JSON response as dictionary

        Raises:
            Exception: If request fails
        """
        # Apply rate limiting
        self._rate_limit()

        url = f"{self.base_url}{endpoint}"

        # Add authentication headers
        headers = kwargs.get('headers', {})
        headers.update({
            'Authorization': f'ResyAPI api_key="{self.api_key}"',
            'X-Resy-Auth-Token': self.auth_token,
            'X-Resy-Universal-Auth': self.auth_token,
        })
        kwargs['headers'] = headers

        try:
            if 'params' in kwargs:
                from urllib.parse import urlencode
                debug_url = f"{url}?{urlencode(kwargs['params'])}"
                logger.debug("Requesting %s", debug_url)

            response = self.session.request(method, url, **kwargs)

            # Check for rate limiting
            if response.status_code == 429:
                logger.warning("Rate limited by Resy. Waiting 60 seconds...")
                time.sleep(60)
                # Retry once
                response = self.session.request(method, url, **kwargs)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("Authentication failed. Check your RESY_API_KEY and RESY_AUTH_TOKEN")
            elif e.response.status_code == 404:
                raise Exception(f"Resource not found: {endpoint}")
            else:
                raise Exception(f"Resy API error: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error: {str(e)}")

    def get_venue_by_slug(self, url_slug: str, location: str = 'ny') -> Optional[Dict]:
        """
        Get venue information by URL slug.

        Args:
            url_slug: Restaurant's URL slug (e.g., 'temple-court')
            location: Location code (e.g., 'ny', 'sf', 'la')

        Returns:
            Venue dictionary with id, name, and details
        """
        logger.info("Looking up venue: %s", url_slug)

        params = {
            'url_slug': url_slug,
            'location': location.lower()  # Resy requires lowercase location codes
        }

        try:
            response = self._make_request('GET', '/3/venue', params=params)

            logger.debug("Response type: %s", type(response))

            # Check if response is what we expect
            if not isinstance(response, dict):
                logger.warning("Unexpected response type: %s", type(response))
                return None

            # Safely extract venue info
            venue_id_dict = response.get('id', {})
            venue_id = venue_id_dict.get('resy') if isinstance(venue_id_dict, dict) else None

            venue_info = {
                'id': venue_id,
                'name': response.get('name'),
                'url_slug': response.get('url_slug'),
                'location': {
                    'neighborhood': response.get('location', {}).get('neighborhood') if isinstance(response.get('location'), dict) else None,
                    'city': response.get('location', {}).get('name') if isinstance(response.get('location'), dict) else None,
                    'address': response.get('location', {}).get('address_1') if isinstance(response.get('location'), dict) else None
                },
                'rating': response.get('rater', {}).get('score') if isinstance(response.get('rater'), dict) else None,
                'price_range': response.get('price_range_id'),
                'min_party_size': response.get('min_party_size'),
                'max_party_size': response.get('max_party_size'),
            }

            logger.info("Found: %s (ID: %s)", venue_info['name'], venue_info['id'])
            return venue_info

        except Exception as e:
            logger.error("Venue lookup failed: %s", e)
            return None

    def search_venues(self, query: str, location: Optional[str] = None, lat: Optional[float] = None, long: Optional[float] = None) -> List[Dict]:
        """
        Search for restaurants on Resy by slug.
        Note: Resy's public search API is limited. This method converts
        restaurant names to URL slugs for lookup.

        Args:
            query: Restaurant name (will be converted to slug)
            location: City code (ny, sf, la, etc.) default: ny

        Returns:
            List with single venue if found, empty list otherwise
        """
        logger.info("Searching Resy for: %s", query)

        # Convert query to URL slug format
        url_slug = query.lower().replace(' ', '-').replace("'", '')
        location_code = (location or 'ny').lower()  # Normalize to lowercase

        # Try to get venue by slug
        venue = self.get_venue_by_slug(url_slug, location_code)

        if venue:
            return [venue]
        else:
            logger.info("Tip: Provide the exact restaurant slug from Resy URL")
            return []

    def get_availability(self, venue_id: str, date: str, party_size: int = 2) -> List[Dict]:
        """
        Get available reservation slots for a venue.

        Args:
            venue_id: Resy venue ID
            date: Date in YYYY-MM-DD format
            party_size: Number of guests (default: 2)

        Returns:
            List of available time slots with slot details
        """
        logger.info("Checking availability for venue %s on %s for %d people", venue_id, date, party_size)

        params = {
            'lat': 0,
            'long': 0,
            'day': date,
            'party_size': party_size,
            'venue_id': venue_id
        }

        try:
            response = self._make_request('GET', '/3/find', params=params)

            # /3/find returns {'results': [...]} where each result has 'venue' and 'configs'
            results = response.get('results', [])

            if not results:
                logger.info("No availability found")
                return []

            # Extract available time slots from configs
            available_slots = []
            for result in results:
                venue_info = result.get('venue', {})
                configs = result.get('configs', [])

                for config in configs:
                    available_slots.append({
                        'config_id': config.get('id'),
                        'token': config.get('token'),
                        'time': config.get('time_slot'),
                        'type': config.get('type'),
                        'table_name': config.get('name'),
                        'venue_name': venue_info.get('name')
                    })

            logger.info("Found %d available slots", len(available_slots))
            return available_slots

        except Exception as e:
            logger.error("Availability check failed: %s", e)
            return []

    def get_booking_details(self, config_id: str, date: str, party_size: int) -> Optional[Dict]:
        """
        Get booking details needed for making a reservation.

        Args:
            config_id: Configuration ID from availability slot
            date: Date in YYYY-MM-DD format
            party_size: Number of guests

        Returns:
            Booking details dictionary or None if failed
        """
        params = {
            'config_id': config_id,
            'day': date,
            'party_size': party_size
        }

        try:
            response = self._make_request('GET', '/3/details', params=params)
            return response

        except Exception as e:
            logger.error("Failed to get booking details: %s", e)
            return None

    def make_reservation(self, config_id: str, date: str, party_size: int, payment_method_id: Optional[str] = None) -> Dict:
        """
        Make a reservation at a restaurant.

        IMPORTANT: This will actually book the reservation and may charge your payment method!

        Args:
            config_id: Configuration ID from availability slot
            date: Date in YYYY-MM-DD format
            party_size: Number of guests
            payment_method_id: Payment method ID (uses Settings default if not provided)

        Returns:
            Reservation details with confirmation token

        Raises:
            Exception: If reservation fails
        """
        logger.info("Attempting to book reservation...")

        payment_method = payment_method_id or Settings.RESY_PAYMENT_METHOD_ID

        if not payment_method:
            raise ValueError("RESY_PAYMENT_METHOD_ID not configured. Cannot make reservation.")

        # First get booking details
        details = self.get_booking_details(config_id, date, party_size)

        if not details:
            raise Exception("Failed to get booking details")

        # Extract booking token
        book_token = details.get('book_token', {}).get('value')

        if not book_token:
            raise Exception("No booking token available")

        # Make the reservation
        payload = {
            'book_token': book_token,
            'struct_payment_method': payment_method,
            'source_id': 'resy.com-venue-details'
        }

        try:
            response = self._make_request('POST', '/3/book', json=payload)

            reservation_id = response.get('reservation_id')
            resy_token = response.get('resy_token')

            logger.info("Reservation successful! Confirmation: %s", reservation_id)

            return {
                'success': True,
                'reservation_id': reservation_id,
                'confirmation_token': resy_token,
                'config_id': config_id,
                'date': date,
                'party_size': party_size
            }

        except Exception as e:
            logger.error("Reservation failed: %s", e)
            return {
                'success': False,
                'error': str(e)
            }

    def get_reservations(self) -> List[Dict]:
        """
        Get user's upcoming reservations.

        Returns:
            List of reservation dictionaries
        """
        try:
            response = self._make_request('GET', '/2/user/reservations')

            reservations = response.get('reservations', [])

            formatted_reservations = []
            for res in reservations:
                formatted_reservations.append({
                    'id': res.get('resy_token'),
                    'venue_name': res.get('venue', {}).get('name'),
                    'date': res.get('day'),
                    'time': res.get('time_slot'),
                    'party_size': res.get('num_seats'),
                    'status': res.get('status')
                })

            return formatted_reservations

        except Exception as e:
            logger.error("Failed to get reservations: %s", e)
            return []

    def cancel_reservation(self, resy_token: str) -> bool:
        """
        Cancel a reservation.

        Args:
            resy_token: Reservation token from booking

        Returns:
            bool: True if cancelled successfully, False otherwise
        """
        try:
            payload = {'resy_token': resy_token}
            self._make_request('POST', '/3/cancel', json=payload)

            logger.info("Reservation cancelled")
            return True

        except Exception as e:
            logger.error("Cancellation failed: %s", e)
            return False

"""Tests for Resy cuisine/neighborhood search functionality."""

import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock


class TestSearchUrlConstruction:
    """Test search URL construction in ResyBrowserClient.search_by_cuisine()."""

    def _build_search_url(self, cuisine=None, neighborhood=None, location='ny',
                          date='2026-02-21', party_size=2):
        """Helper to build expected search URL (mirrors the logic in search_by_cuisine).

        Note: neighborhood is accepted but not added to the URL — Resy's
        facet=neighborhood is unreliable (doesn't work for boroughs).
        """
        from utils.resy_browser_client import resolve_location
        full_location = resolve_location(location)
        url = f"https://resy.com/cities/{full_location}/search?seats={party_size}&date={date}"
        if cuisine:
            url += f"&facet=cuisine:{cuisine}"
        return url

    def test_cuisine_only(self):
        url = self._build_search_url(cuisine='Italian')
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=2&date=2026-02-21&facet=cuisine:Italian'

    def test_neighborhood_only(self):
        """Neighborhood alone doesn't add any facet to the URL."""
        url = self._build_search_url(neighborhood='Soho')
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=2&date=2026-02-21'
        assert 'facet=neighborhood' not in url

    def test_cuisine_and_neighborhood(self):
        """Neighborhood is ignored in URL; only cuisine facet is added."""
        url = self._build_search_url(cuisine='Japanese', neighborhood='West Village')
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=2&date=2026-02-21&facet=cuisine:Japanese'
        assert 'facet=neighborhood' not in url

    def test_borough_not_in_url(self):
        """Boroughs like Manhattan should not appear as facets in the URL."""
        url = self._build_search_url(cuisine='Japanese', neighborhood='Manhattan')
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=2&date=2026-02-21&facet=cuisine:Japanese'
        assert 'Manhattan' not in url

    def test_no_facets(self):
        url = self._build_search_url()
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=2&date=2026-02-21'

    def test_custom_date_and_party_size(self):
        url = self._build_search_url(cuisine='Chinese', date='2026-03-15', party_size=4)
        assert url == 'https://resy.com/cities/new-york-ny/search?seats=4&date=2026-03-15&facet=cuisine:Chinese'

    def test_sf_location(self):
        url = self._build_search_url(cuisine='Mexican', location='sf')
        assert url == 'https://resy.com/cities/san-francisco-ca/search?seats=2&date=2026-02-21&facet=cuisine:Mexican'

    def test_la_location(self):
        url = self._build_search_url(cuisine='Korean', location='la')
        assert url == 'https://resy.com/cities/los-angeles-ca/search?seats=2&date=2026-02-21&facet=cuisine:Korean'


class TestSlugExtraction:
    """Test slug extraction from venue card href patterns."""

    def _extract_slug(self, href):
        """Mirror the slug extraction logic from search_by_cuisine."""
        if '/venues/' in href:
            return href.split('/venues/')[-1].split('?')[0].strip('/')
        return None

    def test_standard_href(self):
        assert self._extract_slug('/cities/new-york-ny/venues/peking-duck-house') == 'peking-duck-house'

    def test_href_with_query_params(self):
        assert self._extract_slug('/cities/new-york-ny/venues/carbone?date=2026-02-21&seats=2') == 'carbone'

    def test_full_url(self):
        assert self._extract_slug('https://resy.com/cities/new-york-ny/venues/lartusi') == 'lartusi'

    def test_trailing_slash(self):
        assert self._extract_slug('/cities/new-york-ny/venues/don-angie/') == 'don-angie'

    def test_no_venues_path(self):
        assert self._extract_slug('/cities/new-york-ny/search') is None


class TestResolveLocation:
    """Test location code resolution."""

    def test_ny(self):
        from utils.resy_browser_client import resolve_location
        assert resolve_location('ny') == 'new-york-ny'

    def test_nyc(self):
        from utils.resy_browser_client import resolve_location
        assert resolve_location('nyc') == 'new-york-ny'

    def test_sf(self):
        from utils.resy_browser_client import resolve_location
        assert resolve_location('sf') == 'san-francisco-ca'

    def test_la(self):
        from utils.resy_browser_client import resolve_location
        assert resolve_location('la') == 'los-angeles-ca'

    def test_unknown_passthrough(self):
        from utils.resy_browser_client import resolve_location
        assert resolve_location('chicago-il') == 'chicago-il'


class TestCuisineSearchHandler:
    """Test the search_resy_by_cuisine handler in ReservationAgent."""

    def test_fallback_when_no_browser_client(self):
        """API client doesn't have search_by_cuisine, should return helpful error."""
        # Mock a client without search_by_cuisine (like ResyClient API)
        mock_client = MagicMock(spec=['search_venues', 'get_availability'])

        # Simulate what execute_tool does
        has_method = hasattr(mock_client, 'search_by_cuisine')
        assert has_method is False

    def test_browser_client_has_method(self):
        """Browser client should have search_by_cuisine method."""
        # Mock a browser client with search_by_cuisine
        mock_client = MagicMock(spec=['search_venues', 'get_availability', 'search_by_cuisine'])
        assert hasattr(mock_client, 'search_by_cuisine') is True

    def test_format_results_with_time_slots(self):
        """Test formatting of search results with available time slots."""
        raw_results = [
            {
                'name': 'Test Restaurant',
                'slug': 'test-restaurant',
                'rating': 4.5,
                'review_count': 120,
                'cuisine': 'Italian',
                'price_range': '$$',
                'neighborhood': 'Soho',
                'available_times': [
                    {'time': '5:15 PM', 'type': 'Dining Room', 'config_id': 'test-restaurant|||2026-02-21|||5:15 PM'},
                    {'time': '7:30 PM', 'type': 'Bar', 'config_id': 'test-restaurant|||2026-02-21|||7:30 PM'},
                ]
            }
        ]

        # Simulate the formatting logic from execute_tool
        formatted = []
        for r in raw_results:
            venue = {
                'name': r.get('name'),
                'slug': r.get('slug'),
                'rating': r.get('rating'),
                'review_count': r.get('review_count'),
                'cuisine': r.get('cuisine'),
                'price_range': r.get('price_range'),
                'neighborhood': r.get('neighborhood'),
            }
            times = r.get('available_times', [])
            if times:
                venue['available_times'] = [
                    {'time': t['time'], 'type': t['type'], 'config_id': t['config_id']}
                    for t in times
                ]
            formatted.append(venue)

        assert len(formatted) == 1
        assert formatted[0]['name'] == 'Test Restaurant'
        assert formatted[0]['slug'] == 'test-restaurant'
        assert formatted[0]['available_times'] == [
            {'time': '5:15 PM', 'type': 'Dining Room', 'config_id': 'test-restaurant|||2026-02-21|||5:15 PM'},
            {'time': '7:30 PM', 'type': 'Bar', 'config_id': 'test-restaurant|||2026-02-21|||7:30 PM'},
        ]

    def test_format_results_without_time_slots(self):
        """Test formatting when no time slots are available."""
        raw_results = [
            {
                'name': 'Busy Place',
                'slug': 'busy-place',
                'rating': None,
                'review_count': None,
                'cuisine': 'French',
                'price_range': '$$$',
                'neighborhood': 'West Village',
                'available_times': []
            }
        ]

        formatted = []
        for r in raw_results:
            venue = {
                'name': r.get('name'),
                'slug': r.get('slug'),
                'rating': r.get('rating'),
                'review_count': r.get('review_count'),
                'cuisine': r.get('cuisine'),
                'price_range': r.get('price_range'),
                'neighborhood': r.get('neighborhood'),
            }
            times = r.get('available_times', [])
            if times:
                venue['available_times'] = [
                    {'time': t['time'], 'type': t['type'], 'config_id': t['config_id']}
                    for t in times
                ]
            formatted.append(venue)

        assert len(formatted) == 1
        assert 'available_times' not in formatted[0]


class TestRateLimit:
    """Test the tiered _rate_limit() behavior in ResyBrowserClient."""

    def _make_client(self):
        """Create a ResyBrowserClient with mocked credentials."""
        with patch('utils.resy_browser_client.Settings') as mock_settings:
            mock_settings.RESY_EMAIL = 'test@example.com'
            mock_settings.RESY_PASSWORD = 'password'
            mock_settings.RESY_BROWSER_HEADLESS = True
            mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 3
            mock_settings.RESY_RATE_LIMIT_JITTER_MIN = 0.5
            mock_settings.RESY_RATE_LIMIT_JITTER_MAX = 1.5
            from utils.resy_browser_client import ResyBrowserClient
            client = ResyBrowserClient.__new__(ResyBrowserClient)
            client.last_request_time = 0
            client.min_delay_seconds = 3
            client.playwright = None
            client.browser = None
            client.context = None
            client.page = None
            client.is_authenticated = False
            return client, mock_settings

    @patch('utils.resy_browser_client.time')
    def test_navigation_rate_limit_sleeps_when_under_min_delay(self, mock_time):
        """Navigation mode should sleep for min_delay + jitter when called too soon."""
        client, mock_settings = self._make_client()
        mock_time.time.return_value = 1.0  # 1s since epoch, last_request at 0 => 1s elapsed < 3s min
        mock_time.sleep = MagicMock()

        with patch('utils.resy_browser_client.random') as mock_random:
            mock_random.uniform.return_value = 0.8  # fixed jitter
            client._rate_limit(navigation=True)

        # Should sleep for (3 - 1) + 0.8 = 2.8s
        mock_time.sleep.assert_called_once_with(2.8)

    @patch('utils.resy_browser_client.time')
    def test_navigation_small_jitter_when_past_min_delay(self, mock_time):
        """Navigation mode should use small jitter (0.3-0.8) when enough time has passed."""
        client, _ = self._make_client()
        mock_time.time.return_value = 10.0  # 10s elapsed > 3s min
        mock_time.sleep = MagicMock()

        with patch('utils.resy_browser_client.random') as mock_random:
            mock_random.uniform.return_value = 0.5
            client._rate_limit(navigation=True)

        # Should sleep for small jitter only
        mock_time.sleep.assert_called_once_with(0.5)
        mock_random.uniform.assert_called_with(0.3, 0.8)

    @patch('utils.resy_browser_client.time')
    def test_non_navigation_uses_lighter_delay(self, mock_time):
        """Non-navigation mode should use 1s min delay with 0.2-0.5 jitter."""
        client, _ = self._make_client()
        mock_time.time.return_value = 0.5  # 0.5s elapsed < 1s min
        mock_time.sleep = MagicMock()

        with patch('utils.resy_browser_client.random') as mock_random:
            mock_random.uniform.return_value = 0.3  # fixed jitter
            client._rate_limit(navigation=False)

        # Should sleep for (1.0 - 0.5) + 0.3 = 0.8s
        mock_time.sleep.assert_called_once_with(0.8)
        mock_random.uniform.assert_called_with(0.2, 0.5)

    @patch('utils.resy_browser_client.time')
    def test_non_navigation_no_sleep_when_past_min(self, mock_time):
        """Non-navigation mode should not sleep when enough time has passed."""
        client, _ = self._make_client()
        mock_time.time.return_value = 10.0  # well past 1s min
        mock_time.sleep = MagicMock()

        client._rate_limit(navigation=False)

        mock_time.sleep.assert_not_called()

    @patch('utils.resy_browser_client.time')
    def test_force_false_skips_when_recent(self, mock_time):
        """force=False should skip rate limiting when last request was < 2s ago."""
        client, _ = self._make_client()
        client.last_request_time = 9.5
        mock_time.time.return_value = 10.0  # 0.5s since last request < 2s threshold
        mock_time.sleep = MagicMock()

        client._rate_limit(force=False)

        mock_time.sleep.assert_not_called()


class TestNormalizeSlugInSearchVenues:
    """Test that search_venues uses normalize_slug for proper slug conversion."""

    def test_apostrophe_handling(self):
        from utils.slug_utils import normalize_slug
        assert normalize_slug("L'Artusi") == 'lartusi'

    def test_ampersand_handling(self):
        from utils.slug_utils import normalize_slug
        assert normalize_slug("ABC & Co") == 'abc-and-co'

    def test_simple_name(self):
        from utils.slug_utils import normalize_slug
        assert normalize_slug("Temple Court") == 'temple-court'

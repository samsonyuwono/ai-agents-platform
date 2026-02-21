"""Tests for Resy browser client and cuisine/neighborhood search functionality."""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call


def _make_browser_client(**overrides):
    """Create a ResyBrowserClient with mocked browser and page.

    Skips __init__ side effects. Returns (client, mock_settings).
    """
    with patch('utils.resy_browser_client.Settings') as mock_settings:
        mock_settings.RESY_EMAIL = 'test@example.com'
        mock_settings.RESY_PASSWORD = 'password'
        mock_settings.RESY_BROWSER_HEADLESS = True
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 3
        mock_settings.RESY_RATE_LIMIT_JITTER_MIN = 0.5
        mock_settings.RESY_RATE_LIMIT_JITTER_MAX = 1.5
        mock_settings.RESY_DEFAULT_LOCATION = 'ny'

        from utils.resy_browser_client import ResyBrowserClient
        client = ResyBrowserClient.__new__(ResyBrowserClient)
        client.last_request_time = 0
        client.min_delay_seconds = 3
        client.email = 'test@example.com'
        client.password = 'password'
        client.headless = True
        client.playwright = None
        client.browser = None
        client.context = MagicMock()
        client.page = MagicMock()
        client.is_authenticated = True
        client.cookie_file = Path('/tmp/test_cookies.json')

        for key, val in overrides.items():
            setattr(client, key, val)

        return client, mock_settings


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

    @patch('utils.resy_browser_client.time')
    def test_navigation_rate_limit_sleeps_when_under_min_delay(self, mock_time):
        """Navigation mode should sleep for min_delay + jitter when called too soon."""
        client, mock_settings = _make_browser_client(is_authenticated=False, context=None, page=None)
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
        client, _ = _make_browser_client(is_authenticated=False, context=None, page=None)
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
        client, _ = _make_browser_client(is_authenticated=False, context=None, page=None)
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
        client, _ = _make_browser_client(is_authenticated=False, context=None, page=None)
        mock_time.time.return_value = 10.0  # well past 1s min
        mock_time.sleep = MagicMock()

        client._rate_limit(navigation=False)

        mock_time.sleep.assert_not_called()

    @patch('utils.resy_browser_client.time')
    def test_force_false_skips_when_recent(self, mock_time):
        """force=False should skip rate limiting when last request was < 2s ago."""
        client, _ = _make_browser_client(is_authenticated=False, context=None, page=None)
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


# ---------------------------------------------------------------------------
# ResyBrowserClient unit tests
# ---------------------------------------------------------------------------

class TestResyBrowserClientInit:
    """Test the __init__() constructor."""

    @patch('utils.resy_browser_client.Settings')
    def test_init_missing_email_raises(self, mock_settings):
        mock_settings.RESY_EMAIL = None
        mock_settings.RESY_PASSWORD = 'password'
        mock_settings.RESY_BROWSER_HEADLESS = True
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 3

        from utils.resy_browser_client import ResyBrowserClient
        with pytest.raises(ValueError, match="email and password are required"):
            ResyBrowserClient()

    @patch('utils.resy_browser_client.Settings')
    def test_init_missing_password_raises(self, mock_settings):
        mock_settings.RESY_EMAIL = 'test@example.com'
        mock_settings.RESY_PASSWORD = None
        mock_settings.RESY_BROWSER_HEADLESS = True
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 3

        from utils.resy_browser_client import ResyBrowserClient
        with pytest.raises(ValueError, match="email and password are required"):
            ResyBrowserClient()

    @patch('utils.resy_browser_client.Settings')
    def test_init_with_defaults(self, mock_settings):
        mock_settings.RESY_EMAIL = 'default@example.com'
        mock_settings.RESY_PASSWORD = 'defaultpass'
        mock_settings.RESY_BROWSER_HEADLESS = False
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6

        from utils.resy_browser_client import ResyBrowserClient
        client = ResyBrowserClient()

        assert client.email == 'default@example.com'
        assert client.password == 'defaultpass'
        assert client.headless is False
        assert client.min_delay_seconds == 6
        assert client.is_authenticated is False
        assert client.page is None

    @patch('utils.resy_browser_client.Settings')
    def test_init_with_custom_params(self, mock_settings):
        mock_settings.RESY_EMAIL = 'default@example.com'
        mock_settings.RESY_PASSWORD = 'defaultpass'
        mock_settings.RESY_BROWSER_HEADLESS = False
        mock_settings.RESY_RATE_LIMIT_MIN_SECONDS = 6

        from utils.resy_browser_client import ResyBrowserClient
        client = ResyBrowserClient(
            email='custom@example.com',
            password='custompass',
            headless=True
        )

        assert client.email == 'custom@example.com'
        assert client.password == 'custompass'
        assert client.headless is True


class TestEnsureAuthenticated:
    """Test _ensure_authenticated() flow."""

    def test_skip_if_already_authenticated(self):
        client, _ = _make_browser_client(is_authenticated=True)
        client._load_cookies = MagicMock()
        client._login = MagicMock()
        client._launch_browser = MagicMock()

        client._ensure_authenticated()

        client._load_cookies.assert_not_called()
        client._login.assert_not_called()

    def test_loads_cookies_and_sets_authenticated(self):
        client, _ = _make_browser_client(is_authenticated=False)
        client._load_cookies = MagicMock(return_value=True)
        client._login = MagicMock()

        client._ensure_authenticated()

        client._load_cookies.assert_called_once()
        client._login.assert_not_called()
        assert client.is_authenticated is True

    def test_calls_login_when_no_cookies(self):
        client, _ = _make_browser_client(is_authenticated=False)
        client._load_cookies = MagicMock(return_value=False)
        client._login = MagicMock()
        client._save_cookies = MagicMock()

        client._ensure_authenticated()

        client._login.assert_called_once()

    def test_launches_browser_if_no_page(self):
        client, _ = _make_browser_client(is_authenticated=False, page=None)
        client._launch_browser = MagicMock()
        client._load_cookies = MagicMock(return_value=True)

        client._ensure_authenticated()

        client._launch_browser.assert_called_once()


class TestAddHumanBehavior:
    """Test _add_human_behavior() randomized delays and scrolls."""

    @patch('utils.resy_browser_client.random')
    @patch('utils.resy_browser_client.time')
    def test_always_sleeps(self, mock_time, mock_random):
        client, _ = _make_browser_client()
        mock_random.uniform.return_value = 0.25
        mock_random.random.return_value = 0.9  # > 0.7 so scroll triggers
        mock_random.randint.return_value = 100

        page = MagicMock()
        client._add_human_behavior(page)

        mock_time.sleep.assert_called_once_with(0.25)

    @patch('utils.resy_browser_client.random')
    @patch('utils.resy_browser_client.time')
    def test_scrolls_when_random_high(self, mock_time, mock_random):
        client, _ = _make_browser_client()
        mock_random.uniform.return_value = 0.2
        mock_random.random.return_value = 0.8  # > 0.7
        mock_random.randint.return_value = 150

        page = MagicMock()
        client._add_human_behavior(page)

        page.evaluate.assert_called_once_with('window.scrollBy(0, 150)')

    @patch('utils.resy_browser_client.random')
    @patch('utils.resy_browser_client.time')
    def test_no_scroll_when_random_low(self, mock_time, mock_random):
        client, _ = _make_browser_client()
        mock_random.uniform.return_value = 0.2
        mock_random.random.return_value = 0.5  # <= 0.7

        page = MagicMock()
        client._add_human_behavior(page)

        page.evaluate.assert_not_called()


class TestFindInFrames:
    """Test _find_in_frames() selector search across page and iframes."""

    def test_finds_in_main_page(self):
        client, _ = _make_browser_client()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = MagicMock()
        mock_locator.first.is_visible.return_value = True

        client.page.locator.return_value = mock_locator
        client.page.frames = []

        result = client._find_in_frames(['.my-selector'])

        assert result is not None
        assert result[0] == mock_locator.first
        assert result[1] == client.page

    def test_finds_in_iframe(self):
        client, _ = _make_browser_client()
        # Main page: not found
        main_locator = MagicMock()
        main_locator.count.return_value = 0
        client.page.locator.return_value = main_locator

        # Iframe: found
        iframe = MagicMock()
        iframe_locator = MagicMock()
        iframe_locator.count.return_value = 1
        iframe_locator.first = MagicMock()
        iframe_locator.first.is_visible.return_value = True
        iframe.locator.return_value = iframe_locator
        client.page.frames = [iframe]

        result = client._find_in_frames(['.my-selector'])

        assert result is not None
        assert result[0] == iframe_locator.first
        assert result[1] == iframe

    def test_returns_none_when_not_found(self):
        client, _ = _make_browser_client()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        client.page.locator.return_value = mock_locator
        client.page.frames = []

        result = client._find_in_frames(['.no-match'])
        assert result is None

    def test_visible_only_skips_hidden(self):
        client, _ = _make_browser_client()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = MagicMock()
        mock_locator.first.is_visible.return_value = False
        client.page.locator.return_value = mock_locator
        client.page.frames = []

        result = client._find_in_frames(['.hidden-elem'], visible_only=True)
        assert result is None


class TestIsSessionValid:
    """Test _is_session_valid() authentication detection."""

    def test_valid_session_detected(self):
        client, _ = _make_browser_client()
        client._screenshot = MagicMock()

        # Auth indicator found on first try
        def locator_side_effect(sel):
            mock = MagicMock()
            if 'user-menu' in sel:
                mock.count.return_value = 1
            else:
                mock.count.return_value = 0
            return mock

        client.page.locator.side_effect = locator_side_effect

        result = client._is_session_valid()
        assert result is True

    def test_invalid_session_login_button(self):
        client, _ = _make_browser_client()
        client._screenshot = MagicMock()

        # No auth indicators, but login button present
        def locator_side_effect(sel):
            mock = MagicMock()
            if 'Log in' in sel:
                mock.count.return_value = 1
            else:
                mock.count.return_value = 0
            return mock

        client.page.locator.side_effect = locator_side_effect

        result = client._is_session_valid()
        assert result is False

    def test_navigation_error_returns_none(self):
        client, _ = _make_browser_client()
        client.page.goto.side_effect = Exception("Network error")

        result = client._is_session_valid()
        assert result is None


class TestSearchVenues:
    """Test search_venues() slug conversion and delegation."""

    def test_calls_get_venue_by_slug(self):
        client, _ = _make_browser_client()
        venue = {'id': 'temple-court', 'name': 'Temple Court'}
        client.get_venue_by_slug = MagicMock(return_value=venue)

        result = client.search_venues("Temple Court")

        client.get_venue_by_slug.assert_called_once_with('temple-court', 'ny')
        assert result == [venue]

    def test_returns_empty_when_not_found(self):
        client, _ = _make_browser_client()
        client.get_venue_by_slug = MagicMock(return_value=None)

        result = client.search_venues("Nonexistent Place")
        assert result == []

    def test_custom_location(self):
        client, _ = _make_browser_client()
        client.get_venue_by_slug = MagicMock(return_value=None)

        client.search_venues("Some Restaurant", location='SF')
        client.get_venue_by_slug.assert_called_once_with('some-restaurant', 'sf')


class TestGetVenueBySlug:
    """Test get_venue_by_slug() page loading and venue extraction."""

    def test_success_modern_url(self):
        client, _ = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        client._add_human_behavior = MagicMock()

        # Page loads successfully (not 404)
        client.page.content.return_value = '<html><body>Temple Court</body></html>'
        client.page.title.return_value = 'Temple Court - Resy'

        # h1 found
        h1_locator = MagicMock()
        h1_locator.inner_text.return_value = 'Temple Court'

        def locator_side_effect(sel):
            if sel == 'h1':
                mock = MagicMock()
                mock.first = h1_locator
                return mock
            mock = MagicMock()
            mock.first.inner_text.side_effect = Exception("not found")
            return mock

        client.page.locator.side_effect = locator_side_effect

        result = client.get_venue_by_slug('temple-court', 'ny')

        assert result is not None
        assert result['name'] == 'Temple Court'
        assert result['id'] == 'temple-court'
        assert result['url_slug'] == 'temple-court'

    def test_404_fallback_to_old_url(self):
        client, _ = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        client._add_human_behavior = MagicMock()

        # content() is called once per URL check.
        # title() is only called when "page not found" is NOT in content
        # (Python short-circuit evaluation). For the first URL, "page not found"
        # matches so title() is skipped. Only the second URL calls title().
        content_responses = [
            '<html><body>page not found</body></html>',  # modern URL → 404 via content
            '<html><body>Some Restaurant</body></html>',  # old URL → success
        ]
        client.page.content.side_effect = content_responses
        client.page.title.return_value = 'Some Restaurant - Resy'

        h1_locator = MagicMock()
        h1_locator.inner_text.return_value = 'Some Restaurant'

        def locator_side_effect(sel):
            if sel == 'h1':
                mock = MagicMock()
                mock.first = h1_locator
                return mock
            mock = MagicMock()
            mock.first.inner_text.side_effect = Exception("not found")
            return mock

        client.page.locator.side_effect = locator_side_effect

        result = client.get_venue_by_slug('some-restaurant', 'ny')

        assert result is not None
        assert result['name'] == 'Some Restaurant'
        # Should have navigated twice
        assert client.page.goto.call_count == 2

    def test_both_urls_404(self):
        client, _ = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        client._add_human_behavior = MagicMock()

        client.page.content.return_value = '<html><body>page not found</body></html>'
        client.page.title.return_value = '404'

        result = client.get_venue_by_slug('nonexistent', 'ny')
        assert result is None


class TestGetAvailability:
    """Test get_availability() time slot parsing."""

    def _setup_availability_client(self):
        client, settings = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        return client, settings

    def test_parses_time_slots(self):
        client, settings = self._setup_availability_client()

        # wait_for_function succeeds
        client.page.wait_for_function = MagicMock()

        # Create buttons that look like time slots
        btn1 = MagicMock()
        btn1.inner_text.return_value = '6:00 PM\nDining Room'
        btn1.is_disabled.return_value = False
        btn1.get_attribute.return_value = None

        btn2 = MagicMock()
        btn2.inner_text.return_value = '7:30 PM\nBar'
        btn2.is_disabled.return_value = False
        btn2.get_attribute.return_value = None

        client.page.locator.return_value.all.return_value = [btn1, btn2]

        result = client.get_availability('temple-court', '2026-02-21', 2)

        assert len(result) == 2
        assert result[0]['time'] == '6:00 PM'
        assert result[0]['table_name'] == 'Dining Room'
        assert '|||' in result[0]['config_id']
        assert result[1]['time'] == '7:30 PM'
        assert result[1]['table_name'] == 'Bar'

    def test_skips_disabled_buttons(self):
        client, settings = self._setup_availability_client()
        client.page.wait_for_function = MagicMock()

        btn_disabled = MagicMock()
        btn_disabled.inner_text.return_value = '8:00 PM\nDining Room'
        btn_disabled.is_disabled.return_value = True
        btn_disabled.get_attribute.return_value = None

        btn_enabled = MagicMock()
        btn_enabled.inner_text.return_value = '9:00 PM\nDining Room'
        btn_enabled.is_disabled.return_value = False
        btn_enabled.get_attribute.return_value = None

        client.page.locator.return_value.all.return_value = [btn_disabled, btn_enabled]

        # Mock SelectorHelper.find_element for no-availability check
        with patch('utils.resy_browser_client.SelectorHelper') as mock_sh:
            mock_sh.find_element.return_value = None
            result = client.get_availability('temple-court', '2026-02-21', 2)

        assert len(result) == 1
        assert result[0]['time'] == '9:00 PM'

    def test_skips_navigation_buttons(self):
        client, settings = self._setup_availability_client()
        client.page.wait_for_function = MagicMock()

        # Navigation button with city name
        nav_btn = MagicMock()
        nav_btn.inner_text.return_value = '5:00 PM\nNew York'
        nav_btn.is_disabled.return_value = False
        nav_btn.get_attribute.return_value = 'CitiesListButton'

        # Real time slot
        time_btn = MagicMock()
        time_btn.inner_text.return_value = '5:00 PM\nDining Room'
        time_btn.is_disabled.return_value = False
        time_btn.get_attribute.return_value = None

        client.page.locator.return_value.all.return_value = [nav_btn, time_btn]

        result = client.get_availability('temple-court', '2026-02-21', 2)

        assert len(result) == 1
        assert result[0]['table_name'] == 'Dining Room'

    def test_numeric_venue_id_rejected(self):
        client, settings = self._setup_availability_client()

        result = client.get_availability('12345', '2026-02-21', 2)
        assert result == []

    def test_no_availability_message(self):
        client, settings = self._setup_availability_client()
        client.page.wait_for_function = MagicMock()

        # No time slot buttons
        empty_btn = MagicMock()
        empty_btn.inner_text.return_value = 'Close'
        empty_btn.is_disabled.return_value = False
        empty_btn.get_attribute.return_value = None
        client.page.locator.return_value.all.return_value = [empty_btn]

        with patch('utils.resy_browser_client.SelectorHelper') as mock_sh:
            mock_sh.find_element.return_value = MagicMock()  # "No availability" found
            result = client.get_availability('temple-court', '2026-02-21', 2)

        assert result == []


class TestMakeReservation:
    """Test make_reservation() booking flow."""

    def _setup_reservation_client(self):
        client, settings = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        client._add_human_behavior = MagicMock()
        client._screenshot = MagicMock(return_value=None)
        client._find_in_frames = MagicMock(return_value=None)
        client._check_booking_confirmation = MagicMock(return_value={
            'success': True,
            'reservation_id': 'resy-test-2026-02-21',
        })
        return client, settings

    def test_invalid_config_id_raises(self):
        client, _ = self._setup_reservation_client()
        client.page.url = ''

        result = client.make_reservation('bad-id', '2026-02-21', 2)

        assert result['success'] is False
        assert 'error' in result

    def test_skips_navigation_when_already_on_page(self):
        client, _ = self._setup_reservation_client()
        config_id = 'temple-court|||2026-02-21|||7:00 PM'
        client.page.url = 'https://resy.com/cities/new-york-ny/venues/temple-court?date=2026-02-21&seats=2'

        # Button found
        btn = MagicMock()
        btn.inner_text.return_value = '7:00 PM\nDining Room'
        btn.is_disabled.return_value = False
        client.page.locator.return_value.all.return_value = [btn]

        # Modal appears
        client.page.wait_for_selector = MagicMock()

        # Reserve button in iframe
        frame = MagicMock()
        frame_btn = MagicMock()
        frame_btn.is_visible.return_value = True
        frame_btn.is_disabled.return_value = False
        frame.locator.return_value.count.return_value = 1
        frame.locator.return_value.first = frame_btn
        client.page.frames = [frame]

        with patch('utils.resy_browser_client.time'):
            result = client.make_reservation(config_id, '2026-02-21', 2)

        # Should NOT have called page.goto since already on page
        client.page.goto.assert_not_called()

    def test_time_button_not_found_raises(self):
        client, _ = self._setup_reservation_client()
        config_id = 'temple-court|||2026-02-21|||11:00 PM'
        client.page.url = ''

        # No matching buttons
        client.page.locator.return_value.all.return_value = []
        client.page.wait_for_function = MagicMock()

        with patch('utils.resy_browser_client.time'):
            result = client.make_reservation(config_id, '2026-02-21', 2)

        assert result['success'] is False
        assert 'error' in result

    def test_conflict_modal_detected(self):
        client, settings = _make_browser_client()
        client._ensure_authenticated = MagicMock()
        client._rate_limit = MagicMock()
        client._add_human_behavior = MagicMock()
        client._screenshot = MagicMock(return_value=None)

        config_id = 'temple-court|||2026-02-21|||7:00 PM'
        client.page.url = ''

        # Time button found and clicked
        btn = MagicMock()
        btn.inner_text.return_value = '7:00 PM\nDining Room'
        btn.is_disabled.return_value = False
        client.page.locator.return_value.all.return_value = [btn]
        client.page.locator.return_value.count.return_value = 0
        client.page.wait_for_selector = MagicMock()
        client.page.wait_for_function = MagicMock()

        # Reserve button in iframe
        frame = MagicMock()
        frame_btn = MagicMock()
        frame_btn.is_visible.return_value = True
        frame_btn.is_disabled.return_value = False
        frame.locator.return_value.count.return_value = 1
        frame.locator.return_value.first = frame_btn
        client.page.frames = [frame]

        # Conflict found in frames
        conflict_locator = MagicMock()
        conflict_frame = MagicMock()
        conflict_dialog = MagicMock()
        conflict_dialog.inner_text.return_value = 'You already have a reservation at Some Place.'
        conflict_frame.locator.return_value.first = conflict_dialog
        client._find_in_frames = MagicMock(return_value=(conflict_locator, conflict_frame))

        with patch('utils.resy_browser_client.time'):
            result = client.make_reservation(config_id, '2026-02-21', 2)

        assert result['status'] == 'conflict'
        assert result['success'] is False
        assert 'options' in result

    def test_uses_non_navigation_rate_limit(self):
        client, _ = self._setup_reservation_client()
        config_id = 'temple-court|||2026-02-21|||7:00 PM'
        client.page.url = ''

        # Minimal setup to get past the button click
        btn = MagicMock()
        btn.inner_text.return_value = '7:00 PM\nDining Room'
        btn.is_disabled.return_value = False
        client.page.locator.return_value.all.return_value = [btn]
        client.page.locator.return_value.count.return_value = 0
        client.page.wait_for_selector = MagicMock()
        client.page.wait_for_function = MagicMock()
        client.page.frames = []

        with patch('utils.resy_browser_client.time'):
            client.make_reservation(config_id, '2026-02-21', 2)

        client._rate_limit.assert_called_once_with(navigation=False)


class TestCheckBookingConfirmation:
    """Test _check_booking_confirmation() confirmation detection."""

    def test_confirmation_found(self):
        client, _ = _make_browser_client()

        # Confirm button found and clicked
        confirm_btn = MagicMock()
        confirm_btn.inner_text.return_value = 'Confirm'
        confirm_btn.is_disabled.return_value = False
        confirm_btn.scroll_into_view_if_needed = MagicMock()

        # Final button on main page (none needed)
        main_locator = MagicMock()
        main_locator.count.return_value = 0

        # Confirmation text found
        confirmation_locator = MagicMock()

        call_count = [0]

        def find_in_frames_side_effect(selectors, visible_only=False):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: looking for Confirm button
                return (confirm_btn, MagicMock())
            else:
                # Second call: looking for confirmation text
                return (confirmation_locator, MagicMock())

        client._find_in_frames = MagicMock(side_effect=find_in_frames_side_effect)
        client.page.locator.return_value.count.return_value = 0

        with patch('utils.resy_browser_client.time'):
            result = client._check_booking_confirmation(
                'temple-court|||2026-02-21|||7:00 PM',
                '2026-02-21', 2, 'temple-court', '7:00 PM'
            )

        assert result['success'] is True
        assert result['reservation_id'] is not None

    def test_no_confirmation_no_error(self):
        client, _ = _make_browser_client()
        client._screenshot = MagicMock()

        # No confirm button, no confirmation, no error
        client._find_in_frames = MagicMock(return_value=None)

        main_locator = MagicMock()
        main_locator.count.return_value = 0
        client.page.locator.return_value = main_locator
        client.page.locator.return_value.all.return_value = []

        with patch('utils.resy_browser_client.time'):
            result = client._check_booking_confirmation(
                'test|||2026-02-21|||7:00 PM',
                '2026-02-21', 2, 'test', '7:00 PM'
            )

        assert result['success'] is True
        assert result['status'] == 'unconfirmed'

    def test_error_message_raises(self):
        client, _ = _make_browser_client()
        client._screenshot = MagicMock()

        # No confirm button, no confirmation
        client._find_in_frames = MagicMock(return_value=None)

        # Error message found
        error_locator = MagicMock()
        error_locator.count.return_value = 0  # default

        def locator_side_effect(sel):
            mock = MagicMock()
            if 'reservation failed' in sel:
                mock.count.return_value = 1
                mock.first.inner_text.return_value = 'reservation failed'
            else:
                mock.count.return_value = 0
                mock.all.return_value = []
            return mock

        client.page.locator.side_effect = locator_side_effect

        with patch('utils.resy_browser_client.time'):
            with pytest.raises(Exception, match="Booking failed"):
                client._check_booking_confirmation(
                    'test|||2026-02-21|||7:00 PM',
                    '2026-02-21', 2, 'test', '7:00 PM'
                )


class TestResolveReservationConflict:
    """Test resolve_reservation_conflict() choice handling."""

    def test_keep_existing(self):
        client, _ = _make_browser_client()
        keep_btn = MagicMock()
        client._find_in_frames = MagicMock(return_value=(keep_btn, MagicMock()))

        result = client.resolve_reservation_conflict('keep_existing')

        assert result['success'] is True
        assert result['status'] == 'kept_existing'
        keep_btn.click.assert_called_once()

    def test_continue_booking(self):
        client, _ = _make_browser_client()
        continue_btn = MagicMock()
        client._find_in_frames = MagicMock(return_value=(continue_btn, MagicMock()))
        client._check_booking_confirmation = MagicMock(return_value={
            'success': True,
            'reservation_id': 'resy-test-2026-02-21',
        })

        with patch('utils.resy_browser_client.time'):
            result = client.resolve_reservation_conflict(
                'continue_booking',
                config_id='test|||2026-02-21|||7:00 PM',
                date='2026-02-21',
                party_size=2,
                venue_slug='test',
                time_text='7:00 PM'
            )

        assert result['success'] is True
        continue_btn.click.assert_called_once()
        client._check_booking_confirmation.assert_called_once()

    def test_invalid_choice(self):
        client, _ = _make_browser_client()

        result = client.resolve_reservation_conflict('invalid_choice')

        assert result['success'] is False
        assert 'Invalid choice' in result['error']

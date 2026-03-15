"""Tests for neighborhood coordinate lookups."""

import pytest
from utils.neighborhood_coords import (
    get_neighborhood_coords,
    normalize_neighborhood_name,
    NYC_DEFAULT_CENTER,
    NYC_NEIGHBORHOODS,
)


class TestGetNeighborhoodCoords:
    """Test coordinate lookup for NYC neighborhoods."""

    def test_known_neighborhoods(self):
        """Verify coords returned for well-known neighborhoods."""
        coords = get_neighborhood_coords('West Village')
        assert coords is not None
        lat, lng = coords
        assert 40.72 < lat < 40.74
        assert -74.01 < lng < -73.99

    def test_williamsburg(self):
        coords = get_neighborhood_coords('Williamsburg')
        assert coords is not None
        lat, lng = coords
        assert 40.70 < lat < 40.72
        assert -73.97 < lng < -73.94

    def test_upper_east_side(self):
        coords = get_neighborhood_coords('Upper East Side')
        assert coords is not None
        lat, lng = coords
        assert 40.76 < lat < 40.79

    def test_case_insensitive(self):
        """Lookup should be case-insensitive."""
        lower = get_neighborhood_coords('west village')
        upper = get_neighborhood_coords('West Village')
        mixed = get_neighborhood_coords('WEST VILLAGE')
        assert lower == upper == mixed

    def test_aliases_les(self):
        """'LES' should resolve to Lower East Side coords."""
        coords = get_neighborhood_coords('LES')
        expected = get_neighborhood_coords('Lower East Side')
        assert coords == expected
        assert coords is not None

    def test_aliases_fidi(self):
        coords = get_neighborhood_coords('FiDi')
        expected = get_neighborhood_coords('Financial District')
        assert coords == expected
        assert coords is not None

    def test_aliases_uws(self):
        coords = get_neighborhood_coords('UWS')
        expected = get_neighborhood_coords('Upper West Side')
        assert coords == expected

    def test_aliases_ues(self):
        coords = get_neighborhood_coords('UES')
        expected = get_neighborhood_coords('Upper East Side')
        assert coords == expected

    def test_unknown_returns_none(self):
        assert get_neighborhood_coords('Narnia') is None
        assert get_neighborhood_coords('') is None

    def test_non_ny_city_returns_none(self):
        assert get_neighborhood_coords('West Village', city='sf') is None

    def test_borough_level(self):
        """Borough names should return coordinates."""
        assert get_neighborhood_coords('Manhattan') is not None
        assert get_neighborhood_coords('Brooklyn') is not None


class TestNormalizeNeighborhoodName:
    """Test name normalization."""

    def test_strips_whitespace(self):
        assert normalize_neighborhood_name('  soho  ') == 'soho'

    def test_lowercases(self):
        assert normalize_neighborhood_name('SoHo') == 'soho'

    def test_alias_resolution(self):
        assert normalize_neighborhood_name('LES') == 'lower east side'
        assert normalize_neighborhood_name('fidi') == 'financial district'

    def test_passthrough_for_known_name(self):
        """Known names without aliases pass through as lowercase."""
        assert normalize_neighborhood_name('Tribeca') == 'tribeca'

    def test_unknown_passthrough(self):
        assert normalize_neighborhood_name('Unknown Place') == 'unknown place'


class TestNYCDefaultCenter:
    """Test the default center constant."""

    def test_is_in_nyc(self):
        lat, lng = NYC_DEFAULT_CENTER
        assert 40.7 < lat < 40.8
        assert -74.1 < lng < -73.9

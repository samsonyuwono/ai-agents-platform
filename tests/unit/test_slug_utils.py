"""Unit tests for slug conversion utilities."""

import pytest
from utils.slug_utils import SlugConverter, normalize_slug


class TestSlugConverter:
    """Test slug conversion."""

    @pytest.mark.parametrize("input_name,expected_slug", [
        ("Temple Court", "temple-court"),
        ("Don Angie", "don-angie"),
        ("Le Bernardin", "le-bernardin"),
        ("Carbone", "carbone"),
        ("L'Artusi", "lartusi"),
        ("ABC & Co", "abc-and-co"),
        ("Test  Multiple  Spaces", "test-multiple-spaces"),
        ("  Leading Trailing  ", "leading-trailing"),
    ])
    def test_normalize_slug(self, input_name, expected_slug):
        """Test slug normalization with various inputs."""
        assert normalize_slug(input_name) == expected_slug

    def test_slug_overrides(self):
        """Test that known overrides are used."""
        assert normalize_slug("Temple Court") == "temple-court"
        assert normalize_slug("don angie") == "don-angie"

    def test_case_insensitive(self):
        """Test that slug conversion is case-insensitive."""
        assert normalize_slug("TEMPLE COURT") == "temple-court"
        assert normalize_slug("Temple Court") == "temple-court"
        assert normalize_slug("temple court") == "temple-court"

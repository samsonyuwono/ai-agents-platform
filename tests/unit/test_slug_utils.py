"""Unit tests for slug conversion utilities."""

import pytest
from utils.slug_utils import (
    SlugConverter, normalize_slug, parse_config_id, make_config_id,
    CONFIG_ID_SEPARATOR,
)


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


class TestConfigId:
    """Test config_id parsing and construction."""

    def test_parse_config_id_valid(self):
        """Test parsing a valid config_id."""
        result = parse_config_id("temple-court|||2026-02-25|||7:00 PM")
        assert result == {
            'venue_slug': 'temple-court',
            'date': '2026-02-25',
            'time_text': '7:00 PM',
        }

    def test_parse_config_id_too_few_parts(self):
        """Test parsing config_id with too few parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid config_id format"):
            parse_config_id("temple-court|||2026-02-25")

    def test_parse_config_id_too_many_parts(self):
        """Test parsing config_id with too many parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid config_id format"):
            parse_config_id("a|||b|||c|||d")

    def test_parse_config_id_no_separator(self):
        """Test parsing config_id without separator raises ValueError."""
        with pytest.raises(ValueError, match="Invalid config_id format"):
            parse_config_id("just-a-string")

    def test_make_config_id(self):
        """Test constructing a config_id."""
        result = make_config_id("temple-court", "2026-02-25", "7:00 PM")
        assert result == "temple-court|||2026-02-25|||7:00 PM"

    def test_roundtrip(self):
        """Test that make then parse returns original values."""
        config_id = make_config_id("lartusi", "2026-03-01", "8:30 PM")
        parsed = parse_config_id(config_id)
        assert parsed['venue_slug'] == "lartusi"
        assert parsed['date'] == "2026-03-01"
        assert parsed['time_text'] == "8:30 PM"

    def test_separator_constant(self):
        """Test that CONFIG_ID_SEPARATOR is the expected value."""
        assert CONFIG_ID_SEPARATOR == '|||'

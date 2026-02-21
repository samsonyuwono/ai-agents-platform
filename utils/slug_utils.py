"""Utility functions for restaurant name to URL slug conversion."""

import re
from typing import Optional


class SlugConverter:
    """Convert restaurant names to Resy URL slugs."""

    # Known slug mappings for restaurants with non-standard slugs
    SLUG_OVERRIDES = {
        "don angie": "don-angie",
        "temple court": "temple-court",
        "le bernardin": "le-bernardin",
        "carbone": "carbone",
        "l'artusi": "lartusi",
        # Add more as discovered
    }

    @staticmethod
    def normalize_slug(restaurant_name: str, location: str = "ny") -> str:
        """
        Convert restaurant name to Resy URL slug.

        Args:
            restaurant_name: Full restaurant name (e.g., "Temple Court")
            location: City code (default: "ny")

        Returns:
            URL slug (e.g., "temple-court")

        Examples:
            >>> SlugConverter.normalize_slug("Temple Court")
            'temple-court'
            >>> SlugConverter.normalize_slug("Don Angie")
            'don-angie'
            >>> SlugConverter.normalize_slug("L'Artusi")
            'lartusi'
        """
        name_lower = restaurant_name.lower().strip()

        # Check known overrides first
        if name_lower in SlugConverter.SLUG_OVERRIDES:
            return SlugConverter.SLUG_OVERRIDES[name_lower]

        # Standard normalization
        slug = name_lower
        slug = slug.replace("'", "")      # Remove apostrophes
        slug = slug.replace("&", "and")   # Replace ampersands
        slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
        slug = re.sub(r'[\s_]+', '-', slug)   # Replace spaces with hyphens
        slug = slug.strip('-')            # Remove leading/trailing hyphens

        return slug


def normalize_slug(restaurant_name: str, location: str = "ny") -> str:
    """Convenience function for slug conversion."""
    return SlugConverter.normalize_slug(restaurant_name, location)

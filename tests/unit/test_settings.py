"""Unit tests for settings configuration."""

import pytest
import os
from config.settings import Settings


class TestSettings:
    """Test settings configuration."""

    def test_has_anthropic_configured(self):
        """Test Anthropic API key detection."""
        if os.getenv("ANTHROPIC_API_KEY"):
            assert Settings.has_anthropic_configured()

    def test_has_resy_browser_configured(self):
        """Test Resy browser credentials detection."""
        if os.getenv("RESY_EMAIL") and os.getenv("RESY_PASSWORD"):
            assert Settings.has_resy_browser_configured()

    def test_has_email_configured(self):
        """Test email configuration detection."""
        if os.getenv("EMAIL_ADDRESS"):
            assert Settings.has_email_configured()

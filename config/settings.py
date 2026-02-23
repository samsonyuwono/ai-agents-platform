"""
Centralized Settings Management
Loads and validates environment variables.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # API Keys
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Email Configuration
    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    EMAIL_TO = os.environ.get("EMAIL_TO")

    # Resy Configuration
    RESY_API_KEY = os.environ.get("RESY_API_KEY")
    RESY_AUTH_TOKEN = os.environ.get("RESY_AUTH_TOKEN")
    RESY_PAYMENT_METHOD_ID = os.environ.get("RESY_PAYMENT_METHOD_ID")

    # Resy Browser Automation (alternative to API)
    RESY_EMAIL = os.environ.get("RESY_EMAIL")
    RESY_PASSWORD = os.environ.get("RESY_PASSWORD")
    RESY_CLIENT_MODE = os.environ.get("RESY_CLIENT_MODE", "auto")  # auto, api, browser
    RESY_BROWSER_HEADLESS = os.environ.get("RESY_BROWSER_HEADLESS", "true").lower() == "true"

    # Resy Dynamic Configuration
    RESY_DEFAULT_LOCATION = os.environ.get("RESY_DEFAULT_LOCATION", "ny")
    RESY_RATE_LIMIT_MIN_SECONDS = int(os.environ.get("RESY_RATE_LIMIT_MIN_SECONDS", "3"))
    RESY_RATE_LIMIT_JITTER_MIN = float(os.environ.get("RESY_RATE_LIMIT_JITTER_MIN", "0.5"))
    RESY_RATE_LIMIT_JITTER_MAX = float(os.environ.get("RESY_RATE_LIMIT_JITTER_MAX", "1.5"))
    RESY_BROWSER_TIMEOUT_MS = int(os.environ.get("RESY_BROWSER_TIMEOUT_MS", "30000"))

    # Residential proxy (optional — routes browser traffic through residential IP)
    RESY_PROXY_SERVER = os.environ.get("RESY_PROXY_SERVER")  # e.g., "http://brd.superproxy.io:22225"
    RESY_PROXY_USERNAME = os.environ.get("RESY_PROXY_USERNAME")
    RESY_PROXY_PASSWORD = os.environ.get("RESY_PROXY_PASSWORD")

    # OpenTable Configuration
    OPENTABLE_EMAIL = os.environ.get("OPENTABLE_EMAIL")
    OPENTABLE_PASSWORD = os.environ.get("OPENTABLE_PASSWORD")

    # Reservation Settings
    DEFAULT_PARTY_SIZE = int(os.environ.get("DEFAULT_PARTY_SIZE", "2"))
    RESERVATION_DB_PATH = os.environ.get("RESERVATION_DB_PATH", "data/reservations.db")

    # Sniper Configuration
    SNIPER_POLL_INTERVAL_SECONDS = int(os.environ.get("SNIPER_POLL_INTERVAL_SECONDS", "5"))
    SNIPER_MAX_ATTEMPTS = int(os.environ.get("SNIPER_MAX_ATTEMPTS", "60"))
    SNIPER_DEFAULT_TIME_WINDOW_MINUTES = int(os.environ.get("SNIPER_DEFAULT_TIME_WINDOW_MINUTES", "60"))
    SNIPER_REMOTE_HOST = os.environ.get("SNIPER_REMOTE_HOST")  # e.g., "root@159.89.41.103"
    SNIPER_REMOTE_DIR = os.environ.get("SNIPER_REMOTE_DIR", "/root/ai-agents")

    # Model Configuration
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 4096

    # Paths
    NEWS_FOLDER = "news"
    LOGS_FOLDER = "logs"

    @classmethod
    def validate(cls):
        """Validate required settings."""
        if not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        return True

    @classmethod
    def has_anthropic_configured(cls):
        """Check if Anthropic API is configured."""
        return bool(cls.ANTHROPIC_API_KEY)

    @classmethod
    def has_email_configured(cls):
        """Check if email is properly configured."""
        return bool(cls.RESEND_API_KEY and cls.EMAIL_FROM and cls.EMAIL_TO)

    @classmethod
    def has_search_configured(cls):
        """Check if web search is configured."""
        return bool(cls.BRAVE_API_KEY)

    @classmethod
    def has_resy_configured(cls):
        """Check if Resy API is properly configured."""
        return bool(cls.RESY_API_KEY and cls.RESY_AUTH_TOKEN)

    @classmethod
    def has_opentable_configured(cls):
        """Check if OpenTable credentials are configured."""
        return bool(cls.OPENTABLE_EMAIL and cls.OPENTABLE_PASSWORD)

    @classmethod
    def has_proxy_configured(cls) -> bool:
        """Check if residential proxy is configured."""
        return bool(cls.RESY_PROXY_SERVER)

    @classmethod
    def has_resy_browser_configured(cls):
        """Check if Resy browser automation is configured."""
        return bool(cls.RESY_EMAIL and cls.RESY_PASSWORD)


# Validate on import
Settings.validate()

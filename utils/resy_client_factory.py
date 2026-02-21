"""
Factory for creating appropriate Resy client based on configuration.
Allows switching between API and browser automation modes.
"""

from config.settings import Settings


class ResyClientFactory:
    """Factory for selecting between API and browser Resy clients."""

    @staticmethod
    def create_client(mode=None):
        """
        Create appropriate Resy client based on configuration.

        Args:
            mode: Client mode - 'api', 'browser', or 'auto'
                 If not provided, uses Settings.RESY_CLIENT_MODE
                 'auto' tries API first, falls back to browser if API not configured

        Returns:
            ResyClient or ResyBrowserClient instance

        Raises:
            ValueError: If mode is invalid or required configuration is missing
        """
        mode = mode or Settings.RESY_CLIENT_MODE

        if mode == 'browser':
            # Use browser automation
            if not Settings.has_resy_browser_configured():
                raise ValueError(
                    "Browser mode requires RESY_EMAIL and RESY_PASSWORD in .env file"
                )

            from utils.resy_browser_client import ResyBrowserClient
            print("🌐 Using Resy browser automation")
            return ResyBrowserClient()

        elif mode == 'api':
            # Use API client
            if not Settings.has_resy_configured():
                raise ValueError(
                    "API mode requires RESY_API_KEY and RESY_AUTH_TOKEN in .env file"
                )

            from utils.resy_client import ResyClient
            print("🔑 Using Resy API")
            return ResyClient()

        elif mode == 'auto':
            # Automatic mode: prefer API, fall back to browser
            if Settings.has_resy_configured():
                from utils.resy_client import ResyClient
                print("🔑 Using Resy API (auto mode)")
                return ResyClient()

            elif Settings.has_resy_browser_configured():
                from utils.resy_browser_client import ResyBrowserClient
                print("🌐 Using Resy browser automation (auto mode - API not configured)")
                return ResyBrowserClient()

            else:
                raise ValueError(
                    "No Resy configuration found. Please add to .env file:\n"
                    "  For API mode: RESY_API_KEY + RESY_AUTH_TOKEN\n"
                    "  For Browser mode: RESY_EMAIL + RESY_PASSWORD\n\n"
                    "Then set RESY_CLIENT_MODE to 'api', 'browser', or 'auto'"
                )

        else:
            raise ValueError(
                f"Invalid RESY_CLIENT_MODE: '{mode}'. "
                f"Must be 'api', 'browser', or 'auto'"
            )

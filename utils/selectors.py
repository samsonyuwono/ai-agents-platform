"""Centralized selector registry for Resy website automation."""


class ResySelectors:
    """Selectors for Resy website elements."""

    # Login flow
    LOGIN_BUTTON = [
        'button:has-text("Log in")',
        'a:has-text("Log in")',
        'button:has-text("Sign in")',
        '[data-test-id="auth-button"]'
    ]

    EMAIL_LOGIN_LINK = [
        'button:has-text("Log in with email & password")',
        'a:has-text("Log in with email & password")',
        ':has-text("Email")',
    ]

    EMAIL_INPUT = [
        'input[type="email"]',
        'input[name="email"]',
        'input[placeholder*="email" i]',
        'input[id*="email" i]',
        '#email',
        '[autocomplete="email"]'
    ]

    PASSWORD_INPUT = [
        'input[type="password"]',
        'input[name="password"]',
        'input[placeholder*="password" i]',
        'input[id*="password" i]',
        '#password',
        '[autocomplete="current-password"]'
    ]

    SUBMIT_BUTTON = [
        'button[type="submit"]',
        'button:has-text("Continue")',
        'button:has-text("Log in")',
        'button:has-text("Sign in")',
    ]

    # Reservation flow
    RESERVE_NOW_BUTTON = '[data-test-id="order_summary_page-button-book"]'

    CONFIRMATION_MESSAGES = [
        ':has-text("Reservation Booked")',
        ':has-text("Confirmed")',
        ':has-text("Success")',
    ]

    # Calendar/availability
    TIME_SLOT_BUTTON = 'button'  # Will filter by text content

    MODAL_CONTAINER = [
        '[class*="Modal"]',
        '[role="dialog"]',
        ':has-text("Complete Your Reservation")',
    ]


class SelectorHelper:
    """Helper methods for finding elements using selector lists."""

    @staticmethod
    def find_element(page, selectors: list, timeout: int = 5000):
        """
        Try multiple selectors until one is found.

        Args:
            page: Playwright page object
            selectors: List of selector strings
            timeout: Timeout per selector in milliseconds

        Returns:
            Locator for first matching element, or None
        """
        for selector in selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    return elem
            except:
                continue
        return None

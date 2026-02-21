"""
Resy Browser Automation Client
Uses Playwright to interact with Resy website when API is unreliable.
"""

import logging
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
import time
import random
import json
from pathlib import Path
from typing import List, Dict, Optional
from config.settings import Settings
from utils.slug_utils import normalize_slug

logger = logging.getLogger(__name__)

# Location code mappings - short codes to full Resy location names
LOCATION_CODES = {
    'ny': 'new-york-ny',
    'nyc': 'new-york-ny',
    'sf': 'san-francisco-ca',
    'la': 'los-angeles-ca',
}


def resolve_location(location: str) -> str:
    """Resolve a short location code to its full Resy location name."""
    return LOCATION_CODES.get(location.lower(), location.lower())


class ResyBrowserClient:
    """Browser automation client for Resy - mirrors ResyClient interface."""

    def __init__(self, email=None, password=None, headless=None):
        """
        Initialize browser client.

        Args:
            email: Resy account email (defaults to Settings.RESY_EMAIL)
            password: Resy account password (defaults to Settings.RESY_PASSWORD)
            headless: Run in headless mode (defaults to Settings.RESY_BROWSER_HEADLESS)
        """
        self.email = email or Settings.RESY_EMAIL
        self.password = password or Settings.RESY_PASSWORD
        self.headless = headless if headless is not None else Settings.RESY_BROWSER_HEADLESS

        if not self.email or not self.password:
            raise ValueError("Resy email and password are required for browser automation")

        # Rate limiting - uses dynamic settings
        self.last_request_time = 0
        self.min_delay_seconds = Settings.RESY_RATE_LIMIT_MIN_SECONDS

        # Browser state
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_authenticated = False

        # Cookie storage for session persistence
        self.cookie_file = Path.home() / '.resy_session_cookies.json'

    def _launch_browser(self):
        """Launch Playwright browser and create page."""
        print("  🚀 Launching browser...")

        self.playwright = sync_playwright().start()

        # Launch browser with stealth args
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )

        # Create context with realistic settings
        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            # Additional stealth settings
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )

        self.page = self.context.new_page()

        # Hide webdriver property
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        print("  ✓ Browser launched")

    def _cleanup(self):
        """Close browser resources."""
        print("  🧹 Cleaning up browser...")

        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"  ⚠️  Error during cleanup: {e}")

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.is_authenticated = False

        print("  ✓ Browser closed")

    def __del__(self):
        """Destructor - cleanup browser resources."""
        self._cleanup()

    def _rate_limit(self, force: bool = True):
        """
        Enforce rate limiting with randomized delays.
        Conservative timing to avoid account flagging.

        Args:
            force: If False, skip rate limit for cached/fast operations
        """
        if not force and (time.time() - self.last_request_time) < 2:
            # Skip rate limit for fast local operations
            return

        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_delay_seconds:
            # Use dynamic jitter settings from configuration
            jitter = random.uniform(
                Settings.RESY_RATE_LIMIT_JITTER_MIN,
                Settings.RESY_RATE_LIMIT_JITTER_MAX
            )
            sleep_time = (self.min_delay_seconds - time_since_last) + jitter
            print(f"  ⏳ Rate limiting: waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
        else:
            # Even when not rate-limited, add small random delay
            small_jitter = random.uniform(0.5, 1.5)
            time.sleep(small_jitter)

        self.last_request_time = time.time()

    def _add_human_behavior(self, page):
        """Add realistic delays and behavior to avoid detection and account flagging."""
        # Random delay - increased for more natural behavior
        time.sleep(random.uniform(0.5, 1.5))

        # Random scroll (more frequently for realism)
        if random.random() > 0.5:
            scroll_amount = random.randint(50, 200)
            page.evaluate(f'window.scrollBy(0, {scroll_amount})')

        # Occasional random mouse movement within viewport
        if random.random() > 0.7:
            try:
                x = random.randint(100, 1000)
                y = random.randint(100, 600)
                page.mouse.move(x, y)
            except:
                pass  # Ignore if mouse movement fails

    def _save_cookies(self):
        """Save browser cookies to file for session persistence."""
        if self.context:
            try:
                cookies = self.context.cookies()
                with open(self.cookie_file, 'w') as f:
                    json.dump(cookies, f)
                print(f"     ✓ Saved session cookies")
            except Exception as e:
                print(f"     ⚠️  Failed to save cookies: {e}")

    def _load_cookies(self):
        """Load browser cookies from file."""
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'r') as f:
                    cookies = json.load(f)
                self.context.add_cookies(cookies)
                print(f"     ✓ Loaded session cookies")
                return True
            except Exception as e:
                print(f"     ⚠️  Failed to load cookies: {e}")
                return False
        return False

    def _is_session_valid(self) -> bool:
        """Check if current session is still authenticated."""
        try:
            print("     → Navigating to Resy homepage for validation...")
            self.page.goto('https://resy.com', wait_until='networkidle', timeout=15000)

            # Wait for dynamic content to load
            print("     → Waiting for page to fully load...")
            time.sleep(2)

            # Take screenshot for debugging
            try:
                screenshot_path = '/tmp/resy_session_check.png'
                self.page.screenshot(path=screenshot_path)
                print(f"     → Screenshot saved: {screenshot_path}")
            except:
                pass

            # Check for user menu or profile indicator
            user_indicators = [
                '[data-test-id="user-menu"]',
                'button:has-text("Sign out")',
                'a:has-text("Sign out")',
                'button:has-text("My Reservations")',
                'a:has-text("My Reservations")',
                ':has-text("Account")',
                'button[aria-label*="user" i]',
                'a[href*="/user"]',
                '[class*="UserMenu"]',
            ]

            print("     → Checking for authentication indicators...")
            for indicator in user_indicators:
                try:
                    count = self.page.locator(indicator).count()
                    print(f"       - {indicator}: {count} matches")
                    if count > 0:
                        print(f"     ✓ Session valid (found: {indicator})")
                        return True
                except Exception as e:
                    print(f"       - {indicator}: error ({e})")
                    continue

            # Check if login button is present (means NOT logged in)
            login_indicators = [
                'button:has-text("Log in")',
                'a:has-text("Log in")',
            ]

            print("     → Checking for login button (inverse check)...")
            for indicator in login_indicators:
                try:
                    count = self.page.locator(indicator).count()
                    print(f"       - {indicator}: {count} matches")
                    if count > 0:
                        print(f"     ✗ Session invalid (found login button)")
                        return False
                except Exception as e:
                    print(f"       - {indicator}: error ({e})")
                    continue

            print("     ⚠️  Could not determine session status (no clear indicators)")
            return None
        except Exception as e:
            print(f"     ⚠️  Session validation error: {e}")
            return None

    def _ensure_authenticated(self):
        """Ensure browser is authenticated, login if needed."""
        # If already authenticated in this session, skip validation
        if self.is_authenticated:
            return

        if not self.page:
            self._launch_browser()

        # Try loading saved cookies first
        if self._load_cookies():
            # Optimistic authentication: assume cookies are valid
            # If they're not, we'll get an auth error and can handle it then
            print("     ✓ Loaded session cookies, assuming authenticated")
            print("     → (Will validate lazily if needed)")
            self.is_authenticated = True
            return

        # No cookies - perform fresh login
        self._login()

        # Save cookies for next time
        if self.is_authenticated:
            self._save_cookies()

    def _login(self):
        """
        Perform Resy login flow.

        Raises:
            Exception: If login fails
        """
        print("  🔐 Logging in to Resy...")

        try:
            # Navigate to Resy homepage
            self.page.goto('https://resy.com', wait_until='load', timeout=30000)
            self._add_human_behavior(self.page)

            # Check if already logged in (no login button present)
            user_indicators = [
                '[data-test-id="user-menu"]',
                'button:has-text("Sign out")',
                'a:has-text("Sign out")',
                'button[aria-label*="user" i]',
                'a[href*="/user"]',
            ]

            print("    Checking if already authenticated...")
            for indicator in user_indicators:
                try:
                    if self.page.locator(indicator).count() > 0:
                        print(f"    ✓ Already logged in (found: {indicator})")
                        self.is_authenticated = True
                        return
                except:
                    continue

            # Find and click login button
            login_selectors = [
                'button:has-text("Log in")',
                'a:has-text("Log in")',
                'button:has-text("Sign in")',
                '[data-test-id="auth-button"]'
            ]

            print("    Looking for login button...")
            login_button = None
            for selector in login_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        login_button = self.page.locator(selector).first
                        print(f"    Found login button: {selector}")
                        break
                except:
                    continue

            if not login_button:
                # One more check - maybe we're logged in but didn't detect it above
                print("    No login button found - checking authentication status...")
                session_status = self._is_session_valid()
                if session_status is True:
                    print("    ✓ Session is valid, proceeding as authenticated")
                    self.is_authenticated = True
                    return
                elif session_status is None:
                    # Can't determine - assume logged in and proceed
                    print("    ⚠️  Cannot determine auth status, assuming logged in")
                    print("    → If you see errors, delete ~/.resy_session_cookies.json")
                    self.is_authenticated = True
                    return
                raise Exception("Could not find login button on homepage")

            # Click login button
            print("    Clicking login button...")
            login_button.click()
            self._add_human_behavior(self.page)

            # Wait for login modal/form to appear
            print("    Waiting for login modal...")
            time.sleep(2)  # Give modal time to animate in

            # Resy login flow: First shows phone number login
            # Need to click "Log in with email & password" link at bottom
            print("    Looking for email/password login link...")
            email_login_selectors = [
                'a:has-text("Log in with email & password")',
                'button:has-text("Log in with email & password")',
                'text="Log in with email & password"'
            ]

            email_login_link = None
            for selector in email_login_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        email_login_link = self.page.locator(selector).first
                        print(f"    Found email login link: {selector}")
                        break
                except:
                    continue

            if email_login_link:
                print("    Clicking 'Log in with email & password'...")
                email_login_link.click()
                time.sleep(2)  # Wait for form to load
            else:
                print("    No email/password link found, trying direct email input...")

            # Try to find email input with multiple strategies
            email_input = None

            # Strategy 1: Direct input selectors
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]',
                'input[id*="email" i]',
                '#email',
                '[autocomplete="email"]'
            ]

            for selector in email_selectors:
                if self.page.locator(selector).count() > 0:
                    email_input = self.page.locator(selector).first
                    print(f"    Found email input: {selector}")
                    break

            # Strategy 2: Look inside modals
            if not email_input:
                print("    Looking inside modal dialogs...")
                modal_selectors = ['[role="dialog"]', '.modal', '[class*="Modal"]', '[class*="Dialog"]']

                for modal_sel in modal_selectors:
                    modals = self.page.locator(modal_sel).all()
                    for modal in modals:
                        # Look for email input inside this modal
                        for email_sel in email_selectors:
                            inputs = modal.locator(email_sel).all()
                            if len(inputs) > 0 and inputs[0].is_visible():
                                email_input = inputs[0]
                                print(f"    Found email input inside modal: {email_sel}")
                                break
                        if email_input:
                            break
                    if email_input:
                        break

            # Strategy 3: Look for any visible input that might be email
            if not email_input:
                print("    Looking for any text inputs...")
                all_inputs = self.page.locator('input[type="text"], input:not([type])').all()
                for inp in all_inputs:
                    if inp.is_visible():
                        placeholder = inp.get_attribute('placeholder') or ''
                        if 'email' in placeholder.lower() or 'user' in placeholder.lower():
                            email_input = inp
                            print(f"    Found potential email input by placeholder: {placeholder}")
                            break

            if not email_input:
                # Debug output
                print("    ✗ Could not find email input")
                print(f"    Current URL: {self.page.url}")
                modals = self.page.locator('[role="dialog"]').count()
                print(f"    Dialog modals found: {modals}")

                # Take a screenshot for debugging
                try:
                    screenshot_path = '/tmp/resy_login_debug.png'
                    self.page.screenshot(path=screenshot_path)
                    print(f"    Screenshot saved to: {screenshot_path}")
                except:
                    pass

                raise Exception("Could not find email input field after clicking login")

            # Fill email
            email_input.fill(self.email)
            self._add_human_behavior(self.page)

            # Wait for password input
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                '#password'
            ]

            password_input = None
            for selector in password_selectors:
                try:
                    self.page.wait_for_selector(selector, timeout=5000, state='visible')
                    password_input = self.page.locator(selector).first
                    break
                except:
                    continue

            if not password_input:
                raise Exception("Could not find password input field")

            # Fill password
            password_input.fill(self.password)
            self._add_human_behavior(self.page)

            # Click submit - try multiple selectors
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Continue")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")'
            ]

            clicked = False
            for selector in submit_selectors:
                try:
                    self.page.click(selector, timeout=5000)
                    clicked = True
                    break
                except:
                    continue

            if not clicked:
                raise Exception("Could not find submit button")

            # Wait for navigation/login to complete
            print("    Waiting for login to complete...")
            time.sleep(3)  # Give time for authentication

            # Check for success message first (Resy shows "You are all set" modal)
            success_selectors = [
                'text="You are all set"',
                'text="Welcome back"',
                'text="Success"',
                '[class*="Success"]'
            ]

            is_logged_in = False
            for selector in success_selectors:
                if self.page.locator(selector).count() > 0:
                    print(f"    Found success message: {selector}")
                    is_logged_in = True
                    break

            # Check for user indicators (profile icon, account menu)
            if not is_logged_in:
                user_indicators = [
                    'button:has-text("My Profile")',
                    'button:has-text("Account")',
                    'img[alt*="profile" i]',
                    '[data-test-id="user-button"]',
                    'a[href="/user"]',
                    'button[aria-label*="Account" i]'
                ]

                for selector in user_indicators:
                    count = self.page.locator(selector).count()
                    if count > 0:
                        print(f"    Found user indicator: {selector}")
                        is_logged_in = True
                        break

            # Check for actual error messages (not just any alert)
            if not is_logged_in:
                error_messages = [
                    'text="Invalid email or password"',
                    'text="Incorrect email or password"',
                    'text="Login failed"',
                    'text="Authentication failed"'
                ]

                for selector in error_messages:
                    if self.page.locator(selector).count() > 0:
                        error_text = self.page.locator(selector).first.inner_text()
                        print(f"    Found error: {error_text}")
                        raise Exception(f"Login failed: {error_text}")

            if is_logged_in:
                self.is_authenticated = True
                print("  ✓ Login successful")

                # Wait for success modal to close (optional)
                print("    Waiting for success modal to close...")
                time.sleep(2)
            else:
                # Take screenshot for debugging
                screenshot_path = '/tmp/resy_login_after_submit.png'
                self.page.screenshot(path=screenshot_path)
                print(f"    Screenshot saved to: {screenshot_path}")
                raise Exception("Could not confirm login success")

        except Exception as e:
            print(f"  ✗ Login failed: {e}")
            raise

    def search_venues(self, query: str, location: Optional[str] = None) -> List[Dict]:
        """
        Search for restaurants on Resy by name.

        Note: This converts query to URL slug format. For accurate results,
        use get_venue_by_slug() with the exact slug from Resy URL.

        Args:
            query: Restaurant name (will be converted to slug)
            location: City code (default: 'ny')

        Returns:
            List with single venue if found via slug conversion, empty list otherwise
        """
        print(f"  🔍 Searching Resy for: {query}")

        # Convert query to URL slug format (simple conversion)
        url_slug = query.lower().replace(' ', '-').replace("'", '')
        location_code = (location or 'ny').lower()

        # Try to get venue by slug
        venue = self.get_venue_by_slug(url_slug, location_code)

        if venue:
            return [venue]
        else:
            print(f"    💡 Tip: Provide the exact restaurant slug from Resy URL")
            print(f"       Example: 'temple-court' from resy.com/cities/ny/temple-court")
            return []

    def get_venue_by_slug(self, url_slug: str, location: str = 'ny') -> Optional[Dict]:
        """
        Get venue information by URL slug.

        Args:
            url_slug: Restaurant's URL slug (e.g., 'table-87-gowanus')
            location: Location code (e.g., 'new-york-ny', 'ny', 'sf', 'la')

        Returns:
            Venue dictionary with id, name, and details, or None if not found
        """
        print(f"  🔍 Looking up venue: {url_slug}")

        self._ensure_authenticated()
        self._rate_limit()

        try:
            # Navigate to venue page
            # Try modern format first (with /venues/)
            full_location = resolve_location(location)

            # Try modern URL format with /venues/ first
            url = f"https://resy.com/cities/{full_location}/venues/{url_slug}"
            print(f"    Navigating to: {url}")

            self.page.goto(url, wait_until='load', timeout=30000)
            self._add_human_behavior(self.page)

            # Check if page loaded successfully (not 404)
            page_content_lower = self.page.content().lower()
            is_404 = "page not found" in page_content_lower or self.page.title().lower() == "404" or "sorry, but we can't find that page" in page_content_lower

            if is_404:
                # Try old URL format as fallback (without /venues/)
                old_url = f"https://resy.com/cities/{location_lower}/{url_slug}"
                print(f"    ✗ Venue not found, trying fallback: {old_url}")

                self.page.goto(old_url, wait_until='load', timeout=30000)
                self._add_human_behavior(self.page)

                # Check again
                page_content_lower = self.page.content().lower()
                is_404 = "page not found" in page_content_lower or self.page.title().lower() == "404" or "sorry, but we can't find that page" in page_content_lower

                if is_404:
                    print(f"    ✗ Venue not found in either URL format")
                    return None
                else:
                    url = old_url  # Update URL to the working one

            # Extract venue information
            venue_info = {
                'id': url_slug,  # Use slug as ID for browser client
                'url_slug': url_slug,
                'name': None,
                'location': {
                    'city': location.upper(),
                    'neighborhood': None,
                    'address': None
                },
                'rating': None,
                'price_range': None
            }

            # Try to extract venue name
            name_selectors = ['h1', '[data-test-id="venue-name"]', '.VenueName']
            for selector in name_selectors:
                try:
                    name = self.page.locator(selector).first.inner_text()
                    if name:
                        venue_info['name'] = name.strip()
                        break
                except:
                    continue

            print(f"    ✓ Found: {venue_info['name']} (slug: {venue_info['id']})")
            return venue_info

        except Exception as e:
            print(f"    ✗ Venue lookup failed: {e}")
            return None

    def get_availability(self, venue_id: str, date: str, party_size: int = 2) -> List[Dict]:
        """
        Get available reservation slots for a venue.

        Args:
            venue_id: Resy venue ID or URL slug (e.g., 'temple-court')
            date: Date in YYYY-MM-DD format
            party_size: Number of guests (default: 2)

        Returns:
            List of available time slots with slot details
        """
        print(f"  📅 Checking availability for venue {venue_id} on {date} for {party_size} people")

        self._ensure_authenticated()
        self._rate_limit()

        try:
            # venue_id might be numeric (from API) or slug (from browser)
            # For browser client, we need the slug
            # If it looks like a number, we can't directly convert it
            # User should pass the slug or we need a mapping

            # Assume venue_id is a slug for now (or extract from previous search)
            url_slug = venue_id if not venue_id.isdigit() else None

            if not url_slug:
                print(f"    ✗ Cannot determine venue slug from ID: {venue_id}")
                print(f"    💡 Tip: Use the venue slug (e.g., 'temple-court') instead of numeric ID")
                return []

            # Use default location from settings and map to full location name
            location = Settings.RESY_DEFAULT_LOCATION
            full_location = resolve_location(location)

            # Navigate to venue page with date and party size parameters (modern format with /venues/)
            url = f"https://resy.com/cities/{full_location}/venues/{url_slug}?date={date}&seats={party_size}"
            print(f"    Navigating to: {url}")

            self.page.goto(url, wait_until='load', timeout=60000)  # Give it more time for availability to load

            # Wait for availability calendar to fully load
            print(f"    Waiting for availability calendar to load...")
            try:
                # Wait for multiple time slot buttons to appear (not just navigation buttons)
                self.page.wait_for_function(
                    """() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const timeButtons = buttons.filter(btn => {
                            const text = btn.innerText;
                            return (text.includes(' AM') || text.includes(' PM')) &&
                                   (text.toLowerCase().includes('dining') ||
                                    text.toLowerCase().includes('bar') ||
                                    text.toLowerCase().includes('patio') ||
                                    text.split('\\n').length >= 2);
                        });
                        return timeButtons.length > 5;  // Wait for multiple slots
                    }""",
                    timeout=20000
                )
                time.sleep(2)  # Additional buffer
                print(f"    ✓ Calendar loaded")
            except Exception as e:
                print(f"    ⚠️  Timeout waiting for calendar: {e}")
                # Continue anyway

            # Look for time slot buttons in the booking section
            # These are typically blue buttons with time + "Dining Room" text
            # Exclude navigation buttons by checking for specific patterns

            available_slots = []

            # Strategy: Find all buttons, then filter for time slots
            all_buttons = self.page.locator('button').all()
            print(f"    Found {len(all_buttons)} total buttons on page")

            for slot in all_buttons:
                try:
                    # Extract button text
                    time_text = slot.inner_text()

                    # Skip empty text
                    if not time_text or time_text.strip() == '':
                        continue

                    # Check if this looks like a time slot
                    # Time slots contain "AM" or "PM" and usually "Dining Room" or similar
                    text_lower = time_text.lower()
                    is_time_slot = (
                        (' am' in text_lower or ' pm' in text_lower) and
                        ('dining' in text_lower or 'bar' in text_lower or 'patio' in text_lower or len(time_text.split('\n')) >= 2)
                    )

                    # Also exclude navigation-like buttons
                    is_navigation = (
                        'cities' in text_lower or
                        'new york' in text_lower or
                        'hamptons' in text_lower or
                        'miami' in text_lower or
                        slot.get_attribute('class') and 'CitiesList' in slot.get_attribute('class')
                    )

                    # Check if slot is available (not disabled)
                    is_disabled = slot.is_disabled()

                    if is_time_slot and not is_navigation and not is_disabled:
                                    # Clean up time text (remove newlines, extra spaces)
                                    clean_time = time_text.replace('\n', ' ').strip()

                                    # Extract just the time part (e.g., "6:00 PM")
                                    # Text might be "6:00 PM\nDining Room" or just "6:00 PM"
                                    time_parts = clean_time.split()
                                    if len(time_parts) >= 2:
                                        # Assume format is "HH:MM AM/PM [optional table name]"
                                        actual_time = ' '.join(time_parts[:2])
                                        table_info = ' '.join(time_parts[2:]) if len(time_parts) > 2 else 'Dining Room'
                                    else:
                                        actual_time = clean_time
                                        table_info = 'Dining Room'

                                    # Parse slot information
                                    # Use ||| as separator to avoid conflicts with hyphens in venue names/dates
                                    available_slots.append({
                                        'config_id': f"{venue_id}|||{date}|||{actual_time}",  # Generate clean ID
                                        'token': None,  # Browser client doesn't have token
                                        'time': actual_time,
                                        'type': 'standard',
                                        'table_name': table_info,
                                        'venue_name': url_slug
                                    })
                except Exception as e:
                    # Skip this button if we can't parse it
                    continue

            if available_slots:
                print(f"    ✓ Found {len(available_slots)} available slots")
                return available_slots
            else:
                # Check if there's a "no availability" message
                no_avail_selectors = [
                    'text="No availability"',
                    'text="fully booked"',
                    '.NoAvailability'
                ]

                for selector in no_avail_selectors:
                    if self.page.locator(selector).count() > 0:
                        print(f"    ✗ No availability found (restaurant is fully booked)")
                        return []

                print(f"    ✗ No availability found (could not find time slots)")
                return []

        except Exception as e:
            print(f"    ✗ Availability check failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_booking_details(self, config_id: str, date: str, party_size: int) -> Optional[Dict]:
        """
        Get booking details needed for making a reservation.

        Note: Browser client has limited access to booking tokens.

        Args:
            config_id: Configuration ID from availability slot
            date: Date in YYYY-MM-DD format
            party_size: Number of guests

        Returns:
            Booking details dictionary or None if failed
        """
        print(f"    ⚠️  Browser client does not support get_booking_details()")
        return None

    def make_reservation(self, config_id: str, date: str, party_size: int, payment_method_id: Optional[str] = None) -> Dict:
        """
        Make a reservation at a restaurant.

        ⚠️  IMPORTANT: This will actually book the reservation and may charge your payment method!

        Args:
            config_id: Configuration ID from availability slot (format: venue_id-date-time)
            date: Date in YYYY-MM-DD format
            party_size: Number of guests
            payment_method_id: Payment method ID (not used in browser client)

        Returns:
            Reservation details with confirmation token

        Raises:
            Exception: If reservation fails
        """
        print(f"  🎫 Attempting to book reservation...")
        print(f"     ⚠️  WARNING: This will make a REAL reservation!")

        self._ensure_authenticated()
        self._rate_limit()

        try:
            # Parse config_id to extract venue, date, and time
            # Format: "venue_id|||date|||time_text"
            parts = config_id.split('|||')
            if len(parts) != 3:
                raise Exception(f"Invalid config_id format: {config_id}. Expected format: venue|||date|||time")

            venue_slug = parts[0]
            date_from_id = parts[1]
            time_text = parts[2]

            print(f"     Venue: {venue_slug}")
            print(f"     Date: {date}")
            print(f"     Time slot: {time_text}")
            print(f"     Party size: {party_size}")

            # Navigate to venue page with date and party size (use correct URL format)
            location = Settings.RESY_DEFAULT_LOCATION
            full_location = resolve_location(location)
            url = f"https://resy.com/cities/{full_location}/venues/{venue_slug}?date={date}&seats={party_size}"

            # Check if we're already on this venue page with same date/seats
            # Resy redirects URLs, so check if we're on the same venue
            current_url = self.page.url
            needs_navigation = True

            # Check if current URL contains the same venue, date, and seats
            if venue_slug in current_url and f"date={date}" in current_url and f"seats={party_size}" in current_url:
                needs_navigation = False
                print(f"     ✓ Already on {venue_slug} with correct date/seats")
            else:
                print(f"     Navigating to: {venue_slug} on {date}")
                self.page.goto(url, wait_until='load', timeout=60000)

            # Wait for availability calendar if we just navigated
            if needs_navigation:
                print(f"     Waiting for availability calendar to load...")
                try:
                    # Wait for time slot buttons to appear
                    self.page.wait_for_function(
                        """() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const timeButtons = buttons.filter(btn => {
                                const text = btn.innerText;
                                return (text.includes(' AM') || text.includes(' PM')) &&
                                       (text.toLowerCase().includes('dining') ||
                                        text.toLowerCase().includes('bar') ||
                                        text.toLowerCase().includes('patio') ||
                                        text.split('\\n').length >= 2);
                            });
                            return timeButtons.length > 5;
                        }""",
                        timeout=20000
                    )
                    time.sleep(2)
                    print(f"     ✓ Availability calendar loaded")
                except Exception as e:
                    print(f"     ⚠️  Timeout waiting for availability: {e}")
            else:
                # Already on page, calendar should be loaded
                print(f"     Calendar should already be loaded from previous check")
                time.sleep(1)

            # Find and click the time slot button
            print(f"     Looking for time slot: {time_text}")

            # Find all buttons and look for one with matching time
            time_button = None

            try:
                all_buttons = self.page.locator('button').all()
                for btn in all_buttons:
                    try:
                        btn_text = btn.inner_text()
                        # Check if this button contains our time text
                        # Button might say "7:00 AM\nDining Room" when we're looking for "7:00 AM"
                        if time_text in btn_text and not btn.is_disabled():
                            # Additional check: make sure it's a time slot button (contains AM/PM)
                            if ' AM' in btn_text or ' PM' in btn_text:
                                time_button = btn
                                print(f"     Found matching button: {btn_text.replace(chr(10), ' ')[:50]}")
                                break
                    except:
                        continue
            except Exception as e:
                print(f"     Error searching buttons: {e}")

            if not time_button:
                # Take screenshot for debugging
                screenshot_path = '/tmp/resy_no_button.png'
                self.page.screenshot(path=screenshot_path)
                print(f"     Screenshot saved to: {screenshot_path}")
                raise Exception(f"Could not find available time slot: {time_text}")

            print(f"     Clicking time slot...")
            time_button.click()

            # Look for booking form or confirmation modal
            print(f"     Waiting for booking modal to appear...")
            time.sleep(0.5)  # Brief wait for modal animation to start

            # Wait for modal to appear (shorter timeout, modal should appear quickly)
            modal_appeared = False
            try:
                # Try multiple selectors for the modal
                modal_selectors = [
                    '[role="dialog"]',
                    ':has-text("Complete Your Reservation")',
                    '[class*="Modal"]'
                ]

                for selector in modal_selectors:
                    try:
                        self.page.wait_for_selector(selector, timeout=3000)
                        print(f"     ✓ Booking modal appeared")
                        modal_appeared = True
                        time.sleep(0.3)  # Brief wait for modal content
                        break
                    except:
                        continue

                if not modal_appeared:
                    print(f"     ⚠️  Modal might not have appeared, proceeding anyway...")
                    time.sleep(0.5)  # Minimal wait

            except Exception as e:
                print(f"     ⚠️  Timeout waiting for modal: {e}")
                # Continue anyway

            # Look for continue/reserve buttons
            print(f"     Looking for Reserve Now button...")

            # First, let's see what buttons are actually visible
            try:
                # Try multiple ways to find the modal
                modal = None
                modal_selectors = [
                    '[role="dialog"]',
                    ':has-text("Complete Your Reservation")',
                    '.Modal',
                    '[class*="Modal"]',
                    '[class*="modal"]'
                ]

                for sel in modal_selectors:
                    try:
                        if self.page.locator(sel).count() > 0:
                            modal = self.page.locator(sel).first
                            print(f"     Debug: Found modal using selector: {sel}")
                            break
                    except:
                        continue

                if modal:
                    # List all buttons in the modal
                    modal_buttons = modal.locator('button').all()
                    print(f"     Debug: Found {len(modal_buttons)} buttons in modal")
                    for i, btn in enumerate(modal_buttons[:10]):  # Limit to first 10
                        try:
                            btn_text = btn.inner_text().strip().replace('\n', ' ')[:60]
                            is_visible = btn.is_visible()
                            is_disabled = btn.is_disabled()
                            print(f"       Button {i}: '{btn_text}' (vis={is_visible}, dis={is_disabled})")
                        except Exception as e:
                            print(f"       Button {i}: Error - {e}")
                else:
                    # No modal found, list visible buttons on whole page
                    print(f"     Debug: No modal container found, checking all visible buttons...")
                    all_buttons = self.page.locator('button:visible').all()
                    print(f"     Found {len(all_buttons)} visible buttons")
                    for i, btn in enumerate(all_buttons[:10]):
                        try:
                            btn_text = btn.inner_text().strip().replace('\n', ' ')[:60]
                            print(f"       Button {i}: '{btn_text}'")
                        except:
                            pass
            except Exception as e:
                print(f"     Debug button listing failed: {e}")

            # Check iframes FIRST (button is always in iframe #5)
            print(f"     Looking for Reserve Now button in iframes...")
            continue_button = None
            booking_button_selector = '[data-test-id="order_summary_page-button-book"]'

            try:
                frames = self.page.frames
                for i, frame in enumerate(frames):
                    try:
                        if frame.locator(booking_button_selector).count() > 0:
                            elem = frame.locator(booking_button_selector).first

                            # Scroll within the iframe to make button visible
                            try:
                                # Scroll the iframe content to bottom
                                frame.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                                time.sleep(0.5)
                            except:
                                pass

                            # Try to scroll element into view
                            try:
                                elem.scroll_into_view_if_needed(timeout=3000)
                                time.sleep(0.5)
                            except:
                                pass

                            if elem.is_visible() and not elem.is_disabled():
                                continue_button = elem
                                print(f"       ✓ Found Reserve Now button in iframe {i}")
                                break
                    except:
                        continue
            except Exception as e:
                print(f"       ⚠️  Iframe check failed: {e}")

            # FALLBACK: If not in iframe, check main page
            if not continue_button:
                print(f"       Not in iframes, checking main page...")
                try:
                    if self.page.locator(booking_button_selector).count() > 0:
                        elem = self.page.locator(booking_button_selector).first
                        elem.scroll_into_view_if_needed(timeout=2000)
                        time.sleep(0.5)
                        if elem.is_visible() and not elem.is_disabled():
                            continue_button = elem
                            print(f"       ✓ Found on main page")
                except:
                    pass

                    # FALLBACK 2: JavaScript click - find ANY element with "Reserve" text
                    if not continue_button:
                        print(f"       Using JavaScript to find and click Reserve button...")
                        try:
                            # Use JavaScript to find and click the button
                            clicked = self.page.evaluate("""() => {
                                // Find all clickable elements
                                const allElements = document.querySelectorAll('button, a, div[role="button"], span[role="button"]');

                                for (const elem of allElements) {
                                    const text = elem.innerText || elem.textContent || '';

                                    // Look for Reserve/Book keywords
                                    if (text.toLowerCase().includes('reserve') ||
                                        text.toLowerCase().includes('book now') ||
                                        text.toLowerCase().includes('complete reservation')) {

                                        // Check if it has the right data-test-id
                                        if (elem.getAttribute('data-test-id') === 'order_summary_page-button-book') {
                                            elem.scrollIntoView({behavior: 'smooth', block: 'center'});
                                            setTimeout(() => elem.click(), 500);
                                            return {success: true, text: text.trim(), method: 'data-test-id'};
                                        }
                                    }
                                }

                                // If not found by data-test-id, try by text and button class
                                for (const elem of allElements) {
                                    const text = elem.innerText || elem.textContent || '';
                                    const classes = elem.className || '';

                                    if ((text.toLowerCase().includes('reserve') && classes.includes('Button--primary')) ||
                                        elem.getAttribute('data-test-id') === 'order_summary_page-button-book') {
                                        elem.scrollIntoView({behavior: 'smooth', block: 'center'});
                                        setTimeout(() => elem.click(), 500);
                                        return {success: true, text: text.trim(), method: 'text+class'};
                                    }
                                }

                                return {success: false, message: 'Button not found'};
                            }""")

                            if clicked and clicked.get('success'):
                                print(f"       ✓ JavaScript click succeeded: '{clicked.get('text')}' via {clicked.get('method')}")
                                # Give time for click to process
                                time.sleep(2)
                                # Mark as found so we don't show error
                                continue_button = "javascript_clicked"
                            else:
                                print(f"       ✗ JavaScript click failed: {clicked.get('message')}")
                        except Exception as e:
                            print(f"       ✗ JavaScript approach failed: {e}")

            # If still no button found, check modal status and report partial success
            if not continue_button:
                print(f"     ⚠️  Could not find clickable Reserve Now button")

                # Check if modal is at least open (try multiple ways)
                modal_is_open = False
                modal_checks = [
                    ':has-text("Complete Your Reservation")',
                    '[class*="Modal"]',
                    '[role="dialog"]'
                ]

                for check in modal_checks:
                    try:
                        if self.page.locator(check).count() > 0:
                            modal_is_open = True
                            print(f"     ✓ Modal detected with: {check}")
                            break
                    except:
                        continue

                if modal_is_open:
                    print(f"     ✅ SUCCESS: Booking modal opened!")
                    print(f"     The time slot button was clicked and reservation modal appeared.")
                    print(f"     Manual step: Click 'Reserve Now' button in the modal to complete booking")

                    # Take screenshot
                    screenshot_path = '/tmp/resy_booking_modal_success.png'
                    self.page.screenshot(path=screenshot_path)
                    print(f"     Screenshot: {screenshot_path}")

                    # Return partial success
                    return {
                        'success': True,
                        'status': 'modal_opened',
                        'message': 'Booking modal opened successfully - ready for manual completion',
                        'reservation_id': None,
                        'confirmation_token': None,
                        'next_step': 'Click Reserve Now button in the modal'
                    }
                else:
                    print(f"     ✗ Modal not detected either")

            if continue_button:
                print(f"     Clicking Reserve Now button...")
                try:
                    # Handle both Playwright element and string marker
                    if continue_button == "javascript_clicked":
                        print(f"       ✓ Already clicked via JavaScript")
                    else:
                        # Try JavaScript click first (bypasses viewport issues)
                        try:
                            continue_button.evaluate('element => element.click()')
                            print(f"       ✓ Button clicked via JavaScript")
                        except Exception as js_error:
                            # Fallback to normal click
                            print(f"       JavaScript click failed, trying normal click...")
                            continue_button.click(timeout=5000)
                            print(f"       ✓ Button clicked successfully")
                except Exception as e:
                    # Last resort: force click
                    print(f"       ⚠️  Click failed: {str(e)[:100]}")
                    print(f"       Trying force click...")
                    try:
                        continue_button.click(force=True)
                        print(f"       ✓ Force click successful")
                    except Exception as e2:
                        print(f"       ✗ All click methods failed: {str(e2)[:100]}")
                        raise e2

                time.sleep(0.5)  # Brief wait for confirmation modal

                # Look for FINAL confirmation button (red Confirm button)
                print(f"     Looking for final Confirm button...")
                final_confirm_selectors = [
                    'button:has-text("Confirm")',
                    'button:has-text("confirm")',
                    'button[class*="confirm" i]',
                    'button[type="submit"]'
                ]

                final_button_found = False
                for selector in final_confirm_selectors:
                    try:
                        # Check all frames including main page
                        all_frames = [self.page] + self.page.frames

                        for frame in all_frames:
                            try:
                                if frame.locator(selector).count() > 0:
                                    buttons = frame.locator(selector).all()
                                    for btn in buttons:
                                        try:
                                            btn_text = btn.inner_text().strip().lower()
                                            if 'confirm' in btn_text and btn.is_visible() and not btn.is_disabled():
                                                print(f"       ✓ Found Confirm button: '{btn_text}'")
                                                btn.scroll_into_view_if_needed(timeout=1000)
                                                time.sleep(0.3)
                                                btn.click(timeout=3000)
                                                print(f"       ✓ Final Confirm button clicked!")
                                                final_button_found = True
                                                break
                                        except:
                                            continue
                                    if final_button_found:
                                        break
                            except:
                                continue
                        if final_button_found:
                            break
                    except:
                        continue

                if final_button_found:
                    time.sleep(1)  # Wait for booking to complete
                else:
                    print(f"       ⚠️  Final Confirm button not found (may not be needed)")
                    time.sleep(0.5)

            # Look for confirmation or final booking button
            final_button_selectors = [
                'button:has-text("Reserve Now")',
                'button:has-text("Complete Reservation")',
                'button:has-text("Confirm")',
                'button:has-text("Book Now")'
            ]

            final_button = None
            for selector in final_button_selectors:
                if self.page.locator(selector).count() > 0:
                    buttons = self.page.locator(selector).all()
                    for btn in buttons:
                        if btn.is_visible() and not btn.is_disabled():
                            final_button = btn
                            break
                if final_button:
                    break

            if final_button:
                print(f"     ⚠️  Final booking button found!")
                print(f"     This will COMPLETE the reservation.")

                print(f"     Clicking final booking button...")
                final_button.click()
                time.sleep(1)  # Brief wait for confirmation

            # Look for confirmation message
            print(f"     Checking for confirmation...")

            confirmation_selectors = [
                'text="Reservation Booked"',
                ':has-text("Reservation Booked")',
                'text="Confirmed"',
                'text="Your reservation is confirmed"',
                'text="Reservation confirmed"',
                ':has-text("check your inbox")',
                '[class*="Confirmation"]',
                '[class*="Success"]'
            ]

            is_confirmed = False
            for selector in confirmation_selectors:
                try:
                    # Check main page and all frames
                    all_frames = [self.page] + self.page.frames
                    for frame in all_frames:
                        try:
                            if frame.locator(selector).count() > 0:
                                print(f"     ✓ Booking confirmed! Found: {selector}")
                                is_confirmed = True
                                break
                        except:
                            continue
                    if is_confirmed:
                        break
                except:
                    continue

            if is_confirmed:
                # Try to extract confirmation details
                confirmation_number = None

                # Look for confirmation number
                try:
                    # Common patterns for confirmation numbers
                    conf_patterns = [
                        r'text=/Confirmation.*#\s*(\w+)/',
                        r'text=/Reference.*#\s*(\w+)/',
                        r'text=/Booking.*#\s*(\w+)/'
                    ]

                    for pattern in conf_patterns:
                        if self.page.locator(pattern).count() > 0:
                            text = self.page.locator(pattern).first.inner_text()
                            # Extract number from text
                            import re
                            match = re.search(r'#\s*(\w+)', text)
                            if match:
                                confirmation_number = match.group(1)
                                break
                except:
                    pass

                print(f"     ✅ Reservation successful!")
                if confirmation_number:
                    print(f"        Confirmation: {confirmation_number}")

                return {
                    'success': True,
                    'reservation_id': confirmation_number or f"resy-{venue_slug}-{date}",
                    'confirmation_token': None,  # Browser client doesn't have token
                    'config_id': config_id,
                    'date': date,
                    'party_size': party_size,
                    'venue_slug': venue_slug,
                    'time_slot': time_text
                }
            else:
                # Check for errors
                error_selectors = [
                    'text="reservation failed"',
                    'text="unable to book"',
                    'text="not available"',
                    '[role="alert"]'
                ]

                error_found = False
                error_message = ""
                for selector in error_selectors:
                    if self.page.locator(selector).count() > 0:
                        try:
                            error_message = self.page.locator(selector).first.inner_text()
                            error_found = True
                            break
                        except:
                            pass

                if error_found:
                    raise Exception(f"Booking failed: {error_message}")

                # Take screenshot for debugging
                screenshot_path = '/tmp/resy_booking_result.png'
                self.page.screenshot(path=screenshot_path)
                print(f"     Screenshot saved to: {screenshot_path}")

                # If no confirmation but no error, return uncertain status
                print(f"     ⚠️  Could not confirm booking status")
                return {
                    'success': False,
                    'error': 'Could not confirm reservation status',
                    'config_id': config_id,
                    'date': date,
                    'party_size': party_size
                }

        except Exception as e:
            print(f"     ✗ Reservation failed: {e}")

            # Take screenshot on error
            try:
                screenshot_path = '/tmp/resy_booking_error.png'
                self.page.screenshot(path=screenshot_path)
                print(f"     Screenshot saved to: {screenshot_path}")
            except:
                pass

            return {
                'success': False,
                'error': str(e),
                'config_id': config_id,
                'date': date,
                'party_size': party_size
            }

    def get_reservations(self) -> List[Dict]:
        """
        Get user's upcoming reservations.

        Note: Browser automation for reservation viewing not yet implemented.

        Returns:
            List of reservation dictionaries
        """
        print(f"    ⚠️  Browser client does not support get_reservations()")
        return []

    def cancel_reservation(self, resy_token: str) -> bool:
        """
        Cancel a reservation.

        Note: Browser automation for cancellation not yet implemented.

        Args:
            resy_token: Reservation token from booking

        Returns:
            bool: False (not implemented)
        """
        print(f"    ⚠️  Browser client does not support cancel_reservation()")
        return False

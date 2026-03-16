"""
Restaurant Reservation Agent
Interactive agent for making restaurant reservations via Resy.
"""

import json
import logging
import os
from datetime import datetime
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)
from utils.resy_client import ResyClient
from utils.reservation_store import ReservationStore
from utils.email_sender import EmailSender
from utils.slug_utils import parse_config_id, normalize_slug
from utils.resy_browser_client import _is_threading_error
from utils.browser_worker_manager import BrowserWorkerManager
from config.settings import Settings

# Path to browser search subprocess helper (used by one-shot fallback)
_BROWSER_SEARCH_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "browser_search.py"
)


class ReservationAgent(BaseAgent):
    """Interactive agent for making restaurant reservations on Resy."""

    def __init__(self, resy_client=None, resy_credentials=None):
        """Initialize the reservation agent.

        Args:
            resy_client: Optional pre-configured ResyClient (e.g. per-user from web API).
                         If None, falls back to factory + .env credentials.
            resy_credentials: Optional dict with email, password, auth_token for
                              deferred client creation (avoids Playwright threading issues).
                              Client is created fresh in each run() call's thread.
        """
        super().__init__()

        self._resy_credentials = resy_credentials

        if resy_client is not None:
            self.resy_client = resy_client
        elif resy_credentials is not None:
            # Client will be created in run() to avoid Playwright threading issues
            self.resy_client = None
        else:
            # Check if Resy is configured (API or browser mode)
            if not Settings.has_resy_configured() and not Settings.has_resy_browser_configured():
                raise ValueError(
                    "Resy not configured. Please add to .env file:\n"
                    "  For API mode: RESY_API_KEY + RESY_AUTH_TOKEN\n"
                    "  For Browser mode: RESY_EMAIL + RESY_PASSWORD"
                )

            # Use factory to select between API and browser clients
            from utils.resy_client_factory import ResyClientFactory
            self.resy_client = ResyClientFactory.create_client()

        self.store = ReservationStore()

        # Email sender for confirmations (optional)
        if Settings.has_email_configured():
            self.email_sender = EmailSender()
        else:
            self.email_sender = None

        # System prompt with date/time parsing guidance
        from zoneinfo import ZoneInfo
        now_est = datetime.now(ZoneInfo("America/New_York"))
        today_str = now_est.strftime("%B %d, %Y")
        time_str = now_est.strftime("%I:%M %p %Z")
        current_year = now_est.year
        self.system_prompt = f"""You are a helpful restaurant reservation assistant.

CRITICAL DATE PARSING RULES:
- Today's date is {today_str}
- Current time is {time_str}
- All times are in Eastern Time (EST/EDT). Always use ET for drop times and scheduling.
- Current year is {current_year}
- When parsing dates:
  * If user says "Feb 25" or "February 25" without a year, assume {current_year}
  * If user says "Wednesday Feb 25th", check which year has Feb 25 on a Wednesday near current date and use {current_year}
  * Always use YYYY-MM-DD format (e.g., "{current_year}-02-25")
  * NEVER use past years for future dates
  * If a date in the current month has already passed, assume next year

Examples:
- "Feb 25" → "{current_year}-02-25"
- "March 1st" → "{current_year}-03-01"
- "next Wednesday" → calculate from today ({today_str})

When making reservations:
1. Search for the restaurant by name or browse by cuisine/neighborhood
2. If search results include config_ids with time slots, you can book directly — no need to check availability separately
3. If booking for a different date than the search, construct a config_id as: slug|||YYYY-MM-DD|||time (e.g., "dr-clark|||2026-02-26|||8:00 PM")
4. Always confirm the booking details with the user before calling make_resy_reservation
5. Always format dates as YYYY-MM-DD when calling tools

AVAILABILITY RESPONSE FORMAT:
- When the user asks to check availability and slots ARE found, respond with: "Yes, [restaurant] has availability on [date]!" followed by the available time slots, then ask: "Please let me know if you'd like to make a reservation."
- When the user asks to check availability and NO slots are found, respond with: "No, [restaurant] doesn't have availability for [party_size] on [date]." then suggest trying a different date, time, or party size.

IMPORTANT BEHAVIORS:
- After a search returns results, present them to the user IMMEDIATELY. Do not make additional tool calls unless the user asks for something new.
- If search_resy_restaurants finds nothing, try search_resy_by_cuisine as a fallback before telling the user.
- If a tool returns an error or no results, explain what happened and suggest alternatives (different date, time, spelling, or cuisine search).
- If make_resy_reservation returns an unconfirmed status (success but no confirmation number), tell the user the booking was likely submitted and to check their email/Resy app for confirmation. Do NOT say it failed.
- If make_resy_reservation returns status 'conflict', the user already has a reservation that conflicts with this time slot (possibly at a different restaurant). Present the conflict details (the conflicting restaurant name and message) and ask the user whether they want to cancel the existing reservation and continue with the new booking, or keep the existing reservation. Then call resolve_reservation_conflict with their choice.
- Answer follow-up questions from conversation context when possible — don't re-call tools for data you already have.
- When the user wants to snipe or schedule a reservation for a future drop, use the schedule_sniper tool. Ask for the restaurant name (or slug), date, preferred time, and drop time (when availability opens). Use the slug from search results if available, otherwise the agent will convert the name automatically. If the sniper fails because the slug couldn't be resolved, ask the user for the exact slug from the Resy URL.
- Before scheduling, call get_current_time to get the accurate current time for computing drop times.
- When the user asks about their sniper jobs or scheduled snipes, use the view_sniper_jobs tool."""

    def define_tools(self):
        """Define Claude tools for reservation tasks."""
        return [
            {
                "name": "search_resy_restaurants",
                "description": "Search for restaurants on Resy by name, cuisine type, or neighborhood. Use this when the user wants to find restaurants.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Restaurant name, cuisine type, or neighborhood to search for"
                        },
                        "location": {
                            "type": "string",
                            "description": "City or neighborhood to narrow the search (optional)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "check_resy_availability",
                "description": "Check available time slots at a specific Resy restaurant for a given date and party size. Use this after finding a restaurant to see when tables are available.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "venue_id": {
                            "type": "string",
                            "description": "The Resy venue ID from search results"
                        },
                        "date": {
                            "type": "string",
                            "description": "Reservation date in YYYY-MM-DD format"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of guests"
                        }
                    },
                    "required": ["venue_id", "date", "party_size"]
                }
            },
            {
                "name": "make_resy_reservation",
                "description": "Book a reservation on Resy. Use this immediately after finding availability to automatically complete the booking for the user.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "config_id": {
                            "type": "string",
                            "description": "The configuration ID from the availability slot"
                        },
                        "date": {
                            "type": "string",
                            "description": "Reservation date in YYYY-MM-DD format"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of guests"
                        }
                    },
                    "required": ["config_id", "date", "party_size"]
                }
            },
            {
                "name": "search_resy_by_cuisine",
                "description": "Browse restaurants on Resy by cuisine type and/or neighborhood/area. Returns venues with available time slots and config_ids for direct booking. Use this when the user wants to discover restaurants by category (e.g., 'Japanese restaurants in Manhattan', 'Italian in West Village').",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cuisine": {
                            "type": "string",
                            "description": "Cuisine type (e.g., Japanese, Italian, French, Chinese, Korean, Mexican, Seafood, Steakhouse)"
                        },
                        "neighborhood": {
                            "type": "string",
                            "description": "Neighborhood or area (e.g., Soho, West Village, Chinatown, Manhattan, Brooklyn). Boroughs work as broad area filters."
                        },
                        "location": {
                            "type": "string",
                            "description": "City code (ny, sf, la). Defaults to ny."
                        },
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format. Defaults to today."
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of guests. Defaults to 2."
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "resolve_reservation_conflict",
                "description": "Resolve an existing reservation conflict. Use when make_resy_reservation returns status 'conflict'. 'continue_booking' cancels the existing reservation and proceeds with the new one. 'keep_existing' keeps the current reservation and aborts the new booking.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "choice": {
                            "type": "string",
                            "enum": ["continue_booking", "keep_existing"],
                            "description": "continue_booking = cancel existing and book new; keep_existing = abort new booking"
                        },
                        "config_id": {
                            "type": "string",
                            "description": "config_id from the conflict result"
                        },
                        "date": {
                            "type": "string",
                            "description": "Date from the conflict result"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Party size from the conflict result"
                        }
                    },
                    "required": ["choice", "config_id", "date", "party_size"]
                }
            },
            {
                "name": "view_my_reservations",
                "description": "View the user's upcoming reservations on Resy. Use this when the user asks about their current bookings.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_current_time",
                "description": "Get the current date and time in Eastern Time (EST/EDT). Use this before scheduling a sniper job to ensure accurate drop times.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "view_sniper_jobs",
                "description": "View all scheduled reservation sniper jobs and their statuses. Shows restaurant, requested date/time, drop time, and current status for each job.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "schedule_sniper",
                "description": "Schedule a reservation sniper to automatically book a table when availability drops. The sniper will rapid-poll at the specified drop time and grab the first matching slot.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "restaurant": {
                            "type": "string",
                            "description": "Restaurant name or Resy slug (e.g., 'Fish Cheeks' or 'fish-cheeks')"
                        },
                        "date": {
                            "type": "string",
                            "description": "Reservation date in YYYY-MM-DD format"
                        },
                        "preferred_time": {
                            "type": "string",
                            "description": "Preferred time slot (e.g., '7:00 PM')"
                        },
                        "party_size": {
                            "type": "integer",
                            "description": "Number of guests (default: 2)"
                        },
                        "drop_time": {
                            "type": "string",
                            "description": "When availability drops, ISO datetime (e.g., '2026-02-22T09:00:00')"
                        }
                    },
                    "required": ["restaurant", "date", "preferred_time", "drop_time"]
                }
            }
        ]

    def execute_tool(self, tool_name, tool_input):
        """
        Execute tool calls from Claude.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Dictionary of tool input parameters

        Returns:
            Tool execution result as dictionary
        """
        logger.info("Executing: %s", tool_name)

        if tool_name == "search_resy_restaurants":
            search_args = {"query": tool_input["query"], "location": tool_input.get("location")}
            try:
                results = self.resy_client.search_venues(**search_args)
            except Exception as e:
                if _is_threading_error(e):
                    fallback = self._handle_threading_fallback("search_venues", search_args)
                    if not fallback.get("success"):
                        return fallback
                    results = fallback.get("results", [])
                else:
                    raise

            # Format results for Claude
            if results:
                formatted = []
                for r in results[:5]:  # Limit to top 5 results
                    location_info = r.get('location', {})
                    neighborhood = location_info.get('neighborhood') if isinstance(location_info, dict) else None
                    city = location_info.get('city') if isinstance(location_info, dict) else None
                    location_str = f"{neighborhood}, {city}" if neighborhood else city

                    formatted.append({
                        'id': r.get('id'),
                        'name': r.get('name'),
                        'slug': r.get('url_slug'),
                        'location': location_str,
                        'price_range': r.get('price_range'),
                        'rating': r.get('rating')
                    })
                return {
                    'success': True,
                    'count': len(formatted),
                    'restaurants': formatted
                }
            else:
                return {
                    'success': False,
                    'message': 'No restaurants found matching that search. Try search_resy_by_cuisine to browse by cuisine type instead.',
                    'query': tool_input["query"]
                }

        elif tool_name == "search_resy_by_cuisine":
            cuisine_args = {
                "cuisine": tool_input.get("cuisine"),
                "neighborhood": tool_input.get("neighborhood"),
                "location": tool_input.get("location", "ny"),
                "date": tool_input.get("date"),
                "party_size": tool_input.get("party_size", 2)
            }

            # If current client doesn't support cuisine search, use browser subprocess
            if not hasattr(self.resy_client, 'search_by_cuisine'):
                fallback = self._handle_threading_fallback("search_by_cuisine", cuisine_args)
                if not fallback.get("success"):
                    return fallback
                results = fallback.get("results", [])
            else:
                try:
                    results = self.resy_client.search_by_cuisine(**cuisine_args)
                except Exception as e:
                    if _is_threading_error(e):
                        fallback = self._handle_threading_fallback("search_by_cuisine", cuisine_args)
                        if not fallback.get("success"):
                            return fallback
                        results = fallback.get("results", [])
                    else:
                        raise

            if results:
                formatted = []
                for r in results:
                    venue = {
                        'name': r.get('name'),
                        'slug': r.get('slug'),
                        'rating': r.get('rating'),
                        'review_count': r.get('review_count'),
                        'cuisine': r.get('cuisine'),
                        'price_range': r.get('price_range'),
                        'neighborhood': r.get('neighborhood'),
                    }
                    # Include available time slots
                    times = r.get('available_times', [])
                    if times:
                        venue['available_times'] = [
                            {'time': t['time'], 'type': t['type'], 'config_id': t['config_id']}
                            for t in times
                        ]
                    formatted.append(venue)

                return {
                    'success': True,
                    'count': len(formatted),
                    'restaurants': formatted,
                    'neighborhood_filter': tool_input.get("neighborhood"),
                }
            else:
                return {
                    'success': False,
                    'message': 'No restaurants found for this cuisine/neighborhood combination. Try a broader search (remove neighborhood or try a different cuisine).',
                    'cuisine': tool_input.get("cuisine"),
                    'neighborhood': tool_input.get("neighborhood")
                }

        elif tool_name == "check_resy_availability":
            avail_args = {
                "venue_id": tool_input["venue_id"],
                "date": tool_input["date"],
                "party_size": tool_input["party_size"]
            }
            try:
                slots = self.resy_client.get_availability(**avail_args)
            except Exception as e:
                if _is_threading_error(e):
                    fallback = self._handle_threading_fallback("get_availability", avail_args)
                    if not fallback.get("success"):
                        return fallback
                    slots = fallback.get("results", [])
                else:
                    raise

            if slots:
                # Format slots for Claude
                formatted_slots = []
                for slot in slots:
                    formatted_slots.append({
                        'config_id': slot['config_id'],
                        'time': slot['time'],
                        'table_type': slot['table_name']
                    })

                return {
                    'success': True,
                    'count': len(formatted_slots),
                    'available_times': formatted_slots,
                    'date': tool_input["date"],
                    'party_size': tool_input["party_size"]
                }
            else:
                return {
                    'success': False,
                    'message': f'No availability found for {tool_input["party_size"]} people on {tool_input["date"]}. Suggest the user try a different date, time, or party size.'
                }

        elif tool_name == "make_resy_reservation":
            reservation_args = {
                "config_id": tool_input["config_id"],
                "date": tool_input["date"],
                "party_size": tool_input["party_size"]
            }
            try:
                result = self.resy_client.make_reservation(**reservation_args)
            except Exception as e:
                if _is_threading_error(e):
                    result = self._handle_threading_fallback("make_reservation", reservation_args)
                else:
                    raise

            if result.get('success'):
                self._save_reservation(result, tool_input)

                # If no confirmation number, flag as unconfirmed
                if not result.get('reservation_id'):
                    result['message'] = 'Booking was submitted but confirmation could not be verified automatically. The user should check their email or Resy app for confirmation.'

                return result
            else:
                if result.get('status') == 'modal_opened':
                    result['message'] = 'Booking modal opened but Reserve Now button could not be clicked. The sniper will retry automatically.'
                elif 'Could not confirm' in result.get('error', ''):
                    result['message'] = 'The booking may have been submitted but we could not verify confirmation on the page. Advise the user to check their Resy app or email.'
                return result

        elif tool_name == "resolve_reservation_conflict":
            # Extract venue_slug and time_text from config_id if available
            config_id_val = tool_input.get("config_id", "")
            venue_slug = None
            time_text = None
            if config_id_val:
                try:
                    parsed = parse_config_id(config_id_val)
                    venue_slug = parsed['venue_slug']
                    time_text = parsed['time_text']
                except ValueError:
                    pass

            conflict_args = {
                "choice": tool_input["choice"],
                "config_id": config_id_val,
                "date": tool_input.get("date"),
                "party_size": tool_input.get("party_size"),
                "venue_slug": venue_slug,
                "time_text": time_text
            }
            try:
                result = self.resy_client.resolve_reservation_conflict(**conflict_args)
            except Exception as e:
                if _is_threading_error(e):
                    result = self._handle_threading_fallback("resolve_reservation_conflict", conflict_args)
                else:
                    raise

            if result.get('success') and result.get('status') != 'kept_existing':
                self._save_reservation(result, tool_input)

            return result

        elif tool_name == "view_my_reservations":
            try:
                reservations = self.resy_client.get_reservations()
            except Exception as e:
                if _is_threading_error(e):
                    fallback = self._handle_threading_fallback("get_reservations", {})
                    if not fallback.get("success"):
                        return fallback
                    reservations = fallback.get("results", [])
                else:
                    raise

            if reservations:
                return {
                    'success': True,
                    'count': len(reservations),
                    'reservations': reservations
                }
            else:
                return {
                    'success': True,
                    'count': 0,
                    'message': 'No upcoming reservations found'
                }

        elif tool_name == "get_current_time":
            from zoneinfo import ZoneInfo
            now_est = datetime.now(ZoneInfo("America/New_York"))
            return {
                'success': True,
                'datetime': now_est.strftime("%Y-%m-%dT%H:%M:%S"),
                'display': now_est.strftime("%B %d, %Y %I:%M %p %Z"),
            }

        elif tool_name == "view_sniper_jobs":
            jobs = self.store.get_all_sniper_jobs()
            if jobs:
                formatted = []
                for j in jobs:
                    formatted.append({
                        'job_id': j['id'],
                        'restaurant': j['venue_slug'],
                        'date': j['date'],
                        'preferred_times': j['preferred_times'],
                        'party_size': j['party_size'],
                        'status': j['status'],
                        'scheduled_at': j['scheduled_at'],
                        'poll_count': j['poll_count'],
                        'max_attempts': j['max_attempts'],
                        'notes': j.get('notes'),
                    })
                return {
                    'success': True,
                    'count': len(formatted),
                    'jobs': formatted,
                }
            else:
                return {
                    'success': True,
                    'count': 0,
                    'message': 'No sniper jobs found',
                }

        elif tool_name == "schedule_sniper":
            return self._schedule_sniper(tool_input)

        else:
            return {
                'success': False,
                'error': f'Unknown tool: {tool_name}'
            }

    def _browser_search_subprocess(self, method: str, args: dict) -> dict:
        """Run a browser operation via the persistent worker (or one-shot fallback).

        Routes through BrowserWorkerManager which keeps Chromium warm.
        Falls back to one-shot subprocess if the worker is unavailable.

        Args:
            method: Method name (e.g. 'search_venues', 'search_by_cuisine')
            args: Dict of arguments to pass to the method

        Returns:
            Dict with 'success' and 'results' or 'error'
        """
        manager = BrowserWorkerManager.get_instance()
        return manager.send_command(
            method=method,
            args=args,
            timeout=120,
            resy_credentials=self._resy_credentials,
        )

    def _handle_threading_fallback(self, method: str, args: dict) -> dict:
        """Handle Playwright threading error with subprocess fallback.

        Returns the raw subprocess result dict. For search methods this has
        {"success": True, "results": [...]}, for action methods it passes
        through the browser client's result structure directly.
        """
        logger.info("Threading error, falling back to subprocess for: %s", method)
        sub_result = self._browser_search_subprocess(method, args)
        if not sub_result.get("success") and "error" in sub_result:
            sub_result['message'] = sub_result.pop('error')
        return sub_result

    def _save_reservation(self, result: dict, tool_input: dict) -> None:
        """Save a reservation to the database.

        Args:
            result: Result dict from resy_client with venue_slug, time_slot, etc.
            tool_input: Tool input dict with date, party_size, etc.
        """
        has_confirmation = bool(result.get('reservation_id'))
        status = 'confirmed' if has_confirmation else 'pending_confirmation'
        self.store.add_reservation({
            'platform': 'resy',
            'restaurant_name': result.get('venue_slug', 'Restaurant'),
            'date': tool_input.get('date', ''),
            'time': result.get('time_slot', 'Time TBD'),
            'party_size': tool_input.get('party_size', 0),
            'confirmation_token': result.get('confirmation_token'),
            'confirmation_number': result.get('reservation_id'),
            'status': status
        })

    def _schedule_sniper(self, tool_input: dict) -> dict:
        """Schedule a sniper job, remotely via SSH if configured, otherwise locally."""
        import shlex
        import subprocess

        restaurant = tool_input["restaurant"]
        # If it looks like a human name (has spaces or uppercase), convert to slug
        if ' ' in restaurant or restaurant != restaurant.lower():
            venue_slug = normalize_slug(restaurant)
        else:
            venue_slug = restaurant
        date = tool_input["date"]
        preferred_time = tool_input["preferred_time"]
        party_size = tool_input.get("party_size", Settings.DEFAULT_PARTY_SIZE)
        drop_time = tool_input["drop_time"]

        remote_host = Settings.SNIPER_REMOTE_HOST
        if remote_host:
            remote_dir = Settings.SNIPER_REMOTE_DIR
            remote_cmd = (
                f"cd {shlex.quote(remote_dir)} && python3 scripts/run_sniper.py "
                f"{shlex.quote(venue_slug)} {shlex.quote(date)} {shlex.quote(preferred_time)} "
                f"--party-size {shlex.quote(str(party_size))} --at {shlex.quote(drop_time)}"
            )
            cmd = [
                "ssh", "-o", "StrictHostKeyChecking=accept-new", remote_host,
                remote_cmd,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                output = result.stdout.strip()
                if result.returncode == 0:
                    # Save a local record so we can track remote jobs
                    job_id = self.store.add_sniper_job({
                        'venue_slug': venue_slug,
                        'date': date,
                        'preferred_times': [preferred_time],
                        'party_size': party_size,
                        'scheduled_at': drop_time,
                        'auto_resolve_conflicts': True,
                        'notes': f'remote:{remote_host}',
                    })
                    return {
                        'success': True,
                        'job_id': job_id,
                        'message': f"Remote sniper scheduled on server: {output}",
                        'venue_slug': venue_slug,
                        'remote': True,
                    }
                else:
                    return {
                        'success': False,
                        'error': f"SSH command failed: {result.stderr.strip()}",
                    }
            except subprocess.TimeoutExpired:
                return {'success': False, 'error': 'SSH connection timed out'}
            except Exception as e:
                return {'success': False, 'error': f'SSH failed: {e}'}
        else:
            from utils.reservation_sniper import ReservationSniper
            sniper = ReservationSniper(
                client=self.resy_client,
                store=self.store,
            )
            job_id = sniper.create_job(
                venue_slug=venue_slug,
                date=date,
                preferred_times=[preferred_time],
                party_size=party_size,
                scheduled_at=drop_time,
                auto_resolve_conflicts=True,
            )
            return {
                'success': True,
                'job_id': job_id,
                'venue_slug': venue_slug,
                'message': (
                    f"Sniper job #{job_id} scheduled for {venue_slug} "
                    f"on {date} at {preferred_time}. "
                    f"Will start polling at {drop_time}. "
                    f"Run `python3 scripts/run_sniper.py --cron` to execute when ready."
                ),
            }

    def _format_confirmation_email(self, result, booking_info):
        """Format a confirmation email in markdown."""
        return f"""# Reservation Confirmed! 🎉

Your reservation has been successfully booked.

## Confirmation Details

- **Confirmation Number:** {result['reservation_id']}
- **Date:** {booking_info['date']}
- **Party Size:** {booking_info['party_size']} people

## What's Next?

- You'll receive a confirmation from Resy directly
- Add this to your calendar
- Arrive on time (Resy restaurants typically hold tables for 15 minutes)

---
*Booked via your AI Reservation Agent*
"""

    def run(self, user_message, max_iterations=10, event_callback=None):
        """
        Run the agent with a user message.

        Args:
            user_message: The user's request
            max_iterations: Maximum number of tool use iterations
            event_callback: Optional callable(event_type, data) for streaming events.
                           Event types: 'thinking', 'tool_call', 'tool_result', 'message', 'done'

        Returns:
            Final response from the agent
        """
        logger.info("Reservation Agent processing request")

        # Create a fresh browser client in this thread if using deferred credentials.
        # This avoids Playwright threading errors since each run() executes in
        # its own daemon thread (SSE streaming), and Playwright is thread-bound.
        if self._resy_credentials:
            from api.session import _create_client_for_user
            self.resy_client = _create_client_for_user(**self._resy_credentials)

        def emit(event_type, data=None):
            if event_callback:
                event_callback(event_type, data or {})

        # Add user message to history
        self.add_to_history("user", user_message)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            logger.debug("Thinking (iteration %d)", iteration)
            emit("thinking", {"iteration": iteration})

            # Call Claude with tool definitions and system prompt
            response = self.call_claude(
                messages=self.conversation_history,
                tools=self.define_tools(),
                system=self.system_prompt
            )

            logger.debug("Stop reason: %s", response.stop_reason)

            if response.stop_reason == "tool_use":
                # Add Claude's response to history
                self.add_to_history("assistant", response.content)

                # Execute all tool calls
                tool_results = []
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        tool_use_id = content_block.id

                        logger.info("Using tool: %s", tool_name)
                        emit("tool_call", {"tool": tool_name, "input": tool_input})

                        # Execute the tool
                        result = self.execute_tool(tool_name, tool_input)

                        emit("tool_result", {"tool": tool_name, "result": result})

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(result)
                        })

                # Add tool results to history
                self.add_to_history("user", tool_results)

            elif response.stop_reason == "end_turn":
                # Claude is done and provided a final answer
                self.add_to_history("assistant", response.content)

                # Extract text from response
                final_answer = ""
                for content_block in response.content:
                    if hasattr(content_block, "text"):
                        final_answer += content_block.text

                logger.info("Final response generated")
                emit("message", {"text": final_answer})
                emit("done")
                return final_answer

            else:
                # Unexpected stop reason
                logger.warning("Unexpected stop reason: %s", response.stop_reason)
                break

        logger.warning("Max iterations (%d) reached", max_iterations)
        msg = "I apologize, but I've reached my maximum thinking iterations. Please try rephrasing your request."
        emit("message", {"text": msg})
        emit("done")
        return msg

    def chat(self):
        """Interactive chat mode for reservations."""
        print("\n" + "="*60)
        print("🤖 Reservation Agent - Interactive Mode")
        print("="*60)
        print("Tell me what reservation you'd like to make!")
        print()
        print("Examples:")
        print("  - 'Find Italian restaurants in Manhattan'")
        print("  - 'Check availability at Carbone for Friday at 7pm for 2'")
        print("  - 'Book it!'")
        print()
        print("Type 'quit' or 'exit' to stop")
        print("Type 'clear' to clear conversation history")
        print("="*60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ['quit', 'exit']:
                    print("👋 Goodbye!")
                    break

                if user_input.lower() == 'clear':
                    self.clear_history()
                    print("🗑️  Conversation history cleared\n")
                    continue

                if not user_input:
                    continue

                response = self.run(user_input)
                if response:
                    print(f"\nAgent: {response}\n")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                logger.error("Error: %s", e)
                print(f"Error: {e}")

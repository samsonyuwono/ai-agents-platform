"""
Restaurant Reservation Agent
Interactive agent for making restaurant reservations via Resy.
"""

import json
import logging
from datetime import datetime
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)
from utils.resy_client import ResyClient
from utils.reservation_store import ReservationStore
from utils.email_sender import EmailSender
from utils.slug_utils import parse_config_id
from config.settings import Settings


class ReservationAgent(BaseAgent):
    """Interactive agent for making restaurant reservations on Resy."""

    def __init__(self):
        """Initialize the reservation agent."""
        super().__init__()

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

        # System prompt with date parsing guidance
        today = datetime.now()
        today_str = today.strftime("%B %d, %Y")
        current_year = today.year
        self.system_prompt = f"""You are a helpful restaurant reservation assistant.

CRITICAL DATE PARSING RULES:
- Today's date is {today_str}
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
- When the user wants to snipe or schedule a reservation for a future drop, use the schedule_sniper tool. Ask for the restaurant slug, date, preferred time, and drop time (when availability opens)."""

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
                "name": "schedule_sniper",
                "description": "Schedule a reservation sniper to automatically book a table when availability drops. The sniper will rapid-poll at the specified drop time and grab the first matching slot.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "venue_slug": {
                            "type": "string",
                            "description": "Restaurant slug from Resy URL (e.g., 'fish-cheeks', 'temple-court')"
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
                    "required": ["venue_slug", "date", "preferred_time", "drop_time"]
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
            results = self.resy_client.search_venues(
                query=tool_input["query"],
                location=tool_input.get("location")
            )

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
            # Check if browser client is available (has search_by_cuisine method)
            if not hasattr(self.resy_client, 'search_by_cuisine'):
                return {
                    'success': False,
                    'message': 'Cuisine search requires browser mode. Set RESY_CLIENT_MODE=browser in .env'
                }

            results = self.resy_client.search_by_cuisine(
                cuisine=tool_input.get("cuisine"),
                neighborhood=tool_input.get("neighborhood"),
                location=tool_input.get("location", "ny"),
                date=tool_input.get("date"),
                party_size=tool_input.get("party_size", 2)
            )

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
                    'restaurants': formatted
                }
            else:
                return {
                    'success': False,
                    'message': 'No restaurants found for this cuisine/neighborhood combination. Try a broader search (remove neighborhood or try a different cuisine).',
                    'cuisine': tool_input.get("cuisine"),
                    'neighborhood': tool_input.get("neighborhood")
                }

        elif tool_name == "check_resy_availability":
            slots = self.resy_client.get_availability(
                venue_id=tool_input["venue_id"],
                date=tool_input["date"],
                party_size=tool_input["party_size"]
            )

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
            result = self.resy_client.make_reservation(
                config_id=tool_input["config_id"],
                date=tool_input["date"],
                party_size=tool_input["party_size"]
            )

            if result.get('success'):
                self._save_reservation(result, tool_input)

                # If status is modal_opened or no confirmation number, flag as unconfirmed
                if result.get('status') == 'modal_opened' or not result.get('reservation_id'):
                    result['message'] = 'Booking was submitted but confirmation could not be verified automatically. The user should check their email or Resy app for confirmation.'

                return result
            else:
                # Check if error suggests the booking might have gone through
                error_msg = result.get('error', '')
                if 'Could not confirm' in error_msg:
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

            result = self.resy_client.resolve_reservation_conflict(
                choice=tool_input["choice"],
                config_id=config_id_val,
                date=tool_input.get("date"),
                party_size=tool_input.get("party_size"),
                venue_slug=venue_slug,
                time_text=time_text
            )

            if result.get('success') and result.get('status') != 'kept_existing':
                self._save_reservation(result, tool_input)

            return result

        elif tool_name == "view_my_reservations":
            reservations = self.resy_client.get_reservations()

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

        elif tool_name == "schedule_sniper":
            from utils.reservation_sniper import ReservationSniper

            sniper = ReservationSniper(
                client=self.resy_client,
                store=self.store,
            )
            job_id = sniper.create_job(
                venue_slug=tool_input["venue_slug"],
                date=tool_input["date"],
                preferred_times=[tool_input["preferred_time"]],
                party_size=tool_input.get("party_size", Settings.DEFAULT_PARTY_SIZE),
                scheduled_at=tool_input["drop_time"],
                auto_resolve_conflicts=True,
            )
            return {
                'success': True,
                'job_id': job_id,
                'message': (
                    f"Sniper job #{job_id} scheduled for {tool_input['venue_slug']} "
                    f"on {tool_input['date']} at {tool_input['preferred_time']}. "
                    f"Will start polling at {tool_input['drop_time']}. "
                    f"Run `python3 scripts/run_sniper.py --cron` to execute when ready."
                ),
            }

        else:
            return {
                'success': False,
                'error': f'Unknown tool: {tool_name}'
            }

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

    def run(self, user_message, max_iterations=10):
        """
        Run the agent with a user message.

        Args:
            user_message: The user's request
            max_iterations: Maximum number of tool use iterations

        Returns:
            Final response from the agent
        """
        logger.info("Reservation Agent processing request")

        # Add user message to history
        self.add_to_history("user", user_message)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            logger.debug("Thinking (iteration %d)", iteration)

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

                        # Execute the tool
                        result = self.execute_tool(tool_name, tool_input)

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
                return final_answer

            else:
                # Unexpected stop reason
                logger.warning("Unexpected stop reason: %s", response.stop_reason)
                break

        logger.warning("Max iterations (%d) reached", max_iterations)
        return "I apologize, but I've reached my maximum thinking iterations. Please try rephrasing your request."

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

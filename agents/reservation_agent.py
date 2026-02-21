"""
Restaurant Reservation Agent
Interactive agent for making restaurant reservations via Resy.
"""

import json
from agents.base_agent import BaseAgent
from utils.resy_client import ResyClient
from utils.reservation_store import ReservationStore
from utils.email_sender import EmailSender
from config.settings import Settings


class ReservationAgent(BaseAgent):
    """Interactive agent for making restaurant reservations on Resy."""

    def __init__(self):
        """Initialize the reservation agent."""
        super().__init__()

        # Check if Resy is configured
        if not Settings.has_resy_configured():
            raise ValueError(
                "Resy API not configured. Please add RESY_API_KEY and RESY_AUTH_TOKEN to .env"
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
        self.system_prompt = """You are a helpful restaurant reservation assistant.

CRITICAL DATE PARSING RULES:
- Today's date is February 16, 2026
- Current year is 2026
- When parsing dates:
  * If user says "Feb 25" or "February 25" without a year, assume 2026
  * If user says "Wednesday Feb 25th", check which year has Feb 25 on a Wednesday near current date and use 2026
  * Always use YYYY-MM-DD format (e.g., "2026-02-25")
  * NEVER use past years (2024, 2025) for future dates
  * If a date in the current month has already passed, assume next year

Examples:
- "Feb 25" → "2026-02-25"
- "Wednesday Feb 18th" → "2026-02-18" (current year)
- "March 1st" → "2026-03-01"
- "next Wednesday" → calculate from today (Feb 16, 2026)

When making reservations:
1. Search for the restaurant first
2. Check availability for the requested date/time
3. If a suitable slot is found, book it automatically
4. Always format dates as YYYY-MM-DD when calling tools"""

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
                "name": "view_my_reservations",
                "description": "View the user's upcoming reservations on Resy. Use this when the user asks about their current bookings.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
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
        print(f"\n🔧 Executing: {tool_name}")

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
                    'message': 'No restaurants found matching that search'
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
                    'message': f'No availability found for {tool_input["party_size"]} people on {tool_input["date"]}'
                }

        elif tool_name == "make_resy_reservation":
            result = self.resy_client.make_reservation(
                config_id=tool_input["config_id"],
                date=tool_input["date"],
                party_size=tool_input["party_size"]
            )

            if result.get('success'):
                # Save to database
                self.store.add_reservation({
                    'platform': 'resy',
                    'restaurant_name': 'Restaurant',  # We'll get this from context
                    'date': tool_input["date"],
                    'time': 'Time TBD',  # Get from config_id if needed
                    'party_size': tool_input["party_size"],
                    'confirmation_token': result['confirmation_token'],
                    'confirmation_number': result['reservation_id'],
                    'status': 'confirmed'
                })

                # Note: Email notification disabled - Resy sends confirmation email
                # Uncomment below to send additional notification via Resend
                # if self.email_sender:
                #     try:
                #         self.email_sender.send(
                #             to_email=Settings.EMAIL_TO,
                #             subject="🎉 Reservation Confirmed!",
                #             content=self._format_confirmation_email(result, tool_input),
                #             content_type="markdown"
                #         )
                #     except Exception as e:
                #         print(f"  ⚠️  Could not send email: {e}")

                return result
            else:
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

        else:
            return {
                'success': False,
                'error': f'Unknown tool: {tool_name}'
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

    def run(self, user_message, max_iterations=10):
        """
        Run the agent with a user message.

        Args:
            user_message: The user's request
            max_iterations: Maximum number of tool use iterations

        Returns:
            Final response from the agent
        """
        print(f"\n{'='*60}")
        print(f"🤖 Reservation Agent")
        print(f"{'='*60}\n")

        # Add user message to history
        self.add_to_history("user", user_message)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Thinking (iteration {iteration}) ---")

            # Call Claude with tool definitions and system prompt
            response = self.call_claude(
                messages=self.conversation_history,
                tools=self.define_tools(),
                system=self.system_prompt
            )

            print(f"  Stop reason: {response.stop_reason}")

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

                        print(f"  🔧 Using tool: {tool_name}")

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

                print(f"\n{'='*60}")
                print(f"✅ Response:")
                print(f"{'='*60}\n")
                print(final_answer)
                print(f"\n{'='*60}\n")

                return final_answer

            else:
                # Unexpected stop reason
                print(f"⚠️  Unexpected stop reason: {response.stop_reason}")
                break

        print(f"⚠️  Max iterations ({max_iterations}) reached")
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

                self.run(user_input)

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

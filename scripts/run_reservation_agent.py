#!/usr/bin/env python3
"""
Reservation Agent Runner
Entry point for the restaurant reservation agent.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.reservation_agent import ReservationAgent


def main():
    """Run the reservation agent."""
    print("""
╔══════════════════════════════════════════════════════════╗
║         Restaurant Reservation Agent                     ║
║         Powered by Claude + Resy                         ║
╚══════════════════════════════════════════════════════════╝

This agent can:
  • Search restaurants on Resy
  • Check availability for specific dates/times
  • Make reservations automatically
  • View your upcoming reservations
  • Send email confirmations
""")

    try:
        agent = ReservationAgent()

        # Check if running with arguments (single query mode)
        if len(sys.argv) > 1:
            query = " ".join(sys.argv[1:])
            agent.run(query)
        else:
            # Interactive chat mode
            agent.chat()

    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\nPlease ensure you have added the following to your .env file:")
        print("  - RESY_API_KEY")
        print("  - RESY_AUTH_TOKEN")
        print("  - RESY_PAYMENT_METHOD_ID (needed for booking)")
        print("\nSee .env file for instructions on how to obtain these.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

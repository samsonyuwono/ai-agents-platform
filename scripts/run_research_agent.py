#!/usr/bin/env python3
"""
Research Agent Runner
Entry point for the interactive research agent.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.research_agent import ResearchAgent


def main():
    """Run the research agent."""
    print("""
╔══════════════════════════════════════════════════════════╗
║           AI Research Agent                              ║
║           Built with Claude by Anthropic                 ║
╚══════════════════════════════════════════════════════════╝

This agent can:
  • Answer questions using its knowledge
  • Search the web for current information
  • Maintain conversation context
""")

    try:
        agent = ResearchAgent()

        # Choose mode
        mode = input("\nChoose mode:\n  1. Interactive chat\n  2. Single query\nEnter 1 or 2: ").strip()

        if mode == "1":
            agent.chat()
        else:
            query = input("\nWhat would you like to know? ")
            if query:
                agent.run(query)

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()

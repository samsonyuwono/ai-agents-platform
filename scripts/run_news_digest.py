#!/usr/bin/env python3
"""
News Digest Agent Runner
Entry point for the news digest agent.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.news_digest_agent import NewsDigestAgent


def main():
    """Run the news digest agent."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("""
Daily News Digest Agent
Powered by Claude + Brave Search
""")

    try:
        agent = NewsDigestAgent()

        # Check if topics provided as command-line arguments
        if len(sys.argv) > 1:
            # Topics provided via command line
            topics = [topic.strip() for topic in sys.argv[1:]]
            print(f"\nCreating digest for: {', '.join(topics)}")
        else:
            # Interactive mode - ask user
            print("What topics do you want in your news digest?")
            print("Enter topics separated by commas (e.g., AI, climate change, SpaceX)")
            print()

            topics_input = input("Topics: ").strip()

            if not topics_input:
                print("No topics provided. Using defaults...")
                topics = ["Artificial Intelligence", "Technology", "Science"]
            else:
                topics = [topic.strip() for topic in topics_input.split(",")]

            print(f"\nCreating digest for: {', '.join(topics)}")

        # Create the digest
        agent.create_digest(topics)

    except Exception as e:
        logging.getLogger(__name__).error("Error: %s", e)


if __name__ == "__main__":
    main()

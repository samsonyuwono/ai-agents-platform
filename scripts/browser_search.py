#!/usr/bin/env python3
"""
Subprocess helper for browser-based Resy searches.

Runs Playwright in its own process to avoid threading issues
when called from the web API's background thread.

Usage:
    python3 scripts/browser_search.py search_venues '{"query": "Carbone"}'
    python3 scripts/browser_search.py search_by_cuisine '{"cuisine": "Japanese", "neighborhood": "Manhattan"}'
"""

import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Redirect stdout to stderr so browser client print() statements
# don't pollute the JSON output. We write JSON to the original stdout at the end.
_real_stdout = sys.stdout
sys.stdout = sys.stderr


def output_json(data):
    """Write JSON result to the real stdout (not stderr)."""
    _real_stdout.write(json.dumps(data) + "\n")
    _real_stdout.flush()


def main():
    if len(sys.argv) < 3:
        output_json({"success": False, "error": "Usage: browser_search.py <method> <json_args>"})
        sys.exit(1)

    method = sys.argv[1]
    try:
        args = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        output_json({"success": False, "error": f"Invalid JSON args: {e}"})
        sys.exit(1)

    # Create browser client in this process (own thread = no greenlet issues)
    from utils.resy_browser_client import ResyBrowserClient
    client = ResyBrowserClient()

    try:
        if method == "search_venues":
            results = client.search_venues(
                query=args["query"],
                location=args.get("location")
            )
            output_json({"success": True, "results": results})

        elif method == "search_by_cuisine":
            results = client.search_by_cuisine(
                cuisine=args.get("cuisine"),
                neighborhood=args.get("neighborhood"),
                location=args.get("location", "ny"),
                date=args.get("date"),
                party_size=args.get("party_size", 2)
            )
            output_json({"success": True, "results": results})

        else:
            output_json({"success": False, "error": f"Unknown method: {method}"})
            sys.exit(1)

    except Exception as e:
        output_json({"success": False, "error": str(e)})
        sys.exit(1)
    finally:
        try:
            client._cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()

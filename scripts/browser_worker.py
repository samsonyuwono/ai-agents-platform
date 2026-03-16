#!/usr/bin/env python3
"""
Persistent browser worker for Resy operations.

Keeps a Chromium instance warm and authenticated, accepting JSON commands
via stdin and returning results via stdout. This avoids the ~2.5 min cold
start on every request.

Protocol:
  Startup: prints {"status": "ready"} when browser is authenticated
  Command: {"id": "abc", "method": "search_venues", "args": {...}}
  Response: {"id": "abc", "success": true, "results": [...]}
  Shutdown: {"id": "x", "method": "shutdown"} or idle timeout

Usage:
    python3 scripts/browser_worker.py
"""

import json
import os
import select
import sys
import time
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Redirect stdout to stderr so browser client print() statements
# don't pollute the JSON protocol. We write JSON to the original stdout.
_real_stdout = sys.stdout
sys.stdout = sys.stderr


def output_json(data):
    """Write JSON to the real stdout (protocol channel)."""
    _real_stdout.write(json.dumps(data) + "\n")
    _real_stdout.flush()


def _health_check(client):
    """Check if the browser page is still alive."""
    try:
        if client.page is None:
            return False
        client.page.evaluate("1+1")
        return True
    except Exception:
        return False


def _restart_browser(client):
    """Restart the browser and re-authenticate."""
    print("  ♻️  Restarting browser...")
    try:
        client._cleanup()
    except Exception:
        pass
    client._launch_browser()
    client._ensure_authenticated()
    print("  ✓ Browser restarted and authenticated")


def _dispatch(client, method, args):
    """Dispatch a command to the browser client, return result dict."""
    if method == "ping":
        alive = _health_check(client)
        return {"success": True, "status": "ok", "browser_alive": alive}

    if method == "shutdown":
        return {"success": True, "status": "shutting_down"}

    if method == "search_venues":
        results = client.search_venues(
            query=args["query"],
            location=args.get("location"),
        )
        return {"success": True, "results": results}

    if method == "search_by_cuisine":
        results = client.search_by_cuisine(
            cuisine=args.get("cuisine"),
            neighborhood=args.get("neighborhood"),
            location=args.get("location", "ny"),
            date=args.get("date"),
            party_size=args.get("party_size", 2),
        )
        return {"success": True, "results": results}

    if method == "get_availability":
        results = client.get_availability(
            venue_id=args["venue_id"],
            date=args["date"],
            party_size=args.get("party_size", 2),
        )
        return {"success": True, "results": results}

    if method == "make_reservation":
        result = client.make_reservation(
            config_id=args["config_id"],
            date=args["date"],
            party_size=args.get("party_size", 2),
            payment_method_id=args.get("payment_method_id"),
        )
        return result  # already has success/error structure

    if method == "get_reservations":
        results = client.get_reservations()
        return {"success": True, "results": results}

    if method == "resolve_reservation_conflict":
        result = client.resolve_reservation_conflict(
            choice=args["choice"],
            config_id=args.get("config_id"),
            date=args.get("date"),
            party_size=args.get("party_size"),
            venue_slug=args.get("venue_slug"),
            time_text=args.get("time_text"),
        )
        return result  # already has success/error structure

    return {"success": False, "error": f"Unknown method: {method}"}


def main():
    from config.settings import Settings

    idle_timeout = Settings.RESY_BROWSER_WORKER_IDLE_TIMEOUT

    # Create and initialize browser client
    from utils.resy_browser_client import ResyBrowserClient
    client = ResyBrowserClient()

    try:
        # Launch browser and authenticate
        client._launch_browser()
        client._ensure_authenticated()

        # Persist session to disk so one-shot fallback can reuse it
        try:
            client._save_session()
        except Exception:
            pass
    except Exception as e:
        output_json({"status": "error", "error": f"Startup failed: {e}"})
        sys.exit(1)

    # Signal readiness
    output_json({"status": "ready"})

    last_activity = time.time()

    # Main command loop — read JSON lines from stdin
    while True:
        # Check idle timeout
        if time.time() - last_activity > idle_timeout:
            print(f"  ⏰ Idle timeout ({idle_timeout}s) reached, shutting down")
            output_json({"status": "idle_shutdown"})
            break

        # Use select to poll stdin with a 1-second timeout so we can
        # check idle timeout periodically
        ready, _, _ = select.select([sys.stdin], [], [], 1.0)
        if not ready:
            continue

        line = _real_stdin_readline()
        if not line:
            # EOF — parent process closed stdin
            print("  📭 stdin closed, shutting down")
            break

        line = line.strip()
        if not line:
            continue

        last_activity = time.time()

        # Parse command
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            output_json({"error": f"Invalid JSON: {e}"})
            continue

        cmd_id = cmd.get("id")
        method = cmd.get("method", "")
        args = cmd.get("args", {})

        try:
            result = _dispatch(client, method, args)

            # Save session after successful operations
            if result.get("success") and method not in ("ping", "shutdown"):
                try:
                    client._save_session()
                except Exception:
                    pass

            if cmd_id is not None:
                result["id"] = cmd_id
            output_json(result)

            if method == "shutdown":
                break

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"  ❌ Error executing {method}: {error_msg}")
            traceback.print_exc()

            error_result = {"success": False, "error": error_msg}
            if cmd_id is not None:
                error_result["id"] = cmd_id
            output_json(error_result)

            # Check if browser is still alive, restart if crashed
            if not _health_check(client):
                try:
                    _restart_browser(client)
                except Exception as restart_err:
                    print(f"  💀 Browser restart failed: {restart_err}")
                    output_json({"status": "fatal", "error": str(restart_err)})
                    break

    # Cleanup
    try:
        client._cleanup()
    except Exception:
        pass


# We need the real stdin for reading commands (sys.stdin is still the real one
# since we only redirected stdout). Store a reference before anything changes.
_real_stdin = sys.stdin


def _real_stdin_readline():
    """Read a line from the real stdin."""
    return _real_stdin.readline()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Sniper Worker — continuous daemon for processing scheduled sniper jobs.

Replaces cron-based scheduling with an always-on loop. Designed to run
as a systemd service (see deploy/sniper.service).

Usage:
  python3 scripts/sniper_worker.py           # Run with default 10s poll interval
  SNIPER_WORKER_POLL_SECONDS=5 python3 scripts/sniper_worker.py  # Custom interval
"""

import logging
import os
import signal
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from config.settings import Settings
from utils.reservation_sniper import ReservationSniper
from utils.reservation_store import ReservationStore

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 10

_shutdown = False


def _handle_signal(signum, frame):
    """Set shutdown flag on SIGTERM/SIGINT for both worker and sniper."""
    global _shutdown
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, shutting down after current iteration...")
    _shutdown = True


def _clear_cookies_for_proxy():
    """Clear cached Resy cookies when proxy is configured so the session routes through the proxy."""
    if Settings.has_proxy_configured():
        cookie_file = Path.home() / '.resy_session_cookies.json'
        if cookie_file.exists():
            cookie_file.unlink()
            logger.info("Cleared cached cookies (proxy is configured)")


def _reset_stale_active_jobs():
    """Reset any jobs stuck in 'active' from a previous crashed worker."""
    with ReservationStore() as store:
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE sniper_jobs SET status = 'pending' WHERE status = 'active'"
        )
        store.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Reset {cursor.rowcount} stale active job(s) to pending")


def get_poll_interval() -> int:
    """Get poll interval from environment, defaulting to 10 seconds."""
    return int(os.environ.get("SNIPER_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS))


def run_loop(sniper: ReservationSniper, poll_seconds: int):
    """Main worker loop. Runs until shutdown signal received."""
    global _shutdown
    logger.info(f"Sniper worker started (poll every {poll_seconds}s)")

    while not _shutdown and not sniper._shutdown:
        try:
            result = sniper.run_scheduled_jobs()
            if result['jobs_run'] > 0:
                logger.info(f"Ran {result['jobs_run']} job(s)")
                for job_id, outcome in result['results'].items():
                    logger.info(f"  Job #{job_id}: {outcome['outcome']}")
        except Exception:
            logger.exception("Error in run_scheduled_jobs")

        # Sleep in small increments so we can respond to shutdown quickly
        for _ in range(poll_seconds):
            if _shutdown or sniper._shutdown:
                break
            time.sleep(1)

    logger.info("Sniper worker stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _clear_cookies_for_proxy()
    _reset_stale_active_jobs()

    poll_seconds = get_poll_interval()

    with ReservationSniper() as sniper:
        # Re-register signal handlers AFTER ReservationSniper.__init__
        # (which installs its own), so both the worker loop and sniper
        # respond to SIGTERM/SIGINT.
        def _combined_handler(signum, frame):
            _handle_signal(signum, frame)
            sniper._shutdown = True

        signal.signal(signal.SIGTERM, _combined_handler)
        signal.signal(signal.SIGINT, _combined_handler)

        run_loop(sniper, poll_seconds)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Reservation Sniper CLI

Usage:
  # Create + run immediately (blocks until done):
  python3 scripts/run_sniper.py fish-cheeks 2026-03-01 "7:00 PM"

  # Schedule for later (saves job, exits):
  python3 scripts/run_sniper.py fish-cheeks 2026-03-01 "7:00 PM" --at "2026-02-22 09:00"

  # Cron mode (process all due jobs):
  python3 scripts/run_sniper.py --cron

  # List all jobs:
  python3 scripts/run_sniper.py --list

  # Cancel a job:
  python3 scripts/run_sniper.py --cancel 1

Cron setup (runs every minute, picks up due jobs):
  * * * * * cd /path/to/ai-agents && python3 scripts/run_sniper.py --cron >> logs/sniper.log 2>&1
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.reservation_sniper import ReservationSniper
from utils.reservation_store import ReservationStore


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_create_and_run(args):
    """Create a sniper job and optionally run it immediately."""
    sniper = ReservationSniper()

    preferred_times = args.times if args.times else []

    job_id = sniper.create_job(
        venue_slug=args.venue_slug,
        date=args.date,
        preferred_times=preferred_times,
        party_size=args.party_size,
        time_window_minutes=args.window,
        max_attempts=args.max_attempts,
        scheduled_at=args.at,
        auto_resolve_conflicts=True,
    )

    if args.at:
        print(f"Sniper job #{job_id} scheduled. Will fire at {args.at}")
        print(f"Set up cron to run: python3 scripts/run_sniper.py --cron")
    else:
        print(f"Sniper job #{job_id} created. Running now...")
        result = sniper.run_job(job_id)
        print(f"Result: {result['outcome']}")
        if result['outcome'] == 'booked':
            print(f"  Time: {result.get('time')}")
            print(f"  Reservation ID: {result.get('reservation_id')}")
        elif result['outcome'] == 'failed':
            print(f"  Reason: {result.get('reason')}")


def cmd_cron(args):
    """Process all due scheduled jobs."""
    sniper = ReservationSniper()
    result = sniper.run_scheduled_jobs()

    if result['jobs_run'] == 0:
        logging.getLogger(__name__).debug("No jobs to run")
    else:
        print(f"Ran {result['jobs_run']} job(s)")
        for job_id, outcome in result['results'].items():
            print(f"  Job #{job_id}: {outcome['outcome']}")


def cmd_list(args):
    """List all sniper jobs."""
    store = ReservationStore()
    jobs = store.get_all_sniper_jobs()
    store.close()

    if not jobs:
        print("No sniper jobs found.")
        return

    print(f"{'ID':>4}  {'Status':<10}  {'Venue':<20}  {'Date':<12}  {'Times':<20}  {'Scheduled At':<20}  {'Polls'}")
    print("-" * 100)
    for job in jobs:
        times = ", ".join(job['preferred_times']) if job['preferred_times'] else "(any)"
        print(
            f"{job['id']:>4}  {job['status']:<10}  {job['venue_slug']:<20}  "
            f"{job['date']:<12}  {times:<20}  {job['scheduled_at']:<20}  "
            f"{job['poll_count']}/{job['max_attempts']}"
        )


def cmd_cancel(args):
    """Cancel a sniper job."""
    store = ReservationStore()
    job = store.get_sniper_job(args.cancel)

    if not job:
        print(f"Job #{args.cancel} not found.")
        store.close()
        return

    if job['status'] in ('completed', 'failed'):
        print(f"Job #{args.cancel} is already {job['status']}.")
        store.close()
        return

    store.update_sniper_job(args.cancel, {'status': 'cancelled'})
    store.close()
    print(f"Job #{args.cancel} cancelled.")


def main():
    parser = argparse.ArgumentParser(
        description="Reservation Sniper — auto-book tables at drop time",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mode flags (mutually exclusive with positional args)
    parser.add_argument("--cron", action="store_true", help="Process all due scheduled jobs")
    parser.add_argument("--list", action="store_true", help="List all sniper jobs")
    parser.add_argument("--cancel", type=int, metavar="JOB_ID", help="Cancel a sniper job")

    # Positional args for creating a job
    parser.add_argument("venue_slug", nargs="?", help="Restaurant slug (e.g., fish-cheeks)")
    parser.add_argument("date", nargs="?", help="Reservation date (YYYY-MM-DD)")
    parser.add_argument("times", nargs="*", help="Preferred times (e.g., '7:00 PM' '7:30 PM')")

    # Optional args for job creation
    parser.add_argument("--party-size", type=int, default=2, help="Number of guests (default: 2)")
    parser.add_argument("--at", type=str, help="Schedule datetime (ISO or 'YYYY-MM-DD HH:MM')")
    parser.add_argument("--window", type=int, default=60, help="Time window in minutes (default: 60)")
    parser.add_argument("--max-attempts", type=int, default=60, help="Max poll attempts (default: 60)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.cron:
        cmd_cron(args)
    elif args.list:
        cmd_list(args)
    elif args.cancel:
        cmd_cancel(args)
    elif args.venue_slug and args.date:
        cmd_create_and_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

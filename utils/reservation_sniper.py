"""Reservation Sniper — automated slot grabbing at drop time.

No LLM involved. Rapid-polls for availability and books the first
matching slot, auto-resolving conflicts if configured.
"""

import logging
import signal
import time
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from config.settings import Settings
from utils.availability_filter import pick_best_slot
from utils.reservation_store import ReservationStore
from utils.notification import SniperNotifier
from utils.slug_utils import make_config_id, parse_config_id

logger = logging.getLogger(__name__)


class ReservationSniper:
    """Automated reservation sniper — polls for availability and books."""

    def __init__(self, client=None, store=None, notifier=None):
        """Initialize sniper with optional dependency injection.

        Args:
            client: Resy client (API or browser). Defaults to factory.
            store: ReservationStore instance. Defaults to new store.
            notifier: SniperNotifier instance. Defaults to new notifier.
        """
        self._client = client
        self._store = store or ReservationStore()
        self._notifier = notifier or SniperNotifier()
        self._shutdown = False

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    @property
    def client(self):
        """Lazy-load the Resy client."""
        if self._client is None:
            from utils.resy_client_factory import ResyClientFactory
            self._client = ResyClientFactory.create_client()
        return self._client

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        logger.info("Shutdown signal received, finishing current poll...")
        self._shutdown = True

    def close(self):
        """Clean up browser client and database connection."""
        if self._client is not None and hasattr(self._client, '_cleanup'):
            self._client._cleanup()
        self._store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_job(
        self,
        venue_slug: str,
        date: str,
        preferred_times: List[str],
        party_size: int = 2,
        time_window_minutes: int = None,
        max_attempts: int = None,
        scheduled_at: str = None,
        auto_resolve_conflicts: bool = True,
        notes: str = None,
    ) -> int:
        """Create and persist a sniper job.

        Args:
            venue_slug: Restaurant slug (e.g., "fish-cheeks")
            date: Reservation date YYYY-MM-DD
            preferred_times: List of preferred time strings (e.g., ["7:00 PM"])
            party_size: Number of guests
            time_window_minutes: Accept slots within this many minutes of preferred
            max_attempts: Maximum poll attempts before giving up
            scheduled_at: ISO datetime when to start sniping (e.g., "2026-02-22T09:00:00")
            auto_resolve_conflicts: Cancel conflicting reservations automatically
            notes: Optional notes

        Returns:
            Job ID
        """
        if time_window_minutes is None:
            time_window_minutes = Settings.SNIPER_DEFAULT_TIME_WINDOW_MINUTES
        if max_attempts is None:
            max_attempts = Settings.SNIPER_MAX_ATTEMPTS
        if scheduled_at is None:
            scheduled_at = datetime.now().isoformat()

        try:
            datetime.fromisoformat(scheduled_at)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid scheduled_at datetime: {scheduled_at!r}")

        job_id = self._store.add_sniper_job({
            'venue_slug': venue_slug,
            'date': date,
            'preferred_times': preferred_times,
            'party_size': party_size,
            'time_window_minutes': time_window_minutes,
            'max_attempts': max_attempts,
            'scheduled_at': scheduled_at,
            'auto_resolve_conflicts': auto_resolve_conflicts,
            'notes': notes,
        })

        logger.info("Sniper job #%d created: %s on %s at %s (fires at %s)",
                     job_id, venue_slug, date, preferred_times, scheduled_at)
        return job_id

    def run_job(self, job_id: int) -> Dict:
        """Execute a sniper job: rapid-poll until booked or exhausted.

        Args:
            job_id: Sniper job ID

        Returns:
            Dict with outcome ('booked', 'failed', 'shutdown') and details
        """
        job = self._store.get_sniper_job(job_id)
        if not job:
            return {'outcome': 'failed', 'reason': f'Job {job_id} not found'}

        self._store.update_sniper_job(job_id, {'status': 'active'})
        logger.info("Starting sniper job #%d: %s on %s", job_id, job['venue_slug'], job['date'])

        poll_interval = Settings.SNIPER_POLL_INTERVAL_SECONDS
        event_only_count = 0  # Track polls where only event card slots were found
        error_counts = Counter()  # Track poll error frequencies

        while not self._shutdown:
            # Refresh job to get current poll_count
            job = self._store.get_sniper_job(job_id)
            if job['poll_count'] >= job['max_attempts']:
                reason = f"Max attempts ({job['max_attempts']}) reached"
                if error_counts:
                    reason += "\n\n## Poll Errors"
                    for error, count in error_counts.most_common():
                        reason += f"\n- {error} ({count}x)"
                if event_only_count > 0:
                    reason += (
                        f"\n\nNote: {event_only_count} poll(s) found only event-style listings "
                        f"(DayOfEventCard UI) instead of standard time slots. "
                        f"This venue may only have special event bookings for this date."
                    )
                self._store.update_sniper_job(job_id, {'status': 'failed'})
                self._notifier.notify_failure(job, reason)
                logger.warning("Sniper job #%d failed: %s", job_id, reason)
                return {'outcome': 'failed', 'reason': reason, 'poll_count': job['poll_count']}

            self._store.increment_poll_count(job_id)
            result = self._poll_once(job)

            if result.get('booked'):
                # Save reservation to DB
                res_id = self._store.add_reservation({
                    'platform': 'resy',
                    'restaurant_name': job['venue_slug'],
                    'date': job['date'],
                    'time': result.get('time', ''),
                    'party_size': job['party_size'],
                    'confirmation_number': result.get('reservation_id'),
                    'status': 'confirmed',
                })

                self._store.update_sniper_job(job_id, {
                    'status': 'completed',
                    'reservation_id': res_id,
                })

                # Cancel other jobs for the same venue/date to avoid duplicate bookings
                cancelled = self._store.cancel_sibling_sniper_jobs(
                    job_id, job['venue_slug'], job['date']
                )
                if cancelled:
                    logger.info("Cancelled %d sibling job(s) for %s on %s", cancelled, job['venue_slug'], job['date'])

                # Refresh job for notification
                job = self._store.get_sniper_job(job_id)
                self._notifier.notify_success(job, result)
                logger.info("Sniper job #%d booked: %s at %s", job_id, job['venue_slug'], result.get('time'))
                return {
                    'outcome': 'booked',
                    'time': result.get('time'),
                    'reservation_id': result.get('reservation_id'),
                    'poll_count': job['poll_count'],
                }

            # Not booked yet — wait and retry
            if result.get('event_only'):
                event_only_count += 1
            if result.get('error'):
                error_counts[result['error']] += 1
                logger.warning("Poll error on job #%d: %s", job_id, result['error'])

            time.sleep(poll_interval)

        # Shutdown signal received
        self._store.update_sniper_job(job_id, {'status': 'pending'})
        logger.info("Sniper job #%d paused due to shutdown", job_id)
        return {'outcome': 'shutdown', 'poll_count': job['poll_count']}

    def _poll_once(self, job: Dict) -> Dict:
        """Single poll attempt: check availability and try to book.

        Args:
            job: Sniper job dict

        Returns:
            Dict with booked (bool), time, reservation_id, error
        """
        try:
            slots = self.client.get_availability(
                venue_id=job['venue_slug'],
                date=job['date'],
                party_size=job['party_size'],
            )
        except Exception as e:  # Broad catch: sniper retries on any transient error
            return {'booked': False, 'error': f'Availability check failed: {e}'}

        if not slots:
            return {'booked': False, 'error': 'No slots available'}

        event_only = all(s.get('type') == 'event' for s in slots)

        best = pick_best_slot(
            slots,
            job['preferred_times'],
            window_minutes=job['time_window_minutes'],
        )

        if not best:
            return {'booked': False, 'error': 'No matching slots in time window', 'event_only': event_only}

        # Attempt booking
        config_id = best.get('config_id')
        if not config_id:
            config_id = make_config_id(job['venue_slug'], job['date'], best['time'])

        try:
            result = self.client.make_reservation(
                config_id=config_id,
                date=job['date'],
                party_size=job['party_size'],
            )
        except Exception as e:  # Broad catch: sniper retries on any transient error
            return {'booked': False, 'error': f'Booking failed: {e}'}

        if result.get('success'):
            return {
                'booked': True,
                'time': best.get('time', ''),
                'time_slot': best.get('time', ''),
                'reservation_id': result.get('reservation_id'),
            }

        # Handle conflict
        if result.get('status') == 'conflict' and job.get('auto_resolve_conflicts'):
            return self._resolve_conflict(job, config_id, best)

        return {'booked': False, 'error': result.get('error', 'Booking unsuccessful')}

    def _resolve_conflict(self, job: Dict, config_id: str, slot: Dict) -> Dict:
        """Auto-resolve a reservation conflict by cancelling existing and rebooking.

        Args:
            job: Sniper job dict
            config_id: Config ID that caused the conflict
            slot: The slot dict being booked

        Returns:
            Dict with booked (bool), time, reservation_id, error
        """
        try:
            parsed = parse_config_id(config_id)
            venue_slug = parsed['venue_slug']
            time_text = parsed['time_text']
        except ValueError:
            venue_slug = job['venue_slug']
            time_text = slot.get('time', '')

        try:
            result = self.client.resolve_reservation_conflict(
                choice='continue_booking',
                config_id=config_id,
                date=job['date'],
                party_size=job['party_size'],
                venue_slug=venue_slug,
                time_text=time_text,
            )
        except Exception as e:  # Broad catch: sniper retries on any transient error
            return {'booked': False, 'error': f'Conflict resolution failed: {e}'}

        if result.get('success'):
            return {
                'booked': True,
                'time': slot.get('time', ''),
                'time_slot': slot.get('time', ''),
                'reservation_id': result.get('reservation_id'),
            }

        return {'booked': False, 'error': result.get('error', 'Conflict resolution failed')}

    def run_scheduled_jobs(self) -> Dict:
        """Run all pending sniper jobs whose scheduled_at has passed.

        Uses atomic claim to prevent two concurrent cron processes from
        picking up the same job.  Intended to be called by cron every minute.

        Returns:
            Dict with results per job ID
        """
        results = {}
        while not self._shutdown:
            job = self._store.claim_next_sniper_job()
            if not job:
                break
            logger.info("Running scheduled sniper job #%d", job['id'])
            results[job['id']] = self.run_job(job['id'])

        if not results:
            logger.debug("No pending sniper jobs to run")

        return {'jobs_run': len(results), 'results': results}

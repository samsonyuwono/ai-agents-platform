"""Sniper notification system for reservation booking events."""

import logging
from typing import Dict, Optional
from config.settings import Settings

logger = logging.getLogger(__name__)


class SniperNotifier:
    """Email notifications for sniper job outcomes."""

    def __init__(self, email_sender=None):
        """Initialize notifier.

        Args:
            email_sender: Optional EmailSender instance (for testing).
                          If None, creates one if email is configured.
        """
        self._sender = email_sender
        if self._sender is None and Settings.has_email_configured():
            from utils.email_sender import EmailSender
            self._sender = EmailSender()

        self._to_email = Settings.EMAIL_TO

    @property
    def is_configured(self) -> bool:
        """Check if notifications can be sent."""
        return self._sender is not None and bool(self._to_email)

    def notify_success(self, job: Dict, reservation: Dict) -> bool:
        """Send success notification for a completed sniper job.

        Args:
            job: Sniper job dict (venue_slug, date, preferred_times, etc.)
            reservation: Reservation result dict (time_slot, reservation_id, etc.)

        Returns:
            True if email sent, False otherwise
        """
        if not self.is_configured:
            logger.info("Email not configured, skipping success notification")
            return False

        subject = f"Reservation Booked: {job['venue_slug']} on {job['date']}"
        body = _format_success(job, reservation)

        return self._sender.send(self._to_email, subject, body)

    def notify_failure(self, job: Dict, reason: str) -> bool:
        """Send failure notification for a sniper job.

        Args:
            job: Sniper job dict
            reason: Human-readable failure reason

        Returns:
            True if email sent, False otherwise
        """
        if not self.is_configured:
            logger.info("Email not configured, skipping failure notification")
            return False

        subject = f"Sniper Failed: {job['venue_slug']} on {job['date']}"
        body = _format_failure(job, reason)

        return self._sender.send(self._to_email, subject, body)


def _format_success(job: Dict, reservation: Dict) -> str:
    """Format a success notification body in markdown."""
    time_slot = reservation.get('time_slot', 'N/A')
    res_id = reservation.get('reservation_id', 'N/A')
    preferred = ", ".join(job.get('preferred_times', []))

    return f"""# Reservation Sniped Successfully!

## Booking Details

- **Restaurant:** {job['venue_slug']}
- **Date:** {job['date']}
- **Time:** {time_slot}
- **Party Size:** {job.get('party_size', 2)}
- **Confirmation:** {res_id}

## Sniper Stats

- **Preferred Times:** {preferred}
- **Attempts Used:** {job.get('poll_count', 0)} / {job.get('max_attempts', 60)}

---
*Booked automatically by Reservation Sniper*
"""


def _format_failure(job: Dict, reason: str) -> str:
    """Format a failure notification body in markdown."""
    preferred = ", ".join(job.get('preferred_times', []))

    return f"""# Sniper Job Failed

## Details

- **Restaurant:** {job['venue_slug']}
- **Date:** {job['date']}
- **Preferred Times:** {preferred}
- **Party Size:** {job.get('party_size', 2)}

## Failure Reason

{reason}

## Stats

- **Attempts Made:** {job.get('poll_count', 0)} / {job.get('max_attempts', 60)}

---
*Reservation Sniper*
"""

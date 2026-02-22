"""
Reservation Database Storage
SQLite database for tracking restaurant reservations.
"""

import json
import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
from config.settings import Settings

_EST = ZoneInfo("America/New_York")


def _now_est() -> str:
    """Return current EST/EDT time as naive ISO string."""
    return datetime.now(_EST).replace(tzinfo=None).isoformat()


class ReservationStore:
    """SQLite database for tracking reservations."""

    def __init__(self, db_path=None):
        """Initialize database connection."""
        self.db_path = db_path or Settings.RESERVATION_DB_PATH

        # Create data directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        self._initialize_tables()

    def _initialize_tables(self):
        """Create tables if they don't exist."""
        cursor = self.conn.cursor()

        # Reservations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                venue_id TEXT,
                restaurant_name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                confirmation_number TEXT,
                confirmation_token TEXT,
                status TEXT DEFAULT 'confirmed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT
            )
        ''')

        # Sniper jobs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sniper_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_slug TEXT NOT NULL,
                date TEXT NOT NULL,
                preferred_times TEXT NOT NULL,
                party_size INTEGER NOT NULL DEFAULT 2,
                time_window_minutes INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'pending',
                poll_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 60,
                scheduled_at TEXT NOT NULL,
                auto_resolve_conflicts INTEGER NOT NULL DEFAULT 1,
                reservation_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        ''')

        self.conn.commit()

    def add_reservation(self, data: Dict) -> int:
        """
        Add a new reservation to the database.

        Args:
            data: Dictionary with reservation details
                  Required: platform, restaurant_name, date, time, party_size
                  Optional: venue_id, confirmation_number, confirmation_token, notes

        Returns:
            int: The ID of the newly created reservation
        """
        cursor = self.conn.cursor()
        now = _now_est()

        cursor.execute('''
            INSERT INTO reservations (
                platform, venue_id, restaurant_name, date, time,
                party_size, confirmation_number, confirmation_token,
                status, created_at, updated_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('platform'),
            data.get('venue_id'),
            data.get('restaurant_name'),
            data.get('date'),
            data.get('time'),
            data.get('party_size'),
            data.get('confirmation_number'),
            data.get('confirmation_token'),
            data.get('status', 'confirmed'),
            now,
            now,
            data.get('notes')
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_reservations(self, filters: Optional[Dict] = None) -> List[Dict]:
        """
        Get reservations with optional filtering.

        Args:
            filters: Optional dictionary with filter criteria
                     Supported: platform, status, date_from, date_to

        Returns:
            List of reservation dictionaries
        """
        cursor = self.conn.cursor()
        query = "SELECT * FROM reservations WHERE 1=1"
        params = []

        if filters:
            if 'platform' in filters:
                query += " AND platform = ?"
                params.append(filters['platform'])

            if 'status' in filters:
                query += " AND status = ?"
                params.append(filters['status'])

            if 'date_from' in filters:
                query += " AND date >= ?"
                params.append(filters['date_from'])

            if 'date_to' in filters:
                query += " AND date <= ?"
                params.append(filters['date_to'])

        query += " ORDER BY date DESC, time DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert to list of dictionaries
        return [dict(row) for row in rows]

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Dict]:
        """Get a single reservation by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()

        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str, notes: Optional[str] = None) -> bool:
        """
        Update the status of a reservation.

        Args:
            reservation_id: ID of the reservation
            status: New status (confirmed, cancelled, completed, no_show)
            notes: Optional notes about the status change

        Returns:
            bool: True if updated successfully, False otherwise
        """
        cursor = self.conn.cursor()
        now = _now_est()

        if notes:
            cursor.execute('''
                UPDATE reservations
                SET status = ?, notes = ?, updated_at = ?
                WHERE id = ?
            ''', (status, notes, now, reservation_id))
        else:
            cursor.execute('''
                UPDATE reservations
                SET status = ?, updated_at = ?
                WHERE id = ?
            ''', (status, now, reservation_id))

        self.conn.commit()
        return cursor.rowcount > 0

    def delete_reservation(self, reservation_id: int) -> bool:
        """
        Delete a reservation from the database.

        Args:
            reservation_id: ID of the reservation to delete

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
        self.conn.commit()

        return cursor.rowcount > 0

    def get_upcoming_reservations(self, days: int = 30) -> List[Dict]:
        """Get all confirmed reservations in the next N days."""
        from datetime import date, timedelta

        today = date.today().isoformat()
        future_date = (date.today() + timedelta(days=days)).isoformat()

        return self.get_reservations({
            'status': 'confirmed',
            'date_from': today,
            'date_to': future_date
        })

    # --- Sniper Jobs ---

    def _deserialize_sniper_job(self, row) -> Dict:
        """Convert a sniper_jobs row to a dict with JSON/bool deserialization."""
        d = dict(row)
        d['preferred_times'] = json.loads(d['preferred_times'])
        d['auto_resolve_conflicts'] = bool(d['auto_resolve_conflicts'])
        return d

    def add_sniper_job(self, data: Dict) -> int:
        """Add a new sniper job.

        Args:
            data: Dict with venue_slug, date, preferred_times (list of str),
                  party_size, time_window_minutes, max_attempts, scheduled_at,
                  auto_resolve_conflicts (bool), notes

        Returns:
            ID of the created job
        """
        cursor = self.conn.cursor()
        now = _now_est()

        preferred_times = data.get('preferred_times', [])
        if isinstance(preferred_times, list):
            preferred_times = json.dumps(preferred_times)

        cursor.execute('''
            INSERT INTO sniper_jobs (
                venue_slug, date, preferred_times, party_size,
                time_window_minutes, status, poll_count, max_attempts,
                scheduled_at, auto_resolve_conflicts, created_at, updated_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['venue_slug'],
            data['date'],
            preferred_times,
            data.get('party_size', Settings.DEFAULT_PARTY_SIZE),
            data.get('time_window_minutes', Settings.SNIPER_DEFAULT_TIME_WINDOW_MINUTES),
            'pending',
            0,
            data.get('max_attempts', Settings.SNIPER_MAX_ATTEMPTS),
            data['scheduled_at'],
            1 if data.get('auto_resolve_conflicts', True) else 0,
            now,
            now,
            data.get('notes'),
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_sniper_job(self, job_id: int) -> Optional[Dict]:
        """Get a sniper job by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sniper_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._deserialize_sniper_job(row)

    def get_pending_sniper_jobs(self) -> List[Dict]:
        """Get sniper jobs whose scheduled_at has passed and status is pending."""
        cursor = self.conn.cursor()
        now = _now_est()
        cursor.execute(
            "SELECT * FROM sniper_jobs WHERE status = 'pending' AND scheduled_at <= ? ORDER BY scheduled_at",
            (now,)
        )
        rows = cursor.fetchall()
        return [self._deserialize_sniper_job(row) for row in rows]

    def get_all_sniper_jobs(self) -> List[Dict]:
        """Get all sniper jobs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sniper_jobs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [self._deserialize_sniper_job(row) for row in rows]

    def claim_next_sniper_job(self) -> Optional[Dict]:
        """Atomically claim the next due pending sniper job.

        Uses SELECT then UPDATE WHERE status='pending' to prevent two
        concurrent cron processes from claiming the same job.

        Returns:
            Claimed job dict, or None if no due jobs
        """
        cursor = self.conn.cursor()
        now = _now_est()
        cursor.execute(
            "SELECT id FROM sniper_jobs WHERE status = 'pending' AND scheduled_at <= ? "
            "ORDER BY scheduled_at LIMIT 1", (now,))
        row = cursor.fetchone()
        if not row:
            return None
        job_id = row['id']
        cursor.execute(
            "UPDATE sniper_jobs SET status = 'active', updated_at = ? "
            "WHERE id = ? AND status = 'pending'", (now, job_id))
        self.conn.commit()
        if cursor.rowcount == 0:
            return None  # Another process claimed it
        return self.get_sniper_job(job_id)

    def update_sniper_job(self, job_id: int, updates: Dict) -> bool:
        """Update fields on a sniper job.

        Args:
            job_id: Job ID
            updates: Dict of field -> value to update

        Returns:
            True if a row was updated
        """
        if not updates:
            return False

        now = _now_est()
        updates['updated_at'] = now

        # Serialize preferred_times if present
        if 'preferred_times' in updates and isinstance(updates['preferred_times'], list):
            updates['preferred_times'] = json.dumps(updates['preferred_times'])
        if 'auto_resolve_conflicts' in updates and isinstance(updates['auto_resolve_conflicts'], bool):
            updates['auto_resolve_conflicts'] = 1 if updates['auto_resolve_conflicts'] else 0

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [job_id]

        cursor = self.conn.cursor()
        cursor.execute(f"UPDATE sniper_jobs SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        return cursor.rowcount > 0

    def increment_poll_count(self, job_id: int) -> bool:
        """Increment the poll_count for a sniper job."""
        cursor = self.conn.cursor()
        now = _now_est()
        cursor.execute(
            "UPDATE sniper_jobs SET poll_count = poll_count + 1, updated_at = ? WHERE id = ?",
            (now, job_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

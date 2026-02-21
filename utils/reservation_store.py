"""
Reservation Database Storage
SQLite database for tracking restaurant reservations.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
from config.settings import Settings


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
        now = datetime.now().isoformat()

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
        now = datetime.now().isoformat()

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

"""
Encrypted Credential Storage
SQLite database for storing per-user Resy credentials with Fernet encryption.
"""

import base64
import os
import sqlite3
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config.settings import Settings

_EST = ZoneInfo("America/New_York")


def _now_est() -> str:
    """Return current EST/EDT time as naive ISO string."""
    return datetime.now(_EST).replace(tzinfo=None).isoformat()


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a Fernet key from the JWT secret using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"resy-credential-store",
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


class CredentialStore:
    """SQLite database for storing encrypted Resy credentials."""

    def __init__(self, db_path: Optional[str] = None, secret: Optional[str] = None):
        """Initialize database connection and encryption.

        Args:
            db_path: Path to SQLite database (defaults to Settings.RESERVATION_DB_PATH)
            secret: Secret for key derivation (defaults to Settings.WEB_JWT_SECRET)
        """
        self.db_path = db_path or Settings.RESERVATION_DB_PATH
        secret = secret or Settings.WEB_JWT_SECRET

        # Create data directory if it doesn't exist
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self._fernet = Fernet(_derive_fernet_key(secret))
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_tables()

    def _initialize_tables(self):
        """Create tables if they don't exist."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_credentials (
                resy_email TEXT PRIMARY KEY,
                encrypted_password BLOB NOT NULL,
                resy_auth_token TEXT,
                token_refreshed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        self.conn.commit()

    def save_credentials(self, resy_email: str, password: str, auth_token: Optional[str] = None) -> None:
        """Save or update encrypted credentials for a user.

        Args:
            resy_email: Resy account email (primary key)
            password: Resy account password (encrypted at rest)
            auth_token: Optional cached auth token
        """
        encrypted = self._fernet.encrypt(password.encode())
        now = _now_est()
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO user_credentials (resy_email, encrypted_password, resy_auth_token, token_refreshed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(resy_email) DO UPDATE SET
                encrypted_password = excluded.encrypted_password,
                resy_auth_token = excluded.resy_auth_token,
                token_refreshed_at = excluded.token_refreshed_at,
                updated_at = excluded.updated_at
        ''', (resy_email, encrypted, auth_token, now if auth_token else None, now, now))
        self.conn.commit()

    def get_credentials(self, resy_email: str) -> Optional[Dict]:
        """Get decrypted credentials for a user.

        Args:
            resy_email: Resy account email

        Returns:
            Dict with resy_email, password, resy_auth_token, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM user_credentials WHERE resy_email = ?", (resy_email,))
        row = cursor.fetchone()
        if not row:
            return None

        decrypted_password = self._fernet.decrypt(row["encrypted_password"]).decode()
        return {
            "resy_email": row["resy_email"],
            "password": decrypted_password,
            "resy_auth_token": row["resy_auth_token"],
            "token_refreshed_at": row["token_refreshed_at"],
        }

    def update_auth_token(self, resy_email: str, auth_token: str) -> bool:
        """Update the cached auth token for a user.

        Args:
            resy_email: Resy account email
            auth_token: New auth token

        Returns:
            True if updated, False if user not found
        """
        now = _now_est()
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE user_credentials
            SET resy_auth_token = ?, token_refreshed_at = ?, updated_at = ?
            WHERE resy_email = ?
        ''', (auth_token, now, now, resy_email))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_credentials(self, resy_email: str) -> bool:
        """Delete credentials for a user.

        Args:
            resy_email: Resy account email

        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM user_credentials WHERE resy_email = ?", (resy_email,))
        self.conn.commit()
        return cursor.rowcount > 0

    def has_credentials(self, resy_email: str) -> bool:
        """Check if credentials exist for a user.

        Args:
            resy_email: Resy account email

        Returns:
            True if credentials exist
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM user_credentials WHERE resy_email = ?", (resy_email,))
        return cursor.fetchone() is not None

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

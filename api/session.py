"""Agent session management — one ReservationAgent per session."""

import logging
import threading
import uuid
from typing import Dict, List, Optional

from agents.reservation_agent import ReservationAgent
from config.settings import Settings

logger = logging.getLogger(__name__)


def _create_client_for_user(email: str, password: str, auth_token: Optional[str] = None):
    """Create a Resy client with the user's credentials.

    Respects RESY_CLIENT_MODE but passes the user's credentials
    directly to the client constructor.

    Returns:
        ResyClient or ResyBrowserClient instance
    """
    mode = Settings.RESY_CLIENT_MODE

    if mode == 'browser' or (mode == 'auto' and Settings.has_resy_browser_configured()):
        from utils.resy_browser_client import ResyBrowserClient
        return ResyBrowserClient(email=email, password=password)

    # API mode
    from utils.resy_client import ResyClient
    api_key = Settings.RESY_API_KEY or Settings.RESY_PUBLIC_API_KEY
    client = ResyClient(api_key=api_key, auth_token=auth_token)
    client._user_email = email
    client._user_password = password
    return client


def _create_agent_for_user(resy_email: str) -> ReservationAgent:
    """Create a ReservationAgent with per-user Resy credentials.

    Args:
        resy_email: User's Resy email to look up credentials

    Returns:
        ReservationAgent with a user-specific client
    """
    from utils.credential_store import CredentialStore

    with CredentialStore() as store:
        creds = store.get_credentials(resy_email)

    if not creds:
        raise ValueError(f"No credentials found for {resy_email}")

    # Pass credentials for deferred client creation in the daemon thread.
    # This avoids Playwright threading issues since the browser client will
    # be created fresh in each run() call's thread.
    return ReservationAgent(resy_credentials={
        "email": resy_email,
        "password": creds["password"],
        "auth_token": creds.get("resy_auth_token"),
    })


class SessionManager:
    """Manages ReservationAgent instances keyed by session ID."""

    def __init__(self):
        self._sessions: Dict[str, ReservationAgent] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: Optional[str] = None, resy_email: Optional[str] = None) -> tuple:
        """Return (session_id, agent). Creates a new session if needed.

        Args:
            session_id: Existing session ID to resume, or None for new session
            resy_email: User's Resy email for per-user client creation

        Returns:
            Tuple of (session_id, ReservationAgent)
        """
        with self._lock:
            if session_id and session_id in self._sessions:
                return session_id, self._sessions[session_id]

            new_id = session_id or str(uuid.uuid4())
            logger.info("Creating new agent session: %s", new_id)

            if resy_email:
                agent = _create_agent_for_user(resy_email)
            else:
                agent = ReservationAgent()

            self._sessions[new_id] = agent
            return new_id, agent

    def get_history(self, session_id: str) -> List[dict]:
        """Return conversation history for a session."""
        with self._lock:
            agent = self._sessions.get(session_id)
            if not agent:
                return []
            return list(agent.conversation_history)

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Deleted session: %s", session_id)
                return True
            return False


# Global singleton
session_manager = SessionManager()

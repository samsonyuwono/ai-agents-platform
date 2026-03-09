"""Agent session management — one ReservationAgent per session."""

import logging
import threading
import uuid
from typing import Dict, List, Optional

from agents.reservation_agent import ReservationAgent

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages ReservationAgent instances keyed by session ID."""

    def __init__(self):
        self._sessions: Dict[str, ReservationAgent] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: Optional[str] = None) -> tuple:
        """Return (session_id, agent). Creates a new session if needed.

        Returns:
            Tuple of (session_id, ReservationAgent)
        """
        with self._lock:
            if session_id and session_id in self._sessions:
                return session_id, self._sessions[session_id]

            new_id = session_id or str(uuid.uuid4())
            logger.info("Creating new agent session: %s", new_id)
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

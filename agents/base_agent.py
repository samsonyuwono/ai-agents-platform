"""
Base Agent Class
Foundation for all AI agents with common functionality.
"""

import logging

import anthropic
from config.settings import Settings

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all AI agents."""

    def __init__(self, api_key=None, model=None):
        """
        Initialize the base agent.

        Args:
            api_key: Anthropic API key (optional, uses Settings if not provided)
            model: Claude model to use (optional, uses Settings default if not provided)
        """
        self.api_key = api_key or Settings.ANTHROPIC_API_KEY
        self.model = model or Settings.DEFAULT_MODEL

        if not self.api_key:
            raise ValueError("Anthropic API key not configured")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.conversation_history = []

    def add_to_history(self, role, content):
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content
        })

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def call_claude(self, messages, tools=None, max_tokens=None, system=None):
        """
        Call Claude API with messages.

        Args:
            messages: List of messages or single message string
            tools: Optional list of tool definitions
            max_tokens: Optional max tokens (uses Settings default if not provided)
            system: Optional system prompt

        Returns:
            API response object

        Raises:
            anthropic.APIConnectionError: If connection to API fails
            anthropic.APIStatusError: If API returns an error status
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        params = {
            "model": self.model,
            "max_tokens": max_tokens or Settings.MAX_TOKENS,
            "messages": messages
        }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        try:
            return self.client.messages.create(**params)
        except anthropic.APIConnectionError as e:
            logger.error("Failed to connect to Anthropic API: %s", e)
            raise
        except anthropic.APIStatusError as e:
            logger.error("Anthropic API error (status %d): %s", e.status_code, e.message)
            raise

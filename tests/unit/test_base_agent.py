"""Unit tests for BaseAgent."""

import pytest
from unittest.mock import MagicMock, patch

from agents.base_agent import BaseAgent


class TestBaseAgent:
    """Test BaseAgent initialization and methods."""

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_init_with_defaults(self, mock_anthropic, mock_settings):
        """Test initialization with default settings."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'

        agent = BaseAgent()

        assert agent.api_key == 'test-key'
        assert agent.model == 'claude-sonnet-4-20250514'
        assert agent.conversation_history == []
        mock_anthropic.assert_called_once_with(api_key='test-key')

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_init_with_custom_params(self, mock_anthropic, mock_settings):
        """Test initialization with custom parameters."""
        mock_settings.ANTHROPIC_API_KEY = 'default-key'
        mock_settings.DEFAULT_MODEL = 'default-model'

        agent = BaseAgent(api_key='custom-key', model='custom-model')

        assert agent.api_key == 'custom-key'
        assert agent.model == 'custom-model'

    @patch('agents.base_agent.Settings')
    def test_init_no_api_key_raises(self, mock_settings):
        """Test that missing API key raises ValueError."""
        mock_settings.ANTHROPIC_API_KEY = None

        with pytest.raises(ValueError, match="Anthropic API key not configured"):
            BaseAgent()

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_add_to_history(self, mock_anthropic, mock_settings):
        """Test adding messages to conversation history."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'

        agent = BaseAgent()
        agent.add_to_history("user", "Hello")
        agent.add_to_history("assistant", "Hi there!")

        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0] == {"role": "user", "content": "Hello"}
        assert agent.conversation_history[1] == {"role": "assistant", "content": "Hi there!"}

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_clear_history(self, mock_anthropic, mock_settings):
        """Test clearing conversation history."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'

        agent = BaseAgent()
        agent.add_to_history("user", "Hello")
        assert len(agent.conversation_history) == 1

        agent.clear_history()
        assert agent.conversation_history == []

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_call_claude_with_string(self, mock_anthropic, mock_settings):
        """Test call_claude with a string message."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'
        mock_settings.MAX_TOKENS = 4096

        agent = BaseAgent()
        mock_response = MagicMock()
        agent.client.messages.create.return_value = mock_response

        result = agent.call_claude("Hello")

        agent.client.messages.create.assert_called_once_with(
            model='test-model',
            max_tokens=4096,
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert result == mock_response

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_call_claude_with_messages(self, mock_anthropic, mock_settings):
        """Test call_claude with a message list."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'
        mock_settings.MAX_TOKENS = 4096

        agent = BaseAgent()
        mock_response = MagicMock()
        agent.client.messages.create.return_value = mock_response

        messages = [{"role": "user", "content": "Hello"}]
        result = agent.call_claude(messages)

        agent.client.messages.create.assert_called_once_with(
            model='test-model',
            max_tokens=4096,
            messages=messages
        )

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_call_claude_with_tools_and_system(self, mock_anthropic, mock_settings):
        """Test call_claude with tools and system prompt."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'
        mock_settings.MAX_TOKENS = 4096

        agent = BaseAgent()
        mock_response = MagicMock()
        agent.client.messages.create.return_value = mock_response

        tools = [{"name": "test_tool", "description": "A test tool", "input_schema": {"type": "object", "properties": {}}}]
        system = "You are a helpful assistant."

        result = agent.call_claude("Hello", tools=tools, system=system)

        agent.client.messages.create.assert_called_once_with(
            model='test-model',
            max_tokens=4096,
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
            system=system
        )

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_call_claude_api_error_raises(self, mock_anthropic, mock_settings):
        """Test that API errors are re-raised."""
        import anthropic as anthropic_module

        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'test-model'
        mock_settings.MAX_TOKENS = 4096

        agent = BaseAgent()
        agent.client.messages.create.side_effect = anthropic_module.APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(anthropic_module.APIConnectionError):
            agent.call_claude("Hello")

"""Unit tests for ResearchAgent."""

import pytest
from unittest.mock import MagicMock, patch


class TestResearchAgent:
    """Test ResearchAgent functionality."""

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def _create_agent(self, mock_anthropic, mock_settings):
        """Helper to create a ResearchAgent with mocked dependencies."""
        mock_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
        mock_settings.MAX_TOKENS = 4096
        mock_settings.BRAVE_API_KEY = None

        from agents.research_agent import ResearchAgent
        return ResearchAgent()

    def test_init_inherits_from_base_agent(self):
        """Test that ResearchAgent inherits from BaseAgent."""
        from agents.base_agent import BaseAgent
        agent = self._create_agent()
        assert isinstance(agent, BaseAgent)

    @patch('agents.research_agent.Settings')
    def test_search_web_mock_results(self, mock_settings):
        """Test search_web returns mock results when no Brave API key."""
        mock_settings.BRAVE_API_KEY = None
        agent = self._create_agent()

        result = agent.search_web("test query")

        assert result["query"] == "test query"
        assert len(result["results"]) == 1
        assert "note" in result

    @patch('agents.research_agent.Settings')
    def test_search_web_with_brave_api(self, mock_settings):
        """Test search_web uses Brave API when key is available."""
        agent = self._create_agent()
        mock_settings.BRAVE_API_KEY = 'brave-test-key'

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "web": {
                    "results": [
                        {"title": "Result 1", "description": "Desc 1", "url": "http://example.com/1"},
                        {"title": "Result 2", "description": "Desc 2", "url": "http://example.com/2"},
                    ]
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = agent.search_web("test query")

            assert result["source"] == "Brave Search API"
            assert len(result["results"]) == 2

    def test_execute_tool_web_search(self):
        """Test execute_tool dispatches web_search correctly."""
        agent = self._create_agent()

        result = agent.execute_tool("web_search", {"query": "test"})

        assert "query" in result
        assert result["query"] == "test"

    def test_execute_tool_unknown(self):
        """Test execute_tool returns error for unknown tools."""
        agent = self._create_agent()

        result = agent.execute_tool("unknown_tool", {})

        assert "error" in result

    def test_run_end_turn(self):
        """Test run method when Claude responds with end_turn."""
        agent = self._create_agent()

        # Mock Claude response with end_turn
        mock_content = MagicMock()
        mock_content.type = "text"
        mock_content.text = "Here is my answer."

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [mock_content]

        agent.client.messages.create.return_value = mock_response

        result = agent.run("What is AI?")

        assert result == "Here is my answer."
        assert len(agent.conversation_history) == 2  # user + assistant

    def test_run_tool_use_then_end_turn(self):
        """Test run method with tool use followed by end turn."""
        agent = self._create_agent()

        # First response: tool_use
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "web_search"
        mock_tool_block.input = {"query": "test"}
        mock_tool_block.id = "tool_123"

        mock_response_1 = MagicMock()
        mock_response_1.stop_reason = "tool_use"
        mock_response_1.content = [mock_tool_block]

        # Second response: end_turn
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Based on my search, here is the answer."

        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.content = [mock_text_block]

        agent.client.messages.create.side_effect = [mock_response_1, mock_response_2]

        result = agent.run("Search for test")

        assert result == "Based on my search, here is the answer."
        assert agent.client.messages.create.call_count == 2

    def test_run_max_iterations(self):
        """Test run method hits max iterations."""
        agent = self._create_agent()

        # Always return tool_use to exhaust iterations
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "web_search"
        mock_tool_block.input = {"query": "test"}
        mock_tool_block.id = "tool_123"

        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"
        mock_response.content = [mock_tool_block]

        agent.client.messages.create.return_value = mock_response

        result = agent.run("Search forever", max_iterations=2)

        assert "maximum thinking iterations" in result
        assert agent.client.messages.create.call_count == 2

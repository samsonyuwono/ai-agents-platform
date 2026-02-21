"""Unit tests for NewsDigestAgent."""

import pytest
from unittest.mock import MagicMock, patch, mock_open


class TestNewsDigestAgent:
    """Test NewsDigestAgent functionality."""

    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    @patch('agents.news_digest_agent.Settings')
    def _create_agent(self, mock_nda_settings, mock_anthropic, mock_base_settings):
        """Helper to create a NewsDigestAgent with mocked dependencies."""
        mock_base_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_base_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
        mock_base_settings.MAX_TOKENS = 4096

        mock_nda_settings.BRAVE_API_KEY = 'brave-test-key'
        mock_nda_settings.RESEND_API_KEY = None
        mock_nda_settings.EMAIL_FROM = None
        mock_nda_settings.EMAIL_TO = None
        mock_nda_settings.NEWS_FOLDER = 'news'
        mock_nda_settings.has_search_configured.return_value = True

        from agents.news_digest_agent import NewsDigestAgent
        return NewsDigestAgent()

    def test_init_inherits_from_base_agent(self):
        """Test that NewsDigestAgent inherits from BaseAgent."""
        from agents.base_agent import BaseAgent
        agent = self._create_agent()
        assert isinstance(agent, BaseAgent)

    @patch('agents.news_digest_agent.Settings')
    @patch('agents.base_agent.Settings')
    def test_init_no_brave_key_raises(self, mock_base_settings, mock_nda_settings):
        """Test that missing Brave API key raises ValueError."""
        mock_nda_settings.has_search_configured.return_value = False

        from agents.news_digest_agent import NewsDigestAgent
        with pytest.raises(ValueError, match="BRAVE_API_KEY"):
            NewsDigestAgent()

    def test_search_news_success(self):
        """Test search_news with successful API call."""
        agent = self._create_agent()

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "web": {
                    "results": [
                        {"title": "AI News", "description": "Latest AI developments", "url": "http://example.com/ai", "age": "2h"},
                    ]
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            articles = agent.search_news("AI")

            assert len(articles) == 1
            assert articles[0]["title"] == "AI News"
            assert articles[0]["age"] == "2h"

    def test_search_news_error_returns_empty(self):
        """Test search_news returns empty list on error."""
        agent = self._create_agent()

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")

            articles = agent.search_news("AI")

            assert articles == []

    def test_generate_digest(self):
        """Test digest generation with mocked Claude."""
        agent = self._create_agent()

        mock_content = MagicMock()
        mock_content.text = "## AI News\n- Big things happening in AI"

        mock_response = MagicMock()
        mock_response.content = [mock_content]

        agent.client.messages.create.return_value = mock_response

        topics_with_articles = {
            "AI": [{"title": "AI News", "snippet": "Latest", "url": "http://example.com", "age": "1h"}]
        }

        digest = agent.generate_digest(topics_with_articles)

        assert digest is not None
        assert "AI News" in digest

    def test_generate_digest_error_returns_none(self):
        """Test digest generation returns None on error."""
        agent = self._create_agent()
        agent.client.messages.create.side_effect = Exception("API Error")

        topics_with_articles = {"AI": []}
        digest = agent.generate_digest(topics_with_articles)

        assert digest is None

    def test_markdown_to_html(self):
        """Test basic markdown to HTML conversion."""
        agent = self._create_agent()

        result = agent._markdown_to_html("## Header\n\n**bold** text\n\n[link](http://example.com)")

        assert "<h2>Header</h2>" in result
        assert "<strong>bold</strong>" in result
        assert '<a href="http://example.com">link</a>' in result

    def test_send_email_not_configured(self):
        """Test send_email skips when not configured."""
        agent = self._create_agent()
        agent.resend_key = None

        result = agent.send_email("test digest", ["AI"])

        assert result is False

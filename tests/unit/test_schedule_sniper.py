"""Unit tests for _schedule_sniper in ReservationAgent."""

import subprocess
import pytest
from unittest.mock import patch, MagicMock


def _make_agent():
    """Create a ReservationAgent with mocked dependencies."""
    with patch('agents.reservation_agent.Settings') as MockSettings, \
         patch('agents.reservation_agent.ResyClient'), \
         patch('agents.reservation_agent.ReservationStore'), \
         patch('agents.reservation_agent.EmailSender'), \
         patch('utils.resy_client_factory.ResyClientFactory'):

        MockSettings.has_resy_configured.return_value = True
        MockSettings.has_resy_browser_configured.return_value = False
        MockSettings.has_email_configured.return_value = False
        MockSettings.ANTHROPIC_API_KEY = 'test-key'
        MockSettings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
        MockSettings.MAX_TOKENS = 4096
        MockSettings.DEFAULT_PARTY_SIZE = 2
        MockSettings.SNIPER_REMOTE_HOST = None
        MockSettings.SNIPER_REMOTE_DIR = '/root/ai-agents'

        from agents.reservation_agent import ReservationAgent
        agent = ReservationAgent()
        return agent


class TestScheduleSniper:
    """Test SSH-based sniper scheduling in ReservationAgent."""

    @patch('subprocess.run')
    def test_ssh_command_escapes_special_chars(self, mock_run):
        """Verify shlex.quote is applied to prevent shell injection."""
        agent = _make_agent()

        mock_run.return_value = MagicMock(
            returncode=0, stdout='Job #1 scheduled', stderr=''
        )

        with patch.object(type(agent), '_schedule_sniper', wraps=agent._schedule_sniper):
            # Patch Settings attributes directly on the agent's closure
            with patch('agents.reservation_agent.Settings') as S:
                S.SNIPER_REMOTE_HOST = 'root@server'
                S.SNIPER_REMOTE_DIR = '/root/ai-agents'
                S.DEFAULT_PARTY_SIZE = 2

                result = agent._schedule_sniper({
                    'restaurant': "O'Brien's",
                    'date': '2026-03-01',
                    'preferred_time': "7:00 PM; rm -rf /",
                    'drop_time': '2026-02-22T09:00:00',
                })

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        remote_part = cmd[-1]  # The remote command string

        # shlex.quote wraps the dangerous value in single quotes, so the
        # semicolon is neutralized.  Verify the quoted form is present.
        assert "'7:00 PM; rm -rf /'" in remote_part
        # Restaurant name with apostrophe is normalized to a slug
        assert "obriens" in remote_part
        # Verify the command uses ssh
        assert cmd[0] == "ssh"

    @patch('subprocess.run')
    def test_ssh_success_returns_result(self, mock_run):
        """Test successful SSH command returns success result."""
        agent = _make_agent()

        mock_run.return_value = MagicMock(
            returncode=0, stdout='Sniper job #5 scheduled', stderr=''
        )

        with patch('agents.reservation_agent.Settings') as S:
            S.SNIPER_REMOTE_HOST = 'root@server'
            S.SNIPER_REMOTE_DIR = '/root/ai-agents'
            S.DEFAULT_PARTY_SIZE = 2

            result = agent._schedule_sniper({
                'restaurant': 'fish-cheeks',
                'date': '2026-03-01',
                'preferred_time': '7:00 PM',
                'drop_time': '2026-02-22T09:00:00',
            })

        assert result['success'] is True
        assert result['remote'] is True
        assert result['job_id'] is not None
        assert 'Sniper job #5' in result['message']
        # Verify local record was saved
        agent.store.add_sniper_job.assert_called_once()
        call_data = agent.store.add_sniper_job.call_args[0][0]
        assert call_data['venue_slug'] == 'fish-cheeks'
        assert call_data['notes'] == 'remote:root@server'

    @patch('subprocess.run')
    def test_ssh_failure_returns_error(self, mock_run):
        """Test SSH command failure returns error result."""
        agent = _make_agent()

        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='Permission denied'
        )

        with patch('agents.reservation_agent.Settings') as S:
            S.SNIPER_REMOTE_HOST = 'root@server'
            S.SNIPER_REMOTE_DIR = '/root/ai-agents'
            S.DEFAULT_PARTY_SIZE = 2

            result = agent._schedule_sniper({
                'restaurant': 'fish-cheeks',
                'date': '2026-03-01',
                'preferred_time': '7:00 PM',
                'drop_time': '2026-02-22T09:00:00',
            })

        assert result['success'] is False
        assert 'Permission denied' in result['error']

    @patch('subprocess.run')
    def test_ssh_timeout_returns_error(self, mock_run):
        """Test SSH timeout returns error result."""
        agent = _make_agent()

        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ssh', timeout=15)

        with patch('agents.reservation_agent.Settings') as S:
            S.SNIPER_REMOTE_HOST = 'root@server'
            S.SNIPER_REMOTE_DIR = '/root/ai-agents'
            S.DEFAULT_PARTY_SIZE = 2

            result = agent._schedule_sniper({
                'restaurant': 'fish-cheeks',
                'date': '2026-03-01',
                'preferred_time': '7:00 PM',
                'drop_time': '2026-02-22T09:00:00',
            })

        assert result['success'] is False
        assert 'timed out' in result['error']

    def test_local_fallback_when_no_remote(self):
        """Test local sniper creation when SNIPER_REMOTE_HOST is None."""
        agent = _make_agent()

        mock_sniper_instance = MagicMock()
        mock_sniper_instance.create_job.return_value = 42

        with patch('agents.reservation_agent.Settings') as S, \
             patch('utils.reservation_sniper.ReservationSniper', return_value=mock_sniper_instance):
            S.SNIPER_REMOTE_HOST = None
            S.DEFAULT_PARTY_SIZE = 2

            # The local path imports ReservationSniper inside the method
            # We need to mock it at the import site
            with patch.dict('sys.modules', {}):
                from utils.reservation_sniper import ReservationSniper as RS

            with patch('utils.reservation_sniper.ReservationSniper') as MockCls:
                MockCls.return_value = mock_sniper_instance

                result = agent._schedule_sniper({
                    'restaurant': 'fish-cheeks',
                    'date': '2026-03-01',
                    'preferred_time': '7:00 PM',
                    'drop_time': '2026-02-22T09:00:00',
                })

        assert result['success'] is True
        assert result['job_id'] == 42

    @patch('subprocess.run')
    def test_restaurant_name_converted_to_slug(self, mock_run):
        """Pass a human-readable name; verify it's converted to a slug."""
        agent = _make_agent()

        mock_run.return_value = MagicMock(
            returncode=0, stdout='Job #1 scheduled', stderr=''
        )

        with patch('agents.reservation_agent.Settings') as S:
            S.SNIPER_REMOTE_HOST = 'root@server'
            S.SNIPER_REMOTE_DIR = '/root/ai-agents'
            S.DEFAULT_PARTY_SIZE = 2

            result = agent._schedule_sniper({
                'restaurant': 'Fish Cheeks',
                'date': '2026-03-01',
                'preferred_time': '7:00 PM',
                'drop_time': '2026-02-22T09:00:00',
            })

        assert result['success'] is True
        assert result['venue_slug'] == 'fish-cheeks'
        # Verify the SSH command used the resolved slug
        remote_cmd = mock_run.call_args[0][0][-1]
        assert 'fish-cheeks' in remote_cmd

    @patch('subprocess.run')
    def test_slug_passed_through_unchanged(self, mock_run):
        """Pass an already-valid slug; verify it's used as-is."""
        agent = _make_agent()

        mock_run.return_value = MagicMock(
            returncode=0, stdout='Job #2 scheduled', stderr=''
        )

        with patch('agents.reservation_agent.Settings') as S:
            S.SNIPER_REMOTE_HOST = 'root@server'
            S.SNIPER_REMOTE_DIR = '/root/ai-agents'
            S.DEFAULT_PARTY_SIZE = 2

            result = agent._schedule_sniper({
                'restaurant': 'fish-cheeks',
                'date': '2026-03-01',
                'preferred_time': '7:00 PM',
                'drop_time': '2026-02-22T09:00:00',
            })

        assert result['success'] is True
        assert result['venue_slug'] == 'fish-cheeks'
        remote_cmd = mock_run.call_args[0][0][-1]
        assert 'fish-cheeks' in remote_cmd

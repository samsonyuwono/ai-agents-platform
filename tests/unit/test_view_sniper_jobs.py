"""Unit tests for view_sniper_jobs handler in ReservationAgent."""

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


def _sample_job(overrides=None):
    """Return a sample sniper job dict as returned by the store."""
    job = {
        'id': 1,
        'venue_slug': 'fish-cheeks',
        'date': '2026-03-01',
        'preferred_times': '7:00 PM',
        'party_size': 2,
        'status': 'pending',
        'scheduled_at': '2026-02-22T09:00:00',
        'poll_count': 0,
        'max_attempts': 50,
        'notes': 'remote:root@server',
    }
    if overrides:
        job.update(overrides)
    return job


class TestViewSniperJobs:
    """Test view_sniper_jobs handler in ReservationAgent."""

    def test_returns_formatted_jobs(self):
        """Two jobs returned — verify success, count, and jobs list."""
        agent = _make_agent()
        agent.store.get_all_sniper_jobs.return_value = [
            _sample_job(),
            _sample_job({'id': 2, 'venue_slug': 'lartusi', 'status': 'completed'}),
        ]

        result = agent.execute_tool('view_sniper_jobs', {})

        assert result['success'] is True
        assert result['count'] == 2
        assert len(result['jobs']) == 2
        assert result['jobs'][0]['restaurant'] == 'fish-cheeks'
        assert result['jobs'][1]['restaurant'] == 'lartusi'

    def test_empty_returns_no_jobs_message(self):
        """No jobs in store — verify count=0 and message present."""
        agent = _make_agent()
        agent.store.get_all_sniper_jobs.return_value = []

        result = agent.execute_tool('view_sniper_jobs', {})

        assert result['success'] is True
        assert result['count'] == 0
        assert 'No sniper jobs' in result['message']

    def test_notes_none_excluded_gracefully(self):
        """Job with notes=None should not raise KeyError."""
        agent = _make_agent()
        agent.store.get_all_sniper_jobs.return_value = [
            _sample_job({'notes': None}),
        ]

        result = agent.execute_tool('view_sniper_jobs', {})

        assert result['success'] is True
        assert result['jobs'][0]['notes'] is None

    def test_job_fields_mapped_correctly(self):
        """Verify field renaming from store dict to formatted output."""
        agent = _make_agent()
        job = _sample_job()
        agent.store.get_all_sniper_jobs.return_value = [job]

        result = agent.execute_tool('view_sniper_jobs', {})

        formatted = result['jobs'][0]
        # id → job_id
        assert formatted['job_id'] == job['id']
        # venue_slug → restaurant
        assert formatted['restaurant'] == job['venue_slug']
        # passthrough fields
        assert formatted['date'] == job['date']
        assert formatted['preferred_times'] == job['preferred_times']
        assert formatted['party_size'] == job['party_size']
        assert formatted['status'] == job['status']
        assert formatted['scheduled_at'] == job['scheduled_at']
        assert formatted['poll_count'] == job['poll_count']
        assert formatted['max_attempts'] == job['max_attempts']
        assert formatted['notes'] == job['notes']

"""Unit tests for ReservationAgent."""

import json
import contextlib
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def agent():
    """Fixture that yields a fully-mocked ReservationAgent."""
    stack = contextlib.ExitStack()

    stack.enter_context(patch('agents.base_agent.anthropic.Anthropic'))
    mock_base_settings = stack.enter_context(patch('agents.base_agent.Settings'))
    mock_ra_settings = stack.enter_context(patch('agents.reservation_agent.Settings'))
    mock_factory = stack.enter_context(patch('utils.resy_client_factory.ResyClientFactory'))
    mock_store = stack.enter_context(patch('agents.reservation_agent.ReservationStore'))

    mock_base_settings.ANTHROPIC_API_KEY = 'test-key'
    mock_base_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
    mock_base_settings.MAX_TOKENS = 4096

    mock_ra_settings.has_resy_configured.return_value = True
    mock_ra_settings.has_resy_browser_configured.return_value = False
    mock_ra_settings.has_email_configured.return_value = False

    mock_factory.create_client.return_value = MagicMock()
    mock_store.return_value = MagicMock()

    from agents.reservation_agent import ReservationAgent
    a = ReservationAgent()
    yield a
    stack.close()


class TestReservationAgent:
    """Test ReservationAgent initialization and tool definitions."""

    def test_init_inherits_from_base_agent(self, agent):
        """Test that ReservationAgent inherits from BaseAgent."""
        from agents.base_agent import BaseAgent
        assert isinstance(agent, BaseAgent)

    def test_init_creates_resy_client(self, agent):
        """Test that init creates a Resy client via factory."""
        assert agent.resy_client is not None

    def test_init_creates_store(self, agent):
        """Test that init creates a ReservationStore."""
        assert agent.store is not None

    def test_init_no_email_when_not_configured(self, agent):
        """Test that email_sender is None when email is not configured."""
        assert agent.email_sender is None

    @patch('agents.reservation_agent.EmailSender')
    @patch('agents.reservation_agent.ReservationStore')
    @patch('utils.resy_client_factory.ResyClientFactory')
    @patch('agents.reservation_agent.Settings')
    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_init_with_email_configured(self, mock_anthropic, mock_base_settings,
                                        mock_ra_settings, mock_factory,
                                        mock_store, mock_email_sender):
        """Test that email_sender is created when email is configured."""
        mock_base_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_base_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
        mock_base_settings.MAX_TOKENS = 4096
        mock_ra_settings.has_resy_configured.return_value = True
        mock_ra_settings.has_resy_browser_configured.return_value = False
        mock_ra_settings.has_email_configured.return_value = True
        mock_factory.create_client.return_value = MagicMock()
        mock_store.return_value = MagicMock()

        from agents.reservation_agent import ReservationAgent
        a = ReservationAgent()
        assert a.email_sender is not None

    @patch('agents.reservation_agent.Settings')
    @patch('agents.base_agent.Settings')
    def test_init_no_resy_config_raises(self, mock_base_settings, mock_ra_settings):
        """Test that missing Resy config raises ValueError."""
        mock_base_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_ra_settings.has_resy_configured.return_value = False
        mock_ra_settings.has_resy_browser_configured.return_value = False

        from agents.reservation_agent import ReservationAgent
        with pytest.raises(ValueError, match="Resy not configured"):
            ReservationAgent()

    @patch('agents.reservation_agent.ReservationStore')
    @patch('agents.base_agent.Settings')
    @patch('agents.base_agent.anthropic.Anthropic')
    def test_init_with_injected_resy_client(self, mock_anthropic, mock_base_settings, mock_store):
        """Test that passing resy_client skips factory and config check."""
        mock_base_settings.ANTHROPIC_API_KEY = 'test-key'
        mock_base_settings.DEFAULT_MODEL = 'claude-sonnet-4-20250514'
        mock_base_settings.MAX_TOKENS = 4096
        mock_store.return_value = MagicMock()

        injected_client = MagicMock()
        from agents.reservation_agent import ReservationAgent
        a = ReservationAgent(resy_client=injected_client)

        assert a.resy_client is injected_client

    def test_define_tools_returns_all_tools(self, agent):
        """Test that define_tools returns all expected tools."""
        tools = agent.define_tools()

        tool_names = [t['name'] for t in tools]
        assert 'search_resy_restaurants' in tool_names
        assert 'check_resy_availability' in tool_names
        assert 'make_resy_reservation' in tool_names
        assert 'search_resy_by_cuisine' in tool_names
        assert 'resolve_reservation_conflict' in tool_names
        assert 'view_my_reservations' in tool_names
        assert 'get_current_time' in tool_names
        assert 'view_sniper_jobs' in tool_names
        assert 'schedule_sniper' in tool_names
        assert len(tools) == 9

    def test_define_tools_have_required_fields(self, agent):
        """Test that each tool has name, description, and input_schema."""
        tools = agent.define_tools()
        for tool in tools:
            assert 'name' in tool
            assert 'description' in tool
            assert 'input_schema' in tool
            assert tool['input_schema']['type'] == 'object'

    def test_system_prompt_contains_date_info(self, agent):
        """Test that system prompt includes current date parsing rules."""
        assert 'CRITICAL DATE PARSING RULES' in agent.system_prompt
        assert 'YYYY-MM-DD' in agent.system_prompt


class TestExecuteToolSearch:
    """Test execute_tool for search-related tools."""

    def test_search_restaurants_success(self, agent):
        """Test search_resy_restaurants returns formatted results."""
        agent.resy_client.search_venues.return_value = [
            {
                'id': '123',
                'name': 'Carbone',
                'url_slug': 'carbone',
                'location': {'neighborhood': 'Greenwich Village', 'city': 'New York'},
                'price_range': '$$$$',
                'rating': 4.8
            },
            {
                'id': '456',
                'name': "L'Artusi",
                'url_slug': 'lartusi',
                'location': {'neighborhood': 'West Village', 'city': 'New York'},
                'price_range': '$$$',
                'rating': 4.6
            }
        ]

        result = agent.execute_tool('search_resy_restaurants', {'query': 'Carbone'})

        assert result['success'] is True
        assert result['count'] == 2
        assert result['restaurants'][0]['name'] == 'Carbone'
        assert result['restaurants'][0]['slug'] == 'carbone'
        assert result['restaurants'][0]['location'] == 'Greenwich Village, New York'

    def test_search_restaurants_no_results(self, agent):
        """Test search_resy_restaurants with no results."""
        agent.resy_client.search_venues.return_value = []

        result = agent.execute_tool('search_resy_restaurants', {'query': 'Nonexistent'})

        assert result['success'] is False
        assert 'No restaurants found' in result['message']
        assert result['query'] == 'Nonexistent'

    def test_search_restaurants_limits_to_5(self, agent):
        """Test that search results are limited to 5."""
        agent.resy_client.search_venues.return_value = [
            {'id': str(i), 'name': f'Restaurant {i}', 'url_slug': f'rest-{i}',
             'location': {}, 'price_range': '$$', 'rating': 4.0}
            for i in range(10)
        ]

        result = agent.execute_tool('search_resy_restaurants', {'query': 'test'})

        assert result['count'] == 5

    def test_search_restaurants_with_location(self, agent):
        """Test search passes location to client."""
        agent.resy_client.search_venues.return_value = []

        agent.execute_tool('search_resy_restaurants',
                           {'query': 'Italian', 'location': 'Manhattan'})

        agent.resy_client.search_venues.assert_called_once_with(
            query='Italian', location='Manhattan')

    def test_search_restaurants_threading_fallback(self, agent):
        """Test threading error triggers subprocess fallback."""
        agent.resy_client.search_venues.side_effect = Exception(
            "cannot be called from a different thread")
        agent._handle_threading_fallback = MagicMock(return_value={
            'success': True,
            'results': [{'id': '1', 'name': 'Test', 'url_slug': 'test',
                         'location': {}, 'price_range': '$$', 'rating': 4.0}]
        })

        result = agent.execute_tool('search_resy_restaurants', {'query': 'test'})

        agent._handle_threading_fallback.assert_called_once()
        assert result['success'] is True

    def test_search_by_cuisine_no_browser_method(self, agent):
        """Test cuisine search fails gracefully without browser client."""
        # Remove search_by_cuisine method to simulate API-only client
        del agent.resy_client.search_by_cuisine

        result = agent.execute_tool('search_resy_by_cuisine',
                                    {'cuisine': 'Japanese'})

        assert result['success'] is False
        assert 'browser mode' in result['message']

    def test_search_by_cuisine_success(self, agent):
        """Test cuisine search returns formatted results with time slots."""
        agent.resy_client.search_by_cuisine.return_value = [
            {
                'name': 'Sushi Nakazawa',
                'slug': 'sushi-nakazawa',
                'rating': 4.9,
                'review_count': 200,
                'cuisine': 'Japanese',
                'price_range': '$$$$',
                'neighborhood': 'West Village',
                'available_times': [
                    {'time': '7:00 PM', 'type': 'Dining Room',
                     'config_id': 'sushi-nakazawa|||2026-03-08|||7:00 PM'}
                ]
            }
        ]

        result = agent.execute_tool('search_resy_by_cuisine',
                                    {'cuisine': 'Japanese', 'neighborhood': 'West Village'})

        assert result['success'] is True
        assert result['count'] == 1
        assert result['restaurants'][0]['name'] == 'Sushi Nakazawa'
        assert len(result['restaurants'][0]['available_times']) == 1

    def test_search_by_cuisine_no_results(self, agent):
        """Test cuisine search with no results."""
        agent.resy_client.search_by_cuisine.return_value = []

        result = agent.execute_tool('search_resy_by_cuisine',
                                    {'cuisine': 'Ethiopian', 'neighborhood': 'Soho'})

        assert result['success'] is False
        assert result['cuisine'] == 'Ethiopian'
        assert result['neighborhood'] == 'Soho'


class TestExecuteToolAvailability:
    """Test execute_tool for availability checking."""

    def test_check_availability_success(self, agent):
        """Test check_resy_availability with available slots."""
        agent.resy_client.get_availability.return_value = [
            {'config_id': 'carbone|||2026-03-10|||7:00 PM',
             'time': '7:00 PM', 'table_name': 'Dining Room'},
            {'config_id': 'carbone|||2026-03-10|||8:00 PM',
             'time': '8:00 PM', 'table_name': 'Bar'},
        ]

        result = agent.execute_tool('check_resy_availability', {
            'venue_id': '123', 'date': '2026-03-10', 'party_size': 2
        })

        assert result['success'] is True
        assert result['count'] == 2
        assert result['available_times'][0]['time'] == '7:00 PM'
        assert result['date'] == '2026-03-10'
        assert result['party_size'] == 2

    def test_check_availability_no_slots(self, agent):
        """Test check_resy_availability with no availability."""
        agent.resy_client.get_availability.return_value = []

        result = agent.execute_tool('check_resy_availability', {
            'venue_id': '123', 'date': '2026-03-10', 'party_size': 4
        })

        assert result['success'] is False
        assert '4 people' in result['message']
        assert '2026-03-10' in result['message']


class TestExecuteToolReservation:
    """Test execute_tool for making and managing reservations."""

    def test_make_reservation_success(self, agent):
        """Test successful reservation booking."""
        agent.resy_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES-12345',
            'venue_slug': 'carbone',
            'time_slot': '7:00 PM',
            'confirmation_token': 'tok-abc'
        }

        result = agent.execute_tool('make_resy_reservation', {
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is True
        assert result['reservation_id'] == 'RES-12345'
        agent.store.add_reservation.assert_called_once()

    def test_make_reservation_saves_to_store(self, agent):
        """Test that successful reservations are persisted."""
        agent.resy_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': 'RES-999',
            'venue_slug': 'lartusi',
            'time_slot': '8:00 PM',
            'confirmation_token': 'tok-xyz'
        }

        agent.execute_tool('make_resy_reservation', {
            'config_id': 'lartusi|||2026-03-15|||8:00 PM',
            'date': '2026-03-15',
            'party_size': 4
        })

        call_args = agent.store.add_reservation.call_args[0][0]
        assert call_args['platform'] == 'resy'
        assert call_args['restaurant_name'] == 'lartusi'
        assert call_args['date'] == '2026-03-15'
        assert call_args['party_size'] == 4
        assert call_args['status'] == 'confirmed'

    def test_make_reservation_unconfirmed(self, agent):
        """Test reservation with no confirmation number gets pending status."""
        agent.resy_client.make_reservation.return_value = {
            'success': True,
            'reservation_id': None,
            'venue_slug': 'carbone',
            'time_slot': '7:00 PM'
        }

        result = agent.execute_tool('make_resy_reservation', {
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is True
        assert 'check their email' in result['message']
        call_args = agent.store.add_reservation.call_args[0][0]
        assert call_args['status'] == 'pending_confirmation'

    def test_make_reservation_failure(self, agent):
        """Test failed reservation returns error info."""
        agent.resy_client.make_reservation.return_value = {
            'success': False,
            'error': 'Could not confirm the reservation'
        }

        result = agent.execute_tool('make_resy_reservation', {
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is False
        assert 'check their Resy app' in result['message']
        agent.store.add_reservation.assert_not_called()

    def test_make_reservation_conflict(self, agent):
        """Test reservation conflict returns status and message."""
        agent.resy_client.make_reservation.return_value = {
            'success': False,
            'status': 'conflict',
            'error': 'You already have a reservation at this time'
        }

        result = agent.execute_tool('make_resy_reservation', {
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is False
        assert result['status'] == 'conflict'

    def test_make_reservation_modal_opened(self, agent):
        """Test reservation that opens modal but fails to book."""
        agent.resy_client.make_reservation.return_value = {
            'success': False,
            'status': 'modal_opened',
            'error': 'Reserve button not found'
        }

        result = agent.execute_tool('make_resy_reservation', {
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert 'modal opened' in result['message'].lower()


class TestExecuteToolConflictResolution:
    """Test execute_tool for reservation conflict resolution."""

    def test_resolve_conflict_continue_booking(self, agent):
        """Test resolving conflict by continuing with new booking."""
        agent.resy_client.resolve_reservation_conflict.return_value = {
            'success': True,
            'status': 'booked',
            'reservation_id': 'RES-NEW',
            'venue_slug': 'carbone',
            'time_slot': '7:00 PM'
        }

        result = agent.execute_tool('resolve_reservation_conflict', {
            'choice': 'continue_booking',
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is True
        agent.store.add_reservation.assert_called_once()

    def test_resolve_conflict_keep_existing(self, agent):
        """Test resolving conflict by keeping existing reservation."""
        agent.resy_client.resolve_reservation_conflict.return_value = {
            'success': True,
            'status': 'kept_existing'
        }

        result = agent.execute_tool('resolve_reservation_conflict', {
            'choice': 'keep_existing',
            'config_id': 'carbone|||2026-03-10|||7:00 PM',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is True
        assert result['status'] == 'kept_existing'
        agent.store.add_reservation.assert_not_called()

    def test_resolve_conflict_invalid_config_id(self, agent):
        """Test conflict resolution with non-standard config_id format."""
        agent.resy_client.resolve_reservation_conflict.return_value = {
            'success': True,
            'status': 'booked',
            'venue_slug': 'test',
            'time_slot': '7:00 PM'
        }

        # config_id without ||| separator should not raise
        result = agent.execute_tool('resolve_reservation_conflict', {
            'choice': 'continue_booking',
            'config_id': 'some-raw-config-id',
            'date': '2026-03-10',
            'party_size': 2
        })

        assert result['success'] is True
        # venue_slug and time_text should be None since parsing failed
        call_kwargs = agent.resy_client.resolve_reservation_conflict.call_args
        assert call_kwargs[1]['venue_slug'] is None
        assert call_kwargs[1]['time_text'] is None


class TestExecuteToolViewAndMisc:
    """Test execute_tool for view and utility tools."""

    def test_view_reservations_with_results(self, agent):
        """Test viewing reservations when there are bookings."""
        agent.resy_client.get_reservations.return_value = [
            {'restaurant': 'Carbone', 'date': '2026-03-10', 'time': '7:00 PM'},
            {'restaurant': "L'Artusi", 'date': '2026-03-12', 'time': '8:00 PM'},
        ]

        result = agent.execute_tool('view_my_reservations', {})

        assert result['success'] is True
        assert result['count'] == 2

    def test_view_reservations_empty(self, agent):
        """Test viewing reservations when there are no bookings."""
        agent.resy_client.get_reservations.return_value = []

        result = agent.execute_tool('view_my_reservations', {})

        assert result['success'] is True
        assert result['count'] == 0
        assert 'No upcoming reservations' in result['message']

    def test_get_current_time(self, agent):
        """Test get_current_time returns formatted time."""
        result = agent.execute_tool('get_current_time', {})

        assert result['success'] is True
        assert 'datetime' in result
        assert 'display' in result
        assert 'T' in result['datetime']

    def test_view_sniper_jobs_with_results(self, agent):
        """Test viewing sniper jobs when jobs exist."""
        agent.store.get_all_sniper_jobs.return_value = [
            {
                'id': 1,
                'venue_slug': 'carbone',
                'date': '2026-03-15',
                'preferred_times': ['7:00 PM'],
                'party_size': 2,
                'status': 'pending',
                'scheduled_at': '2026-03-14T09:00:00',
                'poll_count': 0,
                'max_attempts': 100,
                'notes': None
            }
        ]

        result = agent.execute_tool('view_sniper_jobs', {})

        assert result['success'] is True
        assert result['count'] == 1
        assert result['jobs'][0]['restaurant'] == 'carbone'

    def test_view_sniper_jobs_empty(self, agent):
        """Test viewing sniper jobs when none exist."""
        agent.store.get_all_sniper_jobs.return_value = []

        result = agent.execute_tool('view_sniper_jobs', {})

        assert result['success'] is True
        assert result['count'] == 0

    def test_unknown_tool(self, agent):
        """Test that unknown tools return an error."""
        result = agent.execute_tool('nonexistent_tool', {})

        assert result['success'] is False
        assert 'Unknown tool' in result['error']


class TestRunLoop:
    """Test the run() agentic loop."""

    def test_run_end_turn(self, agent):
        """Test run() with immediate end_turn response."""
        mock_text = MagicMock()
        mock_text.type = 'text'
        mock_text.text = 'Here are some Italian restaurants...'

        mock_response = MagicMock()
        mock_response.stop_reason = 'end_turn'
        mock_response.content = [mock_text]

        agent.client.messages.create.return_value = mock_response

        result = agent.run('Find Italian restaurants')

        assert result == 'Here are some Italian restaurants...'

    def test_run_with_tool_use(self, agent):
        """Test run() executing a tool then returning final answer."""
        # First response: tool_use
        mock_tool_block = MagicMock()
        mock_tool_block.type = 'tool_use'
        mock_tool_block.name = 'search_resy_restaurants'
        mock_tool_block.input = {'query': 'Carbone'}
        mock_tool_block.id = 'tool-123'

        mock_response_1 = MagicMock()
        mock_response_1.stop_reason = 'tool_use'
        mock_response_1.content = [mock_tool_block]

        # Second response: end_turn
        mock_text = MagicMock()
        mock_text.type = 'text'
        mock_text.text = 'I found Carbone in Greenwich Village.'

        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = 'end_turn'
        mock_response_2.content = [mock_text]

        agent.client.messages.create.side_effect = [mock_response_1, mock_response_2]
        agent.resy_client.search_venues.return_value = [
            {'id': '123', 'name': 'Carbone', 'url_slug': 'carbone',
             'location': {}, 'price_range': '$$$$', 'rating': 4.8}
        ]

        result = agent.run('Find Carbone')

        assert result == 'I found Carbone in Greenwich Village.'
        assert agent.client.messages.create.call_count == 2

    def test_run_max_iterations(self, agent):
        """Test run() stops at max_iterations."""
        mock_tool_block = MagicMock()
        mock_tool_block.type = 'tool_use'
        mock_tool_block.name = 'get_current_time'
        mock_tool_block.input = {}
        mock_tool_block.id = 'tool-loop'

        mock_response = MagicMock()
        mock_response.stop_reason = 'tool_use'
        mock_response.content = [mock_tool_block]

        agent.client.messages.create.return_value = mock_response

        result = agent.run('test', max_iterations=3)

        assert 'maximum thinking iterations' in result
        assert agent.client.messages.create.call_count == 3

    def test_run_emits_events(self, agent):
        """Test run() calls event_callback with correct event types."""
        mock_text = MagicMock()
        mock_text.type = 'text'
        mock_text.text = 'Hello!'

        mock_response = MagicMock()
        mock_response.stop_reason = 'end_turn'
        mock_response.content = [mock_text]

        agent.client.messages.create.return_value = mock_response

        events = []
        agent.run('Hi', event_callback=lambda t, d: events.append(t))

        assert 'thinking' in events
        assert 'message' in events
        assert 'done' in events

    def test_run_adds_to_conversation_history(self, agent):
        """Test run() maintains conversation history."""
        mock_text = MagicMock()
        mock_text.type = 'text'
        mock_text.text = 'Response'

        mock_response = MagicMock()
        mock_response.stop_reason = 'end_turn'
        mock_response.content = [mock_text]

        agent.client.messages.create.return_value = mock_response

        agent.run('Hello')

        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]['role'] == 'user'
        assert agent.conversation_history[1]['role'] == 'assistant'


class TestHelperMethods:
    """Test private helper methods."""

    def test_save_reservation_confirmed(self, agent):
        """Test _save_reservation with confirmation number."""
        agent._save_reservation(
            result={'reservation_id': 'RES-1', 'venue_slug': 'carbone',
                    'time_slot': '7:00 PM', 'confirmation_token': 'tok-1'},
            tool_input={'date': '2026-03-10', 'party_size': 2}
        )

        call_args = agent.store.add_reservation.call_args[0][0]
        assert call_args['status'] == 'confirmed'
        assert call_args['confirmation_number'] == 'RES-1'

    def test_save_reservation_pending(self, agent):
        """Test _save_reservation without confirmation number."""
        agent._save_reservation(
            result={'reservation_id': None, 'venue_slug': 'test',
                    'time_slot': '8:00 PM'},
            tool_input={'date': '2026-03-10', 'party_size': 2}
        )

        call_args = agent.store.add_reservation.call_args[0][0]
        assert call_args['status'] == 'pending_confirmation'

    def test_format_confirmation_email(self, agent):
        """Test email formatting includes key details."""
        email = agent._format_confirmation_email(
            result={'reservation_id': 'RES-123'},
            booking_info={'date': '2026-03-10', 'party_size': 2}
        )

        assert 'RES-123' in email
        assert '2026-03-10' in email
        assert '2 people' in email
        assert 'Confirmed' in email

    @patch('agents.reservation_agent.subprocess.run')
    def test_browser_search_subprocess_success(self, mock_run, agent):
        """Test subprocess browser search with valid JSON output."""
        mock_run.return_value = MagicMock(
            stdout='{"success": true, "results": []}',
            stderr=''
        )

        result = agent._browser_search_subprocess('search_venues', {'query': 'test'})

        assert result['success'] is True
        assert result['results'] == []

    @patch('agents.reservation_agent.subprocess.run')
    def test_browser_search_subprocess_timeout(self, mock_run, agent):
        """Test subprocess browser search timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='test', timeout=120)

        result = agent._browser_search_subprocess('search_venues', {'query': 'test'})

        assert result['success'] is False
        assert 'timed out' in result['error']

    @patch('agents.reservation_agent.subprocess.run')
    def test_browser_search_subprocess_empty_output(self, mock_run, agent):
        """Test subprocess browser search with empty output."""
        mock_run.return_value = MagicMock(stdout='', stderr='some error')

        result = agent._browser_search_subprocess('search_venues', {'query': 'test'})

        assert result['success'] is False
        assert 'no output' in result['error'].lower()

    def test_handle_threading_fallback(self, agent):
        """Test threading fallback delegates to subprocess."""
        agent._browser_search_subprocess = MagicMock(return_value={
            'success': True, 'results': [{'name': 'Test'}]
        })

        result = agent._handle_threading_fallback('search_venues', {'query': 'test'})

        assert result['success'] is True
        agent._browser_search_subprocess.assert_called_once_with(
            'search_venues', {'query': 'test'})

    def test_handle_threading_fallback_error_renames_key(self, agent):
        """Test threading fallback renames 'error' to 'message' on failure."""
        agent._browser_search_subprocess = MagicMock(return_value={
            'success': False, 'error': 'Browser failed'
        })

        result = agent._handle_threading_fallback('search_venues', {'query': 'test'})

        assert result['success'] is False
        assert result['message'] == 'Browser failed'
        assert 'error' not in result


class TestIsThreadingError:
    """Test the module-level _is_threading_error helper."""

    def test_threading_error_detected(self):
        from agents.reservation_agent import _is_threading_error
        assert _is_threading_error(Exception("cannot be called from a different thread"))

    def test_non_threading_error(self):
        from agents.reservation_agent import _is_threading_error
        assert not _is_threading_error(Exception("connection refused"))

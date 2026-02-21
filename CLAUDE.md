# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI agents platform for building autonomous agents powered by Claude (Anthropic). Currently includes news digest and research agents, with infrastructure for restaurant reservation automation via Resy API.

## Development Commands

### Setup
```bash
pip3 install -r requirements.txt
```

### Running Agents
```bash
# Research Agent (interactive Q&A with web search)
python3 scripts/run_research_agent.py

# News Digest Agent (automated news collection and summarization)
python3 scripts/run_news_digest.py "AI" "Technology" "SpaceX"
python3 scripts/run_news_digest.py  # Interactive mode

# Daily digest via cron script
./scripts/run_daily_digest.sh
```

### Environment Configuration
All configuration is loaded from `.env` file. Required and optional keys are defined in `config/settings.py`.

## Architecture

### Agent Architecture Pattern

**BaseAgent (`agents/base_agent.py`)**
- Foundation class providing Claude API integration
- Manages conversation history (accessible via `self.conversation_history`)
- Provides `call_claude()` method that handles API calls with tool support
- All new agents should inherit from BaseAgent for consistency

**Exception:** `ResearchAgent` was built before BaseAgent and has its own implementation. Consider refactoring it to use BaseAgent.

### Settings Pattern

Centralized configuration via `config/settings.py`:
- Loads environment variables via `python-dotenv`
- Validates required keys on import (raises error if `ANTHROPIC_API_KEY` missing)
- Provides convenience methods:
  - `Settings.has_email_configured()` - Check if Resend email is set up
  - `Settings.has_search_configured()` - Check if Brave Search is available
  - `Settings.has_resy_configured()` - Check if Resy API credentials are present
  - `Settings.has_opentable_configured()` - Check if OpenTable credentials are present

### Shared Utilities

**Booking Parser (`utils/booking_parser.py`)**
- Natural language parsing for restaurant reservations
- Supports formats: "Temple Court on Feb 18 at 6pm for 2 people"
- Extracts: restaurant name, date, time, party size
- Auto-converts to Resy-compatible format
- Returns structured dict with all booking details

**Slug Utilities (`utils/slug_utils.py`)**
- Restaurant name to URL slug conversion
- Handles special characters, spaces, apostrophes
- Override support for non-standard slugs
- Example: "L'Artusi" → "lartusi", "ABC & Co" → "abc-and-co"

**Selectors (`utils/selectors.py`)**
- Centralized Resy website selectors for browser automation
- Multiple fallback selectors for each element (resilient to UI changes)
- `ResySelectors` class with predefined selectors
- `SelectorHelper` for finding elements with fallback strategies

**Web Search (`utils/web_search.py`)**
- `BraveSearch` class wraps Brave Search API
- Handles rate limiting and error cases
- Returns structured results with title, snippet, URL, and age

**Email (`utils/email_sender.py`)**
- Uses Resend API for email delivery
- Converts markdown to HTML for formatted emails

**Resy Browser Client (`utils/resy_browser_client.py`)**
- Playwright-based browser automation (more reliable than API)
- Session persistence with cookie caching (28s login savings)
- Adaptive rate limiting (6s minimum + jitter)
- Methods: `get_availability()`, `make_reservation()`
- Performance: ~35s first booking, ~7s with cached session

**Resy API Client (`utils/resy_client.py`)**
- API-based integration (fallback when browser not configured)
- Rate limiting with randomized delays (2s minimum + jitter)
- Methods: `search_venues()`, `get_availability()`, `make_reservation()`, `cancel_reservation()`

**Resy Client Factory (`utils/resy_client_factory.py`)**
- Factory pattern for client selection
- Modes: 'api', 'browser', 'auto' (tries API first, falls back to browser)
- Configured via `RESY_CLIENT_MODE` environment variable

**Reservation Store (`utils/reservation_store.py`)**
- SQLite database for tracking reservations across platforms
- Context manager support (`with ReservationStore() as store:`)
- Methods: `add_reservation()`, `get_reservations()`, `update_reservation_status()`

### Tool Use Pattern

Agents use Claude's tool calling feature for autonomous decision making:

1. Define tools in `call_claude()` with JSON schema
2. Claude decides when to use tools based on user input
3. Agent executes tool and returns results to Claude
4. Iterate until Claude provides final answer or hits max iterations

Example from `ResearchAgent`:
- Tool: `web_search` with query parameter
- Agent loops checking `response.stop_reason`
- If `tool_use`, execute tool and add results to conversation history
- If `end_turn`, extract final answer and return

### Creating New Agents

1. **Create agent class** in `agents/your_agent.py`
   - Inherit from `BaseAgent`
   - Override `__init__()` if additional setup needed
   - Implement `run()` method with core logic

2. **Create runner script** in `scripts/run_your_agent.py`
   - Add path manipulation: `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`
   - Import and instantiate your agent
   - Handle command-line arguments if needed

3. **Make executable**: `chmod +x scripts/run_your_agent.py`

## Key Implementation Details

### Conversation History Management

Both `BaseAgent` and `ResearchAgent` maintain conversation history:
- Messages alternate between `user` and `assistant` roles
- Tool results are added as `user` messages with `tool_result` type
- Use `add_to_history()` to append messages
- Use `clear_history()` to reset conversation

### ResearchAgent Agentic Loop

The `run()` method implements an agentic loop pattern:
- Max iterations limit (default: 5) prevents infinite loops
- Checks `stop_reason` to determine next action
- Handles `tool_use` by executing tools and continuing loop
- Handles `end_turn` by extracting and returning final answer

### Rate Limiting in ResyClient

Critical for avoiding bot detection:
- Tracks `last_request_time` per client instance
- Enforces minimum 2 second delay between requests
- Adds random jitter (0.5-1.5s) to appear human-like
- Handles 429 rate limit responses with 60s backoff and retry

### NewsDigestAgent Workflow

1. Search news for each topic via Brave Search (`freshness="pd"` for past day)
2. Collect and format articles with title, snippet, URL, age
3. Send to Claude with prompt asking for synthesis and summary
4. Save markdown output to `news/` folder
5. Send formatted HTML email via Resend

## Testing Approach

**Test Infrastructure:**
- pytest framework with 30+ passing unit tests
- Test coverage: 100% on slug_utils, 97% on booking_parser
- Tests located in `tests/unit/` and `tests/integration/`
- Configuration: `pytest.ini`

**Running Tests:**
```bash
pytest                    # All tests
pytest tests/unit/ -v     # Unit tests only
pytest --cov=utils --cov=config --cov-report=html  # With coverage
```

**Test Organization:**
- `tests/unit/test_booking_parser.py` - Natural language parsing tests
- `tests/unit/test_slug_utils.py` - Slug conversion tests
- `tests/unit/test_settings.py` - Configuration validation tests

**Manual Testing:**
- Use `.env` file for API keys (never commit)
- Research agent has interactive chat mode for manual testing
- News digest saves to `news/` folder for inspection
- Logs are written to `logs/` folder for cron jobs

## Cron Automation

Daily news digest runs at 7 AM via cron:
- Configured in user's crontab
- Executes `scripts/run_daily_digest.sh`
- Topics defined in TOPICS array in the shell script
- Logs to `logs/cron.log` and `logs/daily_digest.log`

## Model Configuration

Default model: `claude-sonnet-4-20250514` (defined in `Settings.DEFAULT_MODEL`)
- Can be overridden in agent constructors
- Max tokens: 4096 (defined in `Settings.MAX_TOKENS`)

## File Organization

- `agents/` - Agent implementations
- `utils/` - Shared utilities (search, email, APIs)
- `config/` - Configuration and settings
- `scripts/` - Executable entry points
- `news/` - Generated news digests (gitignored)
- `logs/` - Log files (gitignored)
- `data/` - SQLite databases (created on first use)

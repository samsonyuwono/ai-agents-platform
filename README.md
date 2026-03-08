# AI Agents Platform

A platform for building autonomous AI agents powered by Claude (Anthropic). Currently includes three agents — a research assistant, a news digest generator, and a restaurant reservation agent with automated drop-time sniping.

## 🏗️ Project Structure

```
ai-agents/
├── agents/                        # 🤖 All AI agents
│   ├── base_agent.py             # Base class for all agents
│   ├── research_agent.py         # Research/Q&A agent
│   ├── news_digest_agent.py      # News digest agent
│   └── reservation_agent.py      # Restaurant reservation agent (Resy)
│
├── utils/                         # 🛠️ Shared utilities
│   ├── availability_filter.py    # Slot matching and ranking
│   ├── booking_parser.py         # Natural language booking parsing
│   ├── email_sender.py           # Email delivery (Resend)
│   ├── notification.py           # Sniper success/failure email alerts
│   ├── reservation_sniper.py     # Automated slot grabbing at drop time
│   ├── reservation_store.py      # SQLite reservation & job tracking
│   ├── resy_browser_client.py    # Playwright browser automation for Resy
│   ├── resy_client.py            # Resy REST API client
│   ├── resy_client_factory.py    # Factory for API vs browser client
│   ├── selectors.py              # Resy website CSS selectors
│   ├── slug_utils.py             # Restaurant name → URL slug
│   └── web_search.py             # Web search (Brave API)
│
├── config/
│   └── settings.py               # Centralized settings and env var loading
│
├── scripts/                       # 🚀 Executable scripts
│   ├── run_research_agent.py     # Run research agent
│   ├── run_news_digest.py        # Run news digest
│   ├── run_daily_digest.sh       # Cron job for daily digest
│   ├── run_reservation_agent.py  # Run reservation agent
│   ├── run_sniper.py             # Sniper CLI (create, list, cancel jobs)
│   ├── sniper_worker.py          # Sniper daemon (systemd service)
│   ├── export_resy_session.py    # Export auth session to VPS
│   └── deploy_sniper.sh          # One-command VPS deployment
│
├── deploy/
│   └── sniper.service            # systemd unit file for sniper worker
│
├── docs/                          # 📚 Documentation
│   ├── reservation-agent-iteration-report.md
│   ├── vps-bot-detection.md
│   ├── raspberry-pi-deployment.md
│   └── TODO.md
│
├── tests/                         # 🧪 264 unit tests
│   └── unit/
│
├── data/                          # 💾 SQLite databases (created on first use)
├── news/                          # 📰 Generated news digests
└── logs/                          # 📝 Log files
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
# Required
ANTHROPIC_API_KEY=your_anthropic_key

# For web search (optional)
BRAVE_API_KEY=your_brave_key

# For email (optional)
RESEND_API_KEY=your_resend_key
EMAIL_FROM=noreply@yourdomain.com
EMAIL_TO=your@email.com
```

### 3. Run an Agent

**Research Agent:**

```bash
python3 scripts/run_research_agent.py
# Or use alias: run-agent
```

**News Digest:**

```bash
python3 scripts/run_news_digest.py
# Or use alias: news-digest
```

## 🤖 Agents

### Research Agent

Interactive Q&A agent with web search. Ask questions, get answers backed by real-time search results. Maintains conversation context across turns.

```bash
python3 scripts/run_research_agent.py
```

- Autonomous tool use — Claude decides when to search vs answer directly
- Brave Search integration for real-time web results
- Multi-turn conversation with history
- Agentic loop with configurable max iterations

### News Digest Agent

Automated news collection and AI-powered summarization. Searches multiple topics, synthesizes results, and delivers a formatted digest via email.

```bash
python3 scripts/run_news_digest.py "AI" "Technology" "SpaceX"
python3 scripts/run_news_digest.py   # Interactive mode
```

- Multi-topic search with freshness filtering (past 24h)
- Claude-powered synthesis across sources
- HTML email delivery via Resend
- Markdown export to `news/` folder
- Cron automation for daily 7 AM digests

### Reservation Agent

Conversational restaurant reservation assistant for Resy. Handles the full lifecycle — search, availability, booking, and automated sniping at drop time.

```bash
python3 scripts/run_reservation_agent.py
# "Book Temple Court on Feb 18 at 6pm for 2"
# "Search Italian restaurants"
# "Snipe Fish Cheeks on March 5 at 7pm, drop time is tomorrow at 9am"
# "Show me my sniper jobs"
```

**9 Claude tools:**

| Tool | Description |
|---|---|
| `search_resy_restaurants` | Find restaurants by name |
| `search_resy_by_cuisine` | Browse by cuisine type |
| `check_resy_availability` | Real-time slot availability |
| `make_resy_reservation` | Book a specific slot |
| `resolve_reservation_conflict` | Handle time conflicts with alternatives |
| `schedule_sniper` | Set up automated drop-time booking |
| `view_sniper_jobs` | Monitor scheduled and completed jobs |
| `view_my_reservations` | List all reservations |
| `get_current_time` | Current EST time for scheduling context |

**Dual execution mode:**
- **API mode** — Direct HTTP calls to Resy's endpoints. Lightweight (18MB), runs on VPS. Works for restaurants with API-accessible availability.
- **Browser mode** — Playwright automation with session persistence. Handles all restaurants including those with bot detection. Requires residential IP.

Configurable via `RESY_CLIENT_MODE` env var (`api`, `browser`, or `auto`).

**Reservation sniper:**

The sniper is a standalone automation engine (no LLM) that rapid-polls for availability at drop time and books the first matching slot.

```bash
# Create and run immediately
python3 scripts/run_sniper.py fish-cheeks 2026-03-01 "7:00 PM"

# Schedule for a future drop time
python3 scripts/run_sniper.py fish-cheeks 2026-03-01 "7:00 PM" --at "2026-02-22 09:00"

# List all jobs
python3 scripts/run_sniper.py --list

# Cancel a job
python3 scripts/run_sniper.py --cancel 5
```

Features: scheduled execution, time-window matching, conflict resolution, sibling job cancellation (prevents duplicate bookings), email notifications with poll error diagnostics, graceful SIGTERM shutdown, SQLite job persistence.

**Sniper worker daemon** (for always-on operation):

```bash
python3 scripts/sniper_worker.py   # Polls every 10s, picks up due jobs
```

Deployed as a systemd service on VPS or home hardware. See `deploy/sniper.service`.

**Performance:**
- First booking (with login): ~35 seconds
- Subsequent bookings (cached session): ~7 seconds
- Sniper first-poll success rate: ~75%

**Successful bookings:** Le Gratin, Delmonicos, Temple Court, Rezdora, Bowery Meat Company, Cuerno, Pepolino

## 🏗️ How the Agents Work

All agents follow the same core pattern: define tools, let Claude decide when to use them, execute tool calls, and loop until Claude provides a final answer.

### Agent Architecture

```
User Input
    ↓
┌─────────────────────┐
│  Agent (BaseAgent)   │
│                      │
│  1. Send message to  │
│     Claude with      │
│     tool definitions │
│  2. Claude responds  │
│     with tool_use    │──→ Execute tool (search, book, check, etc.)
│     or end_turn      │←── Return result to Claude
│  3. Loop until       │
│     end_turn or max  │
│     iterations       │
└─────────────────────┘
    ↓
Final Answer
```

**BaseAgent** (`agents/base_agent.py`) provides:
- Claude API integration via `call_claude()` with automatic tool handling
- Conversation history management (messages alternate user/assistant roles)
- Tool results injected as `tool_result` messages for Claude to reason over

### Research Agent Flow

1. User asks a question
2. Claude evaluates whether it can answer directly or needs to search
3. If `web_search` tool is called → Brave Search API → results returned to Claude
4. Claude synthesizes search results into a final answer
5. Loop continues (up to 5 iterations) if Claude needs more searches

### News Digest Agent Flow

1. For each topic (e.g., "AI", "SpaceX"):
   - Search Brave API with `freshness="pd"` (past day)
   - Collect articles with title, snippet, URL, age
2. Send all collected articles to Claude with a synthesis prompt
3. Claude generates a structured digest with highlights and summaries
4. Save markdown to `news/` folder
5. Convert to HTML and email via Resend

### Reservation Agent Flow

1. User describes what they want in natural language
2. Claude selects from 9 tools based on intent:
   - Search request → `search_resy_restaurants` or `search_resy_by_cuisine`
   - Availability check → `check_resy_availability`
   - Booking → `make_resy_reservation` (with `resolve_reservation_conflict` if needed)
   - Sniping → `schedule_sniper` (creates a job for future execution)
3. Tool results return structured dicts with `success` bool and descriptive data
4. Claude chains tools autonomously (e.g., search → check availability → book)
5. Confirmation email sent on successful booking

### Sniper Engine (No LLM)

The sniper is pure automation — no Claude involved. Speed matters at drop time.

1. Worker daemon polls SQLite every 10 seconds for due jobs
2. When a job fires: check availability → match preferred times → book first match
3. If preferred time taken, try adjacent slots within the time window
4. On success: cancel sibling jobs, send confirmation email
5. On failure: retry up to max attempts, then send failure email with error diagnostics

## 🧪 Testing

### Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# With coverage report
pytest --cov=utils --cov=config --cov-report=html

# Specific test file
pytest tests/unit/test_booking_parser.py -v
```

### Test Coverage

The project includes comprehensive unit tests for:

- **Booking parser** - Natural language parsing
- **Slug utilities** - Restaurant name conversion
- **Availability filter** - Slot matching and ranking
- **Reservation sniper** - Job execution, polling, error tracking
- **Reservation store** - SQLite persistence and queries
- **Notification** - Success/failure email formatting
- **Settings** - Configuration validation

**Current stats:** 264 passing tests

### Writing Tests

Tests are organized in `tests/`:

- `tests/unit/` - Fast unit tests (no external dependencies)
- `tests/integration/` - Integration tests (require browser/API)

See `tests/unit/test_booking_parser.py` for examples.

## 🔧 Configuration

### Settings (config/settings.py)

All configuration is centralized in `Settings` class:

```python
from config.settings import Settings

# Check if email is configured
if Settings.has_email_configured():
    # Send email
    pass

# Access API keys
api_key = Settings.ANTHROPIC_API_KEY
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `BRAVE_API_KEY` | ❌ | Brave Search API (for web search) |
| `RESEND_API_KEY` | ❌ | Resend API (for emails & sniper notifications) |
| `EMAIL_FROM` | ❌ | From email address |
| `EMAIL_TO` | ❌ | Recipient email address |
| `RESY_API_KEY` | ❌ | Resy API key |
| `RESY_AUTH_TOKEN` | ❌ | Resy auth token |
| `RESY_BROWSER_EMAIL` | ❌ | Resy login email (browser mode) |
| `RESY_BROWSER_PASSWORD` | ❌ | Resy login password (browser mode) |
| `RESY_CLIENT_MODE` | ❌ | Client mode: `api`, `browser`, or `auto` |
| `RESY_PROXY_SERVER` | ❌ | Residential proxy server (e.g., `http://gate.decodo.com:10001`) |
| `RESY_PROXY_USERNAME` | ❌ | Proxy username |
| `RESY_PROXY_PASSWORD` | ❌ | Proxy password |
| `SNIPER_REMOTE_HOST` | ❌ | SSH target for remote deployment (e.g., `root@159.89.41.103`) |

## 🆕 Creating a New Agent

### Step 1: Create Agent Class

Create `agents/your_agent.py`:

```python
from agents.base_agent import BaseAgent
from utils.web_search import BraveSearch
from utils.email_sender import EmailSender
from config.settings import Settings


class YourAgent(BaseAgent):
    """Your agent description."""

    def __init__(self):
        super().__init__()
        # Add any additional initialization

    def run(self, input_data):
        """Main agent logic."""
        # Your agent code here
        response = self.call_claude("Your prompt here")
        return response
```

### Step 2: Create Runner Script

Create `scripts/run_your_agent.py`:

```python
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.your_agent import YourAgent


def main():
    agent = YourAgent()
    result = agent.run("input")
    print(result)


if __name__ == "__main__":
    main()
```

### Step 3: Make it Executable

```bash
chmod +x scripts/run_your_agent.py
```

### Step 4: Add Alias (Optional)

Add to `~/.zshrc`:

```bash
alias your-agent='cd ~/Desktop/Development/ai-agents && python3 scripts/run_your_agent.py'
```

## 🛠️ Shared Utilities

### Booking Parser (utils/booking_parser.py)

Natural language parsing for restaurant reservations:

```python
from utils.booking_parser import parse_booking_request

result = parse_booking_request("Temple Court on Feb 18 at 6pm for 2")
# Returns: {
#   'restaurant_name': 'Temple Court',
#   'restaurant_slug': 'temple-court',
#   'date': '2026-02-18',
#   'time': '6:00 PM',
#   'party_size': 2
# }
```

### Slug Utilities (utils/slug_utils.py)

Convert restaurant names to URL-safe slugs:

```python
from utils.slug_utils import normalize_slug

slug = normalize_slug("Temple Court")  # Returns: "temple-court"
slug = normalize_slug("L'Artusi")      # Returns: "lartusi"
```

### Web Search (utils/web_search.py)

```python
from utils.web_search import BraveSearch

search = BraveSearch()
results = search.search("AI news", num_results=5)
```

### Email Sender (utils/email_sender.py)

```python
from utils.email_sender import EmailSender

sender = EmailSender()
sender.send(
    to_email="user@example.com",
    subject="Test",
    content="# Hello\nThis is markdown content"
)
```

### Reservation Sniper (utils/reservation_sniper.py)

Automated slot grabbing with polling, booking, and notification:

```python
from utils.reservation_sniper import ReservationSniper

with ReservationSniper() as sniper:
    job_id = sniper.create_job(
        venue_slug="fish-cheeks",
        date="2026-03-01",
        preferred_times=["7:00 PM", "7:30 PM"],
        party_size=2,
        scheduled_at="2026-02-28T09:00:00",
    )
    result = sniper.run_job(job_id)
```

### Reservation Store (utils/reservation_store.py)

SQLite database for tracking reservations and sniper jobs:

```python
from utils.reservation_store import ReservationStore

with ReservationStore() as store:
    store.add_reservation({...})
    store.add_sniper_job({...})
    jobs = store.get_sniper_jobs(status='pending')
```

### Notification (utils/notification.py)

Email alerts for sniper job outcomes:

```python
from utils.notification import SniperNotifier

notifier = SniperNotifier()
notifier.notify_success(job, result)
notifier.notify_failure(job, reason)
```

### Availability Filter (utils/availability_filter.py)

Slot matching and ranking against preferred times:

```python
from utils.availability_filter import pick_best_slot

best = pick_best_slot(slots, ["7:00 PM"], window_minutes=30)
```

### Selectors (utils/selectors.py)

Centralized selectors for Resy website automation:

```python
from utils.selectors import ResySelectors, SelectorHelper

# Use predefined selectors
email_input = ResySelectors.EMAIL_INPUT

# Helper to find elements with multiple selector fallbacks
element = SelectorHelper.find_element(page, ResySelectors.LOGIN_BUTTON)
```

## ⏰ Automation

### Daily News Digest (7 AM)

The news digest runs automatically every morning at 7 AM via cron.

**View cron jobs:**

```bash
crontab -l
```

**Edit topics:**
Edit `scripts/run_daily_digest.sh` and change the `TOPICS` array:

```bash
TOPICS=("AI" "Technology" "Your Topic Here")
```

**View logs:**

```bash
cat logs/cron.log
cat logs/daily_digest.log
```

## 📚 API Keys & Services

### Anthropic Claude API

- **Get key:** <https://console.anthropic.com/>
- **Pricing:** Pay-as-you-go
- **Models:** Sonnet 4, Opus 4, Haiku 4

### Brave Search API

- **Get key:** <https://brave.com/search/api/>
- **Free tier:** 2,000 searches/month
- **No credit card required**

### Resend Email API

- **Get key:** <https://resend.com/>
- **Free tier:** 3,000 emails/month (100/day)
- **Setup:** Add domain or use `no-reply@resend.dev` for testing

## 🎯 Best Practices

### 1. Inherit from BaseAgent

Always extend `BaseAgent` for new agents to get standard functionality.

### 2. Use Settings

Access configuration through `Settings` class, not direct env vars.

### 3. Reuse Utilities

Use shared utilities (web search, email) instead of duplicating code.

### 4. Add Type Hints

Use Python type hints for better IDE support and documentation.

### 5. Error Handling

Always handle exceptions gracefully and provide useful error messages.

## 🐛 Troubleshooting

### "ANTHROPIC_API_KEY not found"

Make sure `.env` file exists and contains your API key.

### Email not sending

- Check that `RESEND_API_KEY`, `EMAIL_FROM`, and `EMAIL_TO` are set
- Verify `EMAIL_FROM` domain is verified in Resend (or use `noreply@resend.dev`)
- Check spam folder

### Web search not working

- Verify `BRAVE_API_KEY` is set correctly
- Check you haven't exceeded free tier limits (2,000/month)

### Cron job not running

- Verify cron is enabled: `crontab -l`
- Check logs: `cat logs/cron.log`
- Ensure script has execute permissions: `chmod +x scripts/run_daily_digest.sh`

## 📝 License

MIT - Feel free to use and modify!

## 🤝 Contributing

This is a personal project, but feel free to fork and customize for your needs!

---

**Built with ❤️ using Claude by Anthropic**

# AI Agents Platform

A scalable platform for building and deploying AI agents powered by Claude (Anthropic).

## 🏗️ Project Structure

```
ai-agents/
├── .env                          # Environment variables (API keys, config)
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── README.md                     # This file
│
├── agents/                       # 🤖 All AI agents
│   ├── __init__.py
│   ├── base_agent.py            # Base class for all agents
│   ├── research_agent.py        # Research/Q&A agent
│   ├── news_digest_agent.py     # News digest agent
│   └── reservation_agent.py     # Restaurant reservation agent (Resy)
│
├── utils/                        # 🛠️ Shared utilities
│   ├── __init__.py
│   ├── availability_filter.py   # Slot matching and ranking
│   ├── booking_parser.py        # Natural language booking parsing
│   ├── email_sender.py          # Email functionality (Resend)
│   ├── notification.py          # Sniper success/failure email alerts
│   ├── reservation_sniper.py    # Automated slot grabbing at drop time
│   ├── reservation_store.py     # SQLite reservation & job tracking
│   ├── resy_browser_client.py   # Playwright browser automation for Resy
│   ├── resy_client.py           # Resy REST API client
│   ├── resy_client_factory.py   # Factory for API vs browser client
│   ├── selectors.py             # Resy website CSS selectors
│   ├── slug_utils.py            # Restaurant name → URL slug
│   └── web_search.py            # Web search (Brave API)
│
├── config/                       # ⚙️ Configuration
│   ├── __init__.py
│   └── settings.py              # Centralized settings
│
├── scripts/                      # 🚀 Executable scripts
│   ├── run_research_agent.py    # Run research agent
│   ├── run_news_digest.py       # Run news digest
│   ├── run_daily_digest.sh      # Cron job script
│   ├── run_reservation_agent.py # Run reservation agent
│   └── run_sniper.py            # Run reservation sniper
│
├── data/                         # 💾 SQLite databases (created on first use)
├── news/                         # 📰 Generated news digests
└── logs/                         # 📝 Log files
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

## 🤖 Available Agents

### 1. Research Agent

Interactive Q&A agent that can search the web and maintain conversation context.

**Features:**

- Web search integration
- Conversation history
- Tool use (autonomous decision making)
- Interactive chat mode

**Usage:**

```bash
run-agent
```

### 2. News Digest Agent

Collects news about topics you care about and generates a daily digest.

**Features:**

- Multi-topic search
- AI-powered summarization
- Email delivery
- Markdown export
- Automated scheduling (cron)

**Usage:**

```bash
news-digest
# Or with topics:
python3 scripts/run_news_digest.py "AI" "SpaceX" "Climate"
```

### 3. Reservation Agent

Automated restaurant booking agent for Resy using browser automation.

**Features:**

- Browser automation with Playwright (more reliable than API)
- Natural language booking requests
- Session persistence (cached login)
- Rate limiting to protect account
- Automatic confirmation detection

**Usage:**

```bash
python3 scripts/run_reservation_agent.py
# Then use natural language: "Book Temple Court on Feb 18 at 6pm for 2"
```

**Performance:**

- Initial booking (with login): ~35 seconds
- Subsequent bookings (cached session): ~7 seconds
- Availability check only: ~3 seconds

### 4. Reservation Sniper

Automated slot grabbing that rapid-polls for availability at drop time and books the first matching slot. No LLM involved — pure automation for speed.

**Features:**

- Scheduled job execution (fires at a specific datetime)
- Configurable preferred times with flexible time window matching
- Automatic conflict resolution (cancels existing reservation to rebook)
- Sibling job cancellation (avoids duplicate bookings)
- Email notifications on success or failure
- Poll error diagnostics in failure emails (summarizes why each poll failed)
- Graceful shutdown on SIGINT/SIGTERM
- SQLite-backed job persistence and tracking

**Usage:**

```bash
# Run all pending scheduled sniper jobs
python3 scripts/run_sniper.py

# Jobs are created programmatically or via the reservation agent's schedule_sniper tool
```

**Failure Diagnostics:**

When a sniper job exhausts all attempts, the failure email includes a breakdown of poll errors to help diagnose the issue:

```
Max attempts (60) reached

## Poll Errors
- No slots available (55x)
- Availability check failed: browser closed (5x)

Note: 2 poll(s) found only event-style listings...
```

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

**Current stats:** 222 passing tests

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
- **Setup:** Add domain or use `onboarding@resend.dev` for testing

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

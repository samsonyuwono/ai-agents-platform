# AI Agents — Project Todo List

## High Priority

- [ ] **Resy location tracking** — Track and store the city/location code (ny, sf, la) associated with each venue lookup, reservation, and sniper job so results are location-aware across the platform.
- [ ] **Email confirmation format** — Improve the reservation confirmation email template with better formatting, restaurant details (name, address, time), and consistent branding. (`agents/reservation_agent.py:_format_confirmation_email`, `utils/email_sender.py`)
- [ ] **Neighborhood-based restaurant lookup** — Add ability to search/browse Resy restaurants by neighborhood (e.g., "West Village", "SoHo"). Use Resy's location/neighborhood filters in both API and browser clients, and expose as a ReservationAgent tool. (`utils/resy_client.py`, `utils/resy_browser_client.py`, `agents/reservation_agent.py`)

## Medium Priority

- [ ] **Add resy_browser_client tests** — ~1800 lines with zero unit tests. At minimum, test the parsing/extraction logic separately from Playwright calls. (`utils/resy_browser_client.py`)
- [ ] **Document remote sniper deployment** — `SNIPER_REMOTE_HOST` setup, SSH keys, systemd service installation, and monitoring. No docs exist beyond the deploy script itself. (`scripts/deploy_sniper.sh`, `deploy/sniper.service`)
- [ ] **Clean up bare exceptions in browser client** — 22+ bare `except:` clauses. CLAUDE.md discourages this for new code. Gradually replace with specific exception types where feasible. (`utils/resy_browser_client.py`)
- [ ] **Add log rotation** — Cron jobs write to `logs/` with no rotation. Add logrotate config or size-based rotation.

## Low Priority

- [ ] **Archive debug scripts** — `scripts/debug_buttons.py` and `scripts/auto_check_availability.py` are loose one-off scripts. Either integrate into the framework or move to a `scripts/debug/` folder.
- [ ] **Reduce script/utils duplication** — `scripts/reservation_sniper.py` wraps `utils/reservation_sniper.py` with minimal added value. Consider consolidating.
- [ ] **Add integration test suite** — `tests/integration/` folder exists but is mostly empty. Add tests that exercise real API calls (gated behind env vars / CI flags).
- [ ] **Refactor ResearchAgent to use BaseAgent** — Built before BaseAgent existed; has its own API integration and conversation history. Align with the pattern used by NewsDigestAgent and ReservationAgent. (`agents/research_agent.py`)

## Done (Recently Completed)

- [x] **Switch sniper from browser to API mode** — Added slug-to-ID resolution, auth token refresh, API conflict resolution, relaxed rate limiting. Deployed to VPS. (`utils/resy_client.py`, `config/settings.py`)
- [x] **Add ResyClient unit tests** — 13 tests covering init, token refresh, 401 auto-retry, slug resolution, conflict resolution. (`tests/unit/test_resy_client.py`)
- [x] **Deploy API-mode sniper to VPS** — Memory dropped from 393MB to 18MB, no Chromium dependency.
- [x] **Add ReservationAgent unit tests** — Complex tool execution logic (9 tool handlers) has zero test coverage. Test each handler: search, availability, booking, conflict resolution, sniper scheduling, view jobs.

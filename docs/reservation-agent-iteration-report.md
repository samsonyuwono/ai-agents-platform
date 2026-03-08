# Building an AI Reservation Agent: An Iteration Report

## Executive Summary

We built an AI-powered reservation agent that handles the full lifecycle of restaurant bookings — from discovery and availability checking to automated sniping at drop time. The agent is conversational (powered by Claude), understands natural language requests, and can autonomously execute multi-step booking flows across Resy.

The system was developed across 13 iterations over two weeks, with each iteration driven by a specific failure mode discovered in production. We shipped 27 incremental changes, wrote 264 automated tests, and successfully booked 20+ reservations across 7 restaurants — including notoriously difficult venues like Le Gratin, Rezdora, and Temple Court.

---

## MVP Definition (Current)

The reservation agent MVP is a conversational AI assistant that handles restaurant reservations end-to-end on Resy. A user can speak naturally ("Book me a table at Le Gratin next Saturday at 6pm for 2") and the agent handles the rest.

### Core Capabilities

| Capability | Description | Status |
|---|---|---|
| **Restaurant search** | Search by name or cuisine type, resolve to Resy venue | Shipped |
| **Availability check** | Check real-time availability for a venue, date, and party size | Shipped |
| **Instant booking** | Book an available slot immediately with conflict resolution | Shipped |
| **Sniper scheduling** | Schedule a job to auto-book at a future drop time | Shipped |
| **Job management** | View, cancel, and monitor sniper jobs with status dashboard | Shipped |
| **Duplicate prevention** | Auto-cancel sibling jobs when a booking succeeds | Shipped |
| **Failure diagnostics** | Categorized error summaries in email notifications | Shipped |
| **Email confirmations** | Confirmation email sent on successful booking | Shipped |
| **Dual execution mode** | API mode (lightweight, VPS) and browser mode (local, full compatibility) | Shipped |
| **Session export** | Export authenticated session from laptop to VPS for remote execution | Shipped |
| **Multi-UI support** | Handles both standard time-slot grids and event-style card layouts | Shipped |

### Agent Tools (9 tools)

1. `search_resy_restaurants` — Find restaurants by name
2. `search_resy_by_cuisine` — Browse by cuisine type
3. `check_resy_availability` — Real-time slot availability
4. `make_resy_reservation` — Book a specific slot
5. `resolve_reservation_conflict` — Handle time conflicts with alternatives
6. `schedule_sniper` — Set up automated drop-time booking
7. `view_sniper_jobs` — Monitor scheduled and completed jobs
8. `view_my_reservations` — List all reservations
9. `get_current_time` — Current EST time for scheduling context

### Operational Architecture

- **Local (laptop):** Full capability — browser mode works with residential IP, handles all restaurants including those with aggressive bot detection
- **VPS ($6/month):** API-mode bookings only — always-on, 18MB footprint, handles restaurants available via Resy API
- **Sniper worker:** systemd daemon polling every 10s, graceful shutdown, stale job recovery

### What's NOT in the MVP

- Multi-platform support (OpenTable, Tock) — stubs exist but no implementation
- Neighborhood-based browsing — Resy's facet filters are unreliable
- Web/mobile UI — agent is CLI-only via Claude conversation
- Multi-user support — single user, single credential set
- Automatic drop-time detection — user must know when slots release

---

## The Problem

Getting a reservation at a popular restaurant shouldn't require setting an alarm, refreshing a page at exactly 9:00:00 AM, and hoping your fingers are fast enough. But that's reality on Resy, where the most sought-after tables disappear in under 10 seconds.

The manual process is fragile: you need to know the exact drop time, be online and ready, click through multiple screens faster than hundreds of other people, and handle conflicts when your preferred time is already taken — all before you've had your morning coffee.

No existing tool solved this reliably. We set out to change that.

---

## The Iterations

### Iteration 1: Core Sniper Engine

**Hypothesis:** If we can poll Resy the instant slots drop and book faster than any human, we solve the core problem.

We built a job scheduler that fires at the precise drop time, detects newly available time slots, matches them against user preferences, and completes the booking automatically. When the preferred time is taken, the engine tries adjacent slots rather than giving up.

**Key decision:** SQLite for job persistence — lightweight, zero infrastructure, portable enough to run anywhere. Polling architecture over webhooks, since Resy offers no API for drop-time notifications.

**Outcome:** Core loop worked. First successful automated booking.

### Iteration 2: Making It Human-Friendly

**Problem discovered:** Users had to know internal restaurant identifiers and construct machine-formatted timestamps just to schedule a job.

That's an unacceptable UX tax. We added natural language input so users could say "Fish Cheeks" instead of needing to know the platform-specific slug. The system resolves names automatically and handles the formatting internally.

**Decision:** Meet users where they are. If the system can figure it out, the user shouldn't have to.

**Outcome:** Scheduling a snipe went from requiring three technical parameters to one natural sentence.

### Iteration 3: Timezone Correctness

**Problem discovered:** Jobs were firing at the wrong time because the server's timezone didn't match the restaurant's timezone.

Everything appeared to work — jobs ran, slots were checked, bookings were attempted. But the sniper was arriving late to the drop because the schedule was off by hours. We forced all scheduling to EST, the restaurant industry standard for Resy drop times.

**Outcome:** Jobs now fire at the correct moment. Eliminated a class of "it ran but missed the window" failures.

**Lesson:** Timezone bugs are silent. Everything "works," just at the wrong time.

### Iteration 4: Observability and Diagnostics

**Problem discovered:** When the sniper failed, users had no idea why. Was the restaurant sold out? Did something crash? Is it even running?

We added a job status dashboard, error frequency tracking, and detailed failure notifications via email. Diagnostics are surfaced through the same chat interface users already interact with — no separate monitoring tool needed.

For example, a failure summary might read: "No slots available (55x), Browser crashed (5x)." That instantly tells the user whether it was a supply problem or a technical one — fundamentally different issues requiring different responses.

**Outcome:** Users can self-diagnose failures. Support burden dropped to zero.

**Decision:** Observability isn't a developer luxury; it's a user necessity.

### Iteration 5: Preventing Duplicate Reservations

**Problem discovered:** Two sniper jobs targeting the same restaurant could both succeed, creating unwanted duplicate bookings — and potentially unwanted credit card charges.

We implemented automatic sibling job cancellation: when one job books successfully, all related pending jobs are immediately cancelled.

**Outcome:** Zero duplicate bookings since implementation. Verified in production when job #35 auto-cancelled sibling job #34.

**Decision:** Cancel-on-success is safer than lock-on-start. If the first job crashes before booking, a lock would have prevented the second job from trying. By waiting until success is confirmed, we avoid losing attempts while still preventing duplicates.

### Iteration 6: Handling UI Variants

**Problem discovered:** Some Resy restaurants use a completely different booking interface — event-style cards instead of standard time slot grids.

The sniper was successfully navigating to the restaurant page but couldn't find any bookable slots, because it was looking for UI elements that didn't exist on that page layout. We added detection logic to identify which interface variant is present and handle both patterns dynamically.

**Outcome:** Unlocked a new category of restaurants (event-format venues) that were previously un-snipeable.

**Lesson:** Never assume a platform has one UI. Always handle variants.

### Iteration 7: Bot Detection and Residential Proxy

**Problem discovered:** Resy uses bot detection, and data center IP addresses are blocked almost instantly.

No amount of clever request timing or header spoofing was going to solve this. We added residential proxy routing so that browser traffic appears to originate from regular home internet connections — a configuration-level solution rather than a code-level workaround.

**Outcome:** Unblocked the sniper from running on infrastructure outside a home network.

**Decision:** Bot detection is an infrastructure problem, not a code problem. The fix belongs in the environment configuration, not scattered through application logic.

### Iteration 8: The "Last Mile" Bug

**Problem discovered:** The sniper correctly found available slots, opened the booking modal, but couldn't complete the final step — clicking the "Reserve Now" button. Three separate root causes were hiding behind one symptom:

1. **Browser viewport too short** — the confirmation button was below the visible area
2. **Nested iframe** — the booking form loads inside an iframe the automation wasn't waiting for
3. **False success reporting** — the system reported success before the booking was actually confirmed

We fixed all three and added a defense-in-depth click strategy with three fallback methods for the critical final action.

**Outcome:** Booking completion rate went from ~0% to near-100% for available slots. This was the single highest-impact fix.

**Lesson:** End-to-end testing is non-negotiable. Each component working individually doesn't mean the full flow works.

### Iteration 9: Code Quality Pass

**Problem:** Fast iteration had left dead code paths and duplicated logic across the codebase.

We cleaned up unreachable code, extracted shared constants, and added targeted tests for the areas that had been moving fastest. This wasn't just cosmetic — duplicated logic means duplicated bugs.

**Outcome:** Test coverage jumped from 8% to 50% on the browser client. Reduced maintenance risk for future iterations.

**Decision:** Refactor after stabilizing, not during. Shipping working code first and cleaning up afterward was the right sequencing. Premature refactoring during rapid iteration would have slowed us down without improving outcomes.

### Iteration 10: API Mode and VPS Deployment

**Problem discovered:** The browser-based sniper consumed ~393MB of memory on the VPS due to headless Chromium, and was overkill for restaurants whose booking flow is available via Resy's API.

We built a parallel API-mode sniper — direct HTTP calls to Resy's `/4/find` and `/3/book` endpoints, no browser needed. This required slug-to-venue-ID resolution, auth token refresh with automatic 401 retry, and API-native conflict resolution. Memory dropped from 393MB to 18MB.

We deployed to a DigitalOcean VPS as a systemd service with a continuous worker daemon replacing cron. The worker polls every 10 seconds, handles graceful SIGTERM shutdown, and auto-resets stale jobs from previous crashes.

**Outcome:** Always-on sniper running for $6/month with 18MB memory footprint. Successfully booked Delmonicos remotely with laptop closed.

**Key decision:** Dual-mode architecture via factory pattern — API mode for speed and efficiency, browser mode as fallback. Configurable via environment variable, not code changes.

### Iteration 11: PerimeterX Bot Detection on VPS

**Problem discovered:** Resy upgraded from Akamai to PerimeterX/HUMAN bot detection — significantly more aggressive. Both API and browser modes were blocked on the VPS. The API returned 0 slots; the browser loaded the page but CAPTCHA prevented time slots from rendering.

This was invisible at first. The page appeared functional (40+ buttons visible), but no reservation slots appeared. The sniper reported "No slots available" — making it look like a supply problem rather than a detection problem.

**Outcome:** Documented the issue, evaluated three mitigation strategies, and chose the most pragmatic path forward.

**Lesson:** Bot detection evolves. A solution that works today (residential proxy + Akamai bypass) can stop working overnight when the platform switches vendors. Monitor for silent failures — "no slots" doesn't always mean no slots.

### Iteration 12: Session Export from Laptop to VPS

**Hypothesis:** If we export a fully authenticated session from a trusted environment (laptop with residential IP), the VPS can reuse it to bypass PerimeterX.

We built a session export pipeline: authenticate on the laptop via headful Chromium (where CAPTCHA can be solved manually if needed), export Playwright's full `storage_state` (cookies + localStorage, where PerimeterX stores fingerprinting tokens), SCP to the VPS, restart the sniper service.

This replaced cookie-only persistence with full storage state throughout the browser client, added a one-command export script (`export_resy_session.py`), and made the sniper worker session-aware at startup.

**Outcome:** The exported session got past the VPS login check — a partial win. But PerimeterX still flagged the VPS browser environment during availability checks. Slots continued to not render despite a valid session.

**Lesson:** Authentication and bot detection are separate problems. Passing the login check doesn't mean passing the fingerprint check. PerimeterX evaluates the browser environment continuously — not just at login.

### Iteration 13: Accepting the Constraint

**Problem discovered:** After testing session export, residential proxies, and stealth hardening, we confirmed that no combination bypasses PerimeterX on a datacenter VPS. The fingerprinting evaluates the entire browser environment (WebGL renderer, canvas, audio context, screen properties) — which fundamentally differs between a real laptop and a headless Linux server.

However, the VPS works perfectly for API-mode bookings. Delmonicos (job #36) booked on the first poll with the laptop closed. The constraint is browser-mode only.

**Decision:** Stop iterating on VPS browser-mode. The reliable architecture is:
- **VPS** for API-mode bookings — lightweight, always-on, 18MB, $6/month
- **Laptop** for browser-mode bookings — residential IP, real browser fingerprint, requires laptop open at drop time
- **Session export** stays in the toolkit for future platforms with less aggressive fingerprinting

**Outcome:** Clear operational model. Users know which restaurants work remotely and which need local execution.

**Lesson:** Know when to stop. We tried stealth hardening, proxy routing, and session export — each was a reasonable hypothesis, each solved a piece of the puzzle, and none solved the full problem. The constraint isn't temporary or fixable with more code. A datacenter VM will never look like a real user's laptop to a sophisticated fingerprinting system. Recognizing this saved us from an infinite iteration loop.

---

## Results

| Metric | Value |
|--------|-------|
| Development timeline | 2 weeks (Feb 21 – Mar 8, 2026) |
| Iterations | 13 phases across 27 incremental changes |
| Automated tests | 264 (including 90+ for sniper and browser client) |
| Successful bookings | 20+ confirmed reservations |
| Restaurants booked | Le Gratin, Delmonicos, Temple Court, Rezdora, Bowery Meat Company, Cuerno, Pepolino |
| First-poll success rate | ~75% (most bookings complete on the first availability check) |
| VPS memory footprint | 18MB (API mode) vs 393MB (browser mode) |
| Infrastructure cost | $6/month (DigitalOcean droplet) |

---

## Key Product Takeaways

1. **Ship, then polish.** We got the core booking loop working first and refined UX, edge cases, and code quality iteratively. Perfecting early iterations would have delayed learning.

2. **Silent failures are the most dangerous.** Timezone drift, false-success reporting, and bot detection blocking are harder to catch than crashes. The system appeared healthy while quietly failing. Invest in correctness validation, not just error handling.

3. **Infrastructure over cleverness.** Bot detection couldn't be outsmarted with code. It required proxy infrastructure, then ultimately a real browser on a real machine. Some problems don't have software solutions.

4. **Defense in depth.** Critical paths need multiple fallback strategies. The booking click uses three methods. The sniper has two execution modes. No single approach works for all scenarios.

5. **Observability is a user feature.** Users need to understand failures, not just see them. "It didn't work" is not actionable. "No slots were available after 55 attempts" is.

6. **Know when to stop iterating.** Not every problem has a code solution. We tried three approaches to bypass VPS bot detection — each was a reasonable bet, and recognizing the architectural constraint after testing them saved us from an infinite loop. The best iteration is sometimes the one where you stop and design around the constraint instead.

7. **Dual-mode beats single-mode.** Building both API and browser execution wasn't over-engineering — it was the only way to cover the full restaurant landscape. The factory pattern made this a configuration choice, not a code fork.

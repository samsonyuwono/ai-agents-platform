# Building an Automated Reservation Sniper: An Iteration Report

## Executive Summary

We built an automated reservation sniper that books tables at high-demand restaurants the instant they become available. Popular restaurants on Resy release tables at a fixed drop time — typically 9 AM EST — and sell out within seconds. Our sniper eliminates the need for users to be online at the exact right moment, handling the entire flow from slot detection to confirmed booking. The system was developed across 9 distinct iterations and 19 incremental changes, arriving at a production-ready tool backed by 228 automated tests.

---

## The Problem

Getting a reservation at a popular restaurant shouldn't require setting an alarm, refreshing a page at exactly 9:00:00 AM, and hoping your fingers are fast enough. But that's reality on Resy, where the most sought-after tables disappear in under 10 seconds.

The manual process is fragile: you need to know the exact drop time, be online and ready, click through multiple screens faster than hundreds of other people, and handle conflicts when your preferred time is already taken — all before you've had your morning coffee.

No existing tool solved this reliably from a server. We set out to change that.

---

## The Iterations

### 1. Core Sniper Engine

**Hypothesis:** If we can poll Resy the instant slots drop and book faster than any human, we solve the core problem.

We built a job scheduler that fires at the precise drop time, detects newly available time slots, matches them against user preferences, and completes the booking automatically. When the preferred time is taken, the engine tries adjacent slots rather than giving up.

**Key decision:** We chose SQLite for job persistence — lightweight, zero infrastructure, and portable enough to run anywhere. We also chose a polling architecture over webhooks, since Resy offers no API for drop-time notifications.

### 2. Making It Human-Friendly

**Problem discovered:** Users had to know internal restaurant identifiers and construct machine-formatted timestamps just to schedule a job.

That's an unacceptable UX tax. We added natural language input so users could say "Fish Cheeks" instead of needing to know the platform-specific slug. The system resolves names automatically and handles the formatting internally.

**Decision:** Meet users where they are. If the system can figure it out, the user shouldn't have to.

### 3. Timezone Correctness

**Problem discovered:** Jobs were firing at the wrong time because the server's timezone didn't match the restaurant's timezone.

Everything appeared to work — jobs ran, slots were checked, bookings were attempted. But the sniper was arriving late to the drop because the schedule was off by hours. We forced all scheduling to EST, the restaurant industry standard for Resy drop times.

**Lesson:** Timezone bugs are silent. Everything "works," just at the wrong time.

### 4. Observability and Diagnostics

**Problem discovered:** When the sniper failed, users had no idea why. Was the restaurant sold out? Did something crash? Is it even running?

We added a job status dashboard, error frequency tracking, and detailed failure notifications. Diagnostics are surfaced through the same chat interface users already interact with — no separate monitoring tool needed.

For example, a failure summary might read: "No slots available (55x), Browser crashed (5x)." That instantly tells the user whether it was a supply problem or a technical one — fundamentally different issues requiring different responses.

**Decision:** Observability isn't a developer luxury; it's a user necessity.

### 5. Preventing Duplicate Reservations

**Problem discovered:** Two sniper jobs targeting the same restaurant could both succeed, creating unwanted duplicate bookings — and potentially unwanted credit card charges.

We implemented automatic sibling job cancellation: when one job books successfully, all related pending jobs are immediately cancelled.

**Decision:** Cancel-on-success is safer than lock-on-start. If the first job crashes before booking, a lock would have prevented the second job from trying. By waiting until success is confirmed, we avoid losing attempts while still preventing duplicates.

### 6. Handling UI Variants

**Problem discovered:** Some Resy restaurants use a completely different booking interface — event-style cards instead of standard time slot grids.

The sniper was successfully navigating to the restaurant page but couldn't find any bookable slots, because it was looking for UI elements that didn't exist on that page layout. We added detection logic to identify which interface variant is present and handle both patterns dynamically.

**Lesson:** Never assume a platform has one UI. Always handle variants.

### 7. Bot Detection and Infrastructure

**Problem discovered:** Resy uses Akamai bot detection, and data center IP addresses are blocked almost instantly.

No amount of clever request timing or header spoofing was going to solve this. We added residential proxy routing so that browser traffic appears to originate from regular home internet connections — a configuration-level solution rather than a code-level workaround.

**Decision:** Bot detection is an infrastructure problem, not a code problem. The fix belongs in the environment configuration, not scattered through application logic.

### 8. The "Last Mile" Bug

**Problem discovered:** The sniper correctly found available slots, opened the booking modal, but couldn't complete the final step — clicking the "Reserve Now" button. Three separate root causes were hiding behind one symptom:

1. **Browser viewport too short** — the confirmation button was below the visible area
2. **Nested iframe** — the booking form loads inside an iframe the automation wasn't waiting for
3. **False success reporting** — the system reported success before the booking was actually confirmed

We fixed all three and added a defense-in-depth click strategy with three fallback methods for the critical final action.

**Lesson:** End-to-end testing is non-negotiable. Each component working individually doesn't mean the full flow works.

### 9. Code Quality Pass

**Problem:** Fast iteration had left dead code paths and duplicated logic across the codebase.

We cleaned up unreachable code, extracted shared constants, and added targeted tests for the areas that had been moving fastest. This wasn't just cosmetic — duplicated logic means duplicated bugs.

**Decision:** Refactor after stabilizing, not during. Shipping working code first and cleaning up afterward was the right sequencing. Premature refactoring during rapid iteration would have slowed us down without improving outcomes.

---

## Summary

| Metric | Value |
|--------|-------|
| Development iterations | 9 phases across 19 incremental changes |
| Automated tests | 228 (including 60+ new for the sniper) |
| Core capabilities | Scheduled booking, time-slot matching, conflict resolution, failure diagnostics, bot detection bypass, duplicate prevention |

---

## Key Product Takeaways

1. **Ship, then polish.** We got the core booking loop working first and refined UX, edge cases, and code quality iteratively. Perfecting early iterations would have delayed learning.

2. **Silent bugs are the worst.** Timezone drift and false-success statuses are harder to catch than crashes. The system appeared healthy while quietly failing. Invest in correctness checks, not just error handling.

3. **Infrastructure over cleverness.** Bot detection couldn't be outsmarted with code tricks. It required proxy infrastructure — a fundamentally different kind of solution that no amount of application-level optimization would have replaced.

4. **Defense in depth.** Critical paths need multiple fallback strategies. The final booking click uses three different methods because no single approach is reliable across all page states.

5. **Observability from day one.** Users need to understand failures, not just see them. "It didn't work" is not actionable. "No slots were available after 55 attempts" is.

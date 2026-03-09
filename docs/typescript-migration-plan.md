# Python → TypeScript Migration (Incremental)

## Context

The `ai-agents` repo is ~11,000 lines of Python. You don't know Python, making the codebase hard to maintain and debug. The frontend (`reservation-ui`) is already TypeScript. This migration unifies the stack so you can work across both repos in one language.

**Approach**: Incremental. Each phase produces a **working, deployable system**. You can stop after any phase and have a functional product. Python code is only deleted once its TypeScript replacement is verified.

## Tech Stack

| Concern | Python (current) | TypeScript (target) |
|---------|-------------------|---------------------|
| Web framework | FastAPI + uvicorn | Hono + @hono/node-server |
| LLM SDK | `anthropic` | `@anthropic-ai/sdk` |
| Auth | `pyjwt` | `jsonwebtoken` |
| Database | `sqlite3` | `better-sqlite3` |
| HTTP client | `requests` | native `fetch` |
| Email | `resend` | `resend` |
| Browser automation | `playwright` (sync) | `playwright` (async) |
| Validation | Pydantic | `zod` |
| Testing | pytest | vitest |
| Build/Run | `python3` | `tsx` (dev), `tsup` (build) |

## Target Directory Structure

```
src/
  config/
    settings.ts
  agents/
    base-agent.ts
    research-agent.ts
    news-digest-agent.ts
    reservation-agent.ts
  api/
    app.ts
    auth.ts
    chat.ts
    session.ts
    schemas.ts
  utils/
    web-search.ts
    email-sender.ts
    slug-utils.ts
    booking-parser.ts
    availability-filter.ts
    resy-client.ts
    resy-browser-client.ts
    resy-client-factory.ts
    reservation-store.ts
    reservation-sniper.ts
    notification.ts
    selectors.ts
tests/
  unit/
    (one .test.ts per module)
package.json
tsconfig.json
vitest.config.ts
```

TypeScript lives in `src/`, Python stays at root — they coexist without conflicts during migration.

---

## Phase 1: Web UI Backend (Reservation Agent + API)

**Goal**: Replace the Python backend that the `reservation-ui` frontend talks to. This is the code you actively use and need to maintain. After this phase, the web UI runs on TypeScript.

**What gets migrated** (~2,800 lines):
- `config/settings.py` → `src/config/settings.ts`
- `agents/base_agent.py` → `src/agents/base-agent.ts`
- `agents/reservation_agent.py` → `src/agents/reservation-agent.ts`
- `utils/slug_utils.py` → `src/utils/slug-utils.ts`
- `utils/reservation_store.py` → `src/utils/reservation-store.ts`
- `utils/resy_client.py` → `src/utils/resy-client.ts`
- `utils/resy_client_factory.py` → `src/utils/resy-client-factory.ts`
- `utils/selectors.py` → `src/utils/selectors.ts`
- `api/main.py` → `src/api/app.ts`
- `api/auth.py` → `src/api/auth.ts`
- `api/chat.py` → `src/api/chat.ts`
- `api/session.py` → `src/api/session.ts`
- `api/schemas.py` → `src/api/schemas.ts`

**Steps**:

1. **Scaffold** — `package.json`, `tsconfig.json`, `vitest.config.ts`, install deps
2. **Config** — `src/config/settings.ts`: env loading via `dotenv`, validation
3. **Leaf utils** — `slug-utils.ts`, `selectors.ts`: pure logic, no I/O
4. **Database** — `reservation-store.ts`: `better-sqlite3`, same schema/queries
5. **Resy API client** — `resy-client.ts`: `fetch()`, rate limiting, all methods async
6. **Client factory** — `resy-client-factory.ts`: returns API client only (browser client comes in Phase 3)
7. **Base agent** — `base-agent.ts`: `@anthropic-ai/sdk`, async `callClaude()`
8. **Reservation agent** — `reservation-agent.ts`: 8 tool handlers, agentic loop, `eventCallback`
9. **API layer** — `schemas.ts` (zod), `auth.ts` (JWT middleware), `session.ts` (Map, no locks needed), `chat.ts` (Hono `streamSSE`, no thread bridge), `app.ts` (Hono + CORS)
10. **Tests** — Port corresponding test files from pytest to vitest
11. **Verify** — Start TypeScript backend, connect `reservation-ui`, test login → chat → search → book

**What still runs on Python**: Research agent, news digest, browser client, sniper. All CLI-only features.

**Deliverable**: `npm run dev:api` replaces `uvicorn api.main:app`. Frontend works identically.

### Key file mappings and translation notes

| Python file | TS file | Key changes |
|-------------|---------|-------------|
| `config/settings.py` | `src/config/settings.ts` | `os.environ.get()` → `process.env`, class → const object |
| `agents/base_agent.py` | `src/agents/base-agent.ts` | `client.messages.create()` becomes `await`, SDK types for messages |
| `agents/reservation_agent.py` | `src/agents/reservation-agent.ts` | `execute_tool()` → `async executeTool()`, `subprocess.run` → `child_process.exec` for SSH, `zoneinfo` → `date-fns-tz` |
| `utils/resy_client.py` | `src/utils/resy-client.ts` | `requests.Session` → `fetch()` wrapper, `time.sleep()` → `await delay()`, define `IResyClient` interface |
| `utils/reservation_store.py` | `src/utils/reservation-store.ts` | `sqlite3` → `better-sqlite3` (both sync), context manager → `try/finally` |
| `api/chat.py` | `src/api/chat.ts` | **Simplifies**: no `asyncio.Queue`, no thread bridge. Agent loop runs directly in Hono's SSE stream |
| `api/auth.py` | `src/api/auth.ts` | FastAPI `Depends(require_auth)` → Hono middleware function |

### SSE streaming improvement

The Python version uses `asyncio.Queue` + `threading.Thread` to bridge the sync agent into an async SSE stream. In TypeScript, the Anthropic SDK is natively async, so the agent loop runs directly inside Hono's `streamSSE` helper. No thread bridge, no queue, no `check_same_thread=False`. This fixes the threading bugs we hit.

---

## Phase 2: CLI Reservation Agent + Sniper

**Goal**: The CLI `run_reservation_agent.py` and sniper scripts work in TypeScript. After this phase, you can delete all reservation-related Python code.

**What gets migrated** (~1,700 lines):
- `utils/booking_parser.py` → `src/utils/booking-parser.ts`
- `utils/availability_filter.py` → `src/utils/availability-filter.ts`
- `utils/notification.py` → `src/utils/notification.ts`
- `utils/email_sender.py` → `src/utils/email-sender.ts`
- `utils/reservation_sniper.py` → `src/utils/reservation-sniper.ts`
- `scripts/run_reservation_agent.py` → `src/scripts/run-reservation-agent.ts`
- `scripts/run_sniper.py` → `src/scripts/run-sniper.ts`
- `scripts/sniper_worker.py` → `src/scripts/sniper-worker.ts`

**Steps**:
1. **Booking parser** — regex date/time/party extraction, `datetime` → `date-fns`
2. **Availability filter** — time slot matching logic
3. **Email sender** — `resend` npm package (nearly identical API)
4. **Notification** — sniper success/failure email templates
5. **Reservation sniper** — `signal.signal()` → `process.on()`, `Counter` → `Map`, all async
6. **CLI scripts** — `input()` → `node:readline/promises`, `argparse` → `process.argv`
7. **Tests** — Port sniper/parser/filter tests
8. **Verify** — `tsx src/scripts/run-reservation-agent.ts` interactive chat works, `tsx src/scripts/run-sniper.ts` schedules jobs

**Deliverable**: `npm run reservation` and `npm run sniper` replace Python CLI commands.

**Cleanup**: Delete `scripts/run_reservation_agent.py`, `scripts/run_sniper.py`, `scripts/sniper_worker.py`, `utils/booking_parser.py`, `utils/availability_filter.py`, `utils/notification.py`, `utils/reservation_sniper.py`.

---

## Phase 3: Browser Client

**Goal**: Port the Playwright browser automation. After this phase, `RESY_CLIENT_MODE=browser` works in TypeScript.

**What gets migrated** (~1,900 lines):
- `utils/resy_browser_client.py` → `src/utils/resy-browser-client.ts`
- `scripts/export_resy_session.py` → `src/scripts/export-resy-session.ts`
- Update `resy-client-factory.ts` to support browser mode

**Key changes**:
- Python `sync_playwright()` → async Playwright API (every call gets `await`)
- TypeScript catches missing `await` at compile time (Promise type mismatch)
- Implements same `IResyClient` interface as the API client
- Cookie/session persistence: `Path.home()` → `os.homedir()`
- **No more threading issues** — Playwright async in Node.js runs in the same event loop as the web server

**Deliverable**: Browser client works for cuisine search and all booking flows.

**Cleanup**: Delete `utils/resy_browser_client.py`, `scripts/export_resy_session.py`.

---

## Phase 4: Research + News Agents

**Goal**: Port the remaining agents. After this phase, all Python is deleted.

**What gets migrated** (~650 lines):
- `agents/research_agent.py` → `src/agents/research-agent.ts`
- `agents/news_digest_agent.py` → `src/agents/news-digest-agent.ts`
- `utils/web_search.py` → `src/utils/web-search.ts`
- `scripts/run_research_agent.py` → `src/scripts/run-research-agent.ts`
- `scripts/run_news_digest.py` → `src/scripts/run-news-digest.ts`

**Deliverable**: `npm run research` and `npm run news` work.

**Final cleanup**:
- Delete all remaining `.py` files
- Delete `requirements.txt`, `pytest.ini`, `tests/conftest.py`, `tests/__init__.py`
- Update `.gitignore`
- Rewrite `CLAUDE.md` for TypeScript
- Update shell scripts

---

## What Each Phase Gives You

| After Phase | Web UI works? | CLI reservation? | Sniper? | Browser mode? | Research/News? |
|-------------|---------------|-------------------|---------|---------------|----------------|
| **Phase 1** | **TS** | Python | Python | Python | Python |
| **Phase 2** | TS | **TS** | **TS** | Python | Python |
| **Phase 3** | TS | TS | TS | **TS** | Python |
| **Phase 4** | TS | TS | TS | TS | **TS** (all Python deleted) |

You can stop after Phase 1 and have a fully working web UI on TypeScript while rarely-used features stay on Python.

---

## Verification (per phase)

Each phase is verified before moving on:
1. `npm run typecheck` — zero type errors
2. `npm test` — all migrated tests pass
3. Feature-specific manual test (see deliverable per phase)
4. For Phase 1 specifically: `reservation-ui` frontend works end-to-end

## Transition Strategy

1. Each phase gets its own branch off `main`:
   - Phase 1: `migration/phase1-web-api`
   - Phase 2: `migration/phase2-cli-sniper`
   - Phase 3: `migration/phase3-browser-client`
   - Phase 4: `migration/phase4-research-news`
2. TypeScript in `src/`, Python at root — coexist during migration
3. Python tests (`pytest`) continue to run for unmigrated modules
4. Delete Python files per-phase only after TypeScript replacement is verified
5. **Each phase creates a PR for your manual review and approval before merging to `main`** — no auto-merging, no force pushes. You review the diff, test it, and merge when satisfied.
6. Next phase branches off the updated `main` after the previous PR is merged

# Tests — usage and coverage

`httpx.AsyncClient` (via `ASGITransport`) runs the FastAPI app **in-process**
(no server needed): each `await client.get/post(...)` goes through real
routing, dependencies, JWT auth, role guards, and SlowAPI checks. Tests are
native async on the anyio plugin (asyncio backend, per-test loops); the
`tests/realism/` suite adds one shared-loop + lifespan-on session for
concurrency. The suite below is the easy way to verify what
is built today and to lock in behavior as you build more.

## Prerequisites

```bash
docker compose up -d postgres redis
make test-db   # create 9jastay_test once (idempotent) + alembic upgrade head
uv sync        # installs pytest + anyio (dev group) + httpx
```

The suite uses a **dedicated test database** (`TEST_DATABASE_URL`,
default `.../9jastay_test` on the same docker Postgres) — never the dev DB.
`tests/conftest.py` swaps `DATABASE_URL`/`REDIS_URL` (db index 1) before any
`app.*` import so the global engine, helpers, and seed all follow, and
aborts unless the active db name contains "test". Every test still starts
from a truncated + minimally seeded state (`tests/helpers.py`: 2 room types,
rooms 101/102/105/201/202, guest × 2, receptionist, manager — all password
`Password123!`), so it is safe to re-run any time but **do not point
TEST_DATABASE_URL at a production database** (the guard only checks for
"test" in the name).

The webhook secret is read from `.env` (`WEBHOOK_SECRET`, min 8 chars) through
`app.core.config.settings` — it is never hardcoded in tests. Override per run
with `WEBHOOK_SECRET=... uv run pytest` if needed.

## Run

```bash
uv run pytest -q                 # whole suite (correctness + realism)
make test                        # test-db first, then the suite (blessed path)
uv run pytest tests/test_auth.py -q
uv run pytest tests/test_payments_webhook.py -v   # HMAC cases verbosely
uv run pytest tests/realism/ -q  # concurrency only (needs lifespan-friendly env)
```

All API paths are versioned (`/api/v1/...`); legacy unprefixed paths are
only served if mounted in `app/main.py`.

## Layout

| File | Covers |
|---|---|
| `tests/conftest.py` | `AsyncClient` fixture, per-test DB reset+seed, per-test redis client, role login fixtures, session `password_hash` (bcrypt once), `anyio_backend → asyncio`, `limiter.enabled = False` (see below) |
| `tests/helpers.py` | Native-async DB seed/count helpers, `login_headers`, `sign_raw` / `encode_event` / `make_event` webhook helpers (no `asyncio.run` anywhere) |
| `tests/test_auth.py` | `POST /auth/register` 201 + duplicate 409; `POST /auth/login` 200/401; `GET /users/me` 200/401 |
| `tests/test_rooms.py` | `GET /rooms/` list (open, `room_id` keys) + `room_state` filter + invalid 422; `GET /rooms/search` happy path, bad-dates 422, unavailable room excluded |
| `tests/test_bookings.py` | `POST /holds/{id}` 201/400/404/403; `POST /bookings/` 201 with hold, 409 without, 422 bad dates; `POST /bookings/{id}/check-in` 200 receptionist / 403 guest / 409 non-confirmed |
| `tests/test_payments_webhook.py` | HMAC webhook cases (table below) + `verify_signature` unit tests |
| `tests/test_payments_offline.py` | `POST /payments/offline/{id}`: receptionist 201 + confirmed, walk-in without hold, wrong amount 422, non-processing/double-pay 409, unknown 404, guest/manager 403 |
| `tests/test_sweeper.py` | `cancel_stale_processing`: stale-by-age cancelled + hold freed, fresh/CONFIRMED untouched, past check-in cancelled, other-guest hold preserved, custom grace, hold-window boundary, room searchable after sweep |
| `tests/test_rooms_stream.py` | Dashboard stream: payload shape, real-redis publish round-trip, generator yield/disconnect, router publishing on check-in + offline pay + webhook confirm (async anyio tests, no per-call loops) |
| `tests/realism/` | Session-loop + lifespan-on concurrency: hold/booking/pay races, webhook retry storm, stream-under-write, expired hold. Seeded once, rooms partitioned per test, no truncation. See below. |

## Dashboard stream (`GET /rooms/stream`, SSE)

## HMAC webhook coverage (`POST /api/v1/webhooks/payment`)

Signing mirrors `mock_payment_provider.sign`: `HMAC-SHA256(secret, raw_bytes).hexdigest()`
sent as `X-Signature`. The router verifies the seal on the **raw body bytes**
*before* parsing JSON, so tests POST `content=<exact signed bytes>`, never `json=`.

| Case | Request | Expect |
|---|---|---|
| Valid `payment.succeeded`, amount == total, `NGN` | correct sig | 200 `confirmed`; booking → confirmed, `Payment` + `ProcessedEvent` + nightly `RoomNight`s created, hold deleted |
| Provider retry (same `event_id` + bytes) | correct sig twice | 200 `duplicate`; payment count unchanged |
| Wrong signature | `deadbeef…` | 401, nothing written |
| Missing signature | no header | 401 |
| Tampered body (sign A, send B) | mismatched sig | 401 |
| Amount mismatch | correct sig, wrong amount | 422, booking stays `processing`, no payment |
| Unknown reference | correct sig | 200 `orphan`, event logged |
| Non-succeeded type (`payment.failed`) | correct sig | 200 `ignored`, booking untouched |
| Invalid JSON with valid sig | sig over `b"{not-json"` | 422 |
| `verify_signature` unit | direct calls | valid passes; wrong/empty raise `WebhookAuthError` |

## Dashboard stream (`GET /api/v1/rooms/stream`, SSE)

Manager-only (front-desk dashboards); deltas carry
room status only, no guest data. Responsibility split:

- `app/integrations/redis.py` — connection lifecycle (`app.state.redis`).
- `app/domains/rooms/streaming.py` — `CHANNEL`, `RoomDashboardRead` payload,
  best-effort `publish_room_status` / `publish_booking_room`, the subscribe loop.
- `rooms/router.py` — thin `EventSourceResponse` endpoint (`@limiter.exempt`).
- Publishing routers call `publish_booking_room` after success: booking
  check-in, webhook `confirmed`, offline record. Services stay
  transport-agnostic. Publishing never fails the response (skipped without
  redis; redis errors logged).

Test notes: `conftest.py` attaches a fresh real-redis client per test on the
test's own loop (one loop per test under anyio — no hopping by construction).
Pub/sub units share that loop; router wiring is asserted via a spy.
`redis-py` can miss the first poll window, so tests poll in a retry loop.
Requires `docker compose up -d redis` (`REDIS_URL`, default
`redis://localhost:6379/0`).

## Bugs this suite caught and fixed

1. **Webhook router never mounted** — `payments/router.py:root_router`
   (`POST /api/v1/webhooks/payment`) was not included in `app/main.py`, so every
   webhook delivery returned 404. Fixed by importing and including it as
   `payments_webhook_router`.
2. **`Room` had no `room_state`** — `check_in/out_guest` assigned
   `room.room_state`, raising `ValueError: "Room" object has no field "room_state"`
   (500 on check-in). Fixed by adding `room_state: RoomState = CLEAN` to the
   `Room` model + migration `746006cfbe5d`.
3. **Payment/event insert order** — `process_payment_event` added the `Payment`
   row before its parent `ProcessedEvent` row, violating
   `payments_provider_event_id_fkey` (500 on every real confirmation). Fixed by
   adding + flushing the `ProcessedEvent` first.

## Offline payments (`POST /payments/offline/{booking_id}`)

Receptionist-only, no hold required (walk-ins confirmable), exact amount only.
Writes a `Payment(method=offline, provider_event_id=NULL, recorded_by=staff)`
and no `ProcessedEvent` row — those remain provider-only. `provider_event_id`
is nullable since migration `132d37c678b0`.

## Sweepers (runs every 60s / 5min in `lifespan`, never in correctness tests)

- `delete_expired_holds` (60s): removes expired + consumed holds.
- `cancel_stale_processing` (300s, grace 3 min): cancels (never deletes)
  `PROCESSING` bookings older than the grace or with past check-in, and frees
  the booking's own hold. Correctness tests call them directly with `await`;
  `helpers.backdate_booking` moves `created_at` into the past for fixtures.
- Known gap, bitten once: sweepers have no Redis access, so `rooms:search:*`
  heals by 60s TTL. `test_room_searchable_after_sweep` expires the search
  cache explicitly so it asserts sweep correctness, not TTL.

## Realism suite (`tests/realism/`, one loop + lifespan on)

The opposite trade to the correctness suite: a single session loop drives
everything, the app lifespan runs once (real Redis + scheduler), the DB is
seeded once plus extra rooms 301–312, and tests partition rooms instead of
truncating. Sync tests drive the loop with `run(loop, coro)`.

| Test | Locks in |
|---|---|
| concurrent holds, one room × 20 | exactly one 201, rest 409, zero 500s |
| concurrent bookings, one hold × 15 | only 201/409, never 500 (over-count possible: the known PROCESSING overlap race) |
| concurrent offline pays × 10 | one 201 + nine 409s, exactly one `Payment` (replay is 409 today, not idempotent) |
| webhook retry storm × 10 | one `confirmed` + nine `duplicate`, exactly one `Payment` |
| stream under write | live subscriber receives the check-in delta |
| expired hold | 410, nothing created |

Bugs this suite caught on its first run:

4. **Concurrent duplicate webhooks 500'd** — two identical deliveries both
   passed the `ProcessedEvent` pre-check, then both `INSERT`ed: second died
   on `processed_events_pkey`. Fixed with `_record_event()`
   (`payments/service.py`): the insert is the arbiter, loser answers
   `"duplicate"` (HTTP 200). Same helper now guards the ignored/orphan/
   confirmed paths and the hold-gone path.

## Deliberate simplifications

- **Rate limiting disabled** (`limiter.enabled = False` in `conftest.py`): login is
  `5/minute` and register `10/hour`, which a suite trips immediately. Re-enable
  per-test if you ever want to assert 429s.
- **No lifespan in correctness tests**: the `AsyncClient` is used without
  lifespan, so the APScheduler sweeper never starts and the engine is never
  disposed mid-suite. (The realism suite opts into lifespan deliberately.)
- **No live pay-flow test**: `pay_booking` shells out to the mock provider
  against hardcoded `http://127.0.0.1:8000/...`; nothing listens there
  in-process. The webhook tests above cover the confirmation logic; exercise
  `POST /payments/pay/{id}` manually against a running server.
- **Shared dev DB**: tests truncate `users/rooms/room_types/bookings/holds/
  room_nights/payments/processed_events`. For full isolation later, add a
  `naijastay_test` database + `dependency_overrides[get_session]` in `conftest.py`.

## Adding a test (pattern)

```python
pytestmark = pytest.mark.anyio  # or per-test @pytest.mark.anyio

async def test_something(client, guest_headers):
    resp = await client.get("/api/v1/rooms/", headers=guest_headers)
    assert resp.status_code == 200
```

Need another role? Use `receptionist_headers` / `manager_headers` fixtures.
Need DB state? `await tests.helpers.create_hold / create_booking / count`.
Need a webhook event? Build with `helpers.make_event(...)`, serialize with
`helpers.encode_event(...)`, sign with `helpers.sign_raw(raw)`.
Costly setup used by every test (hashes, static fixtures)? Session scope it
in `conftest.py` — but only loop-free values; loop-bound clients stay
per-test under anyio's per-test loop.

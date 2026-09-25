# NaijaStay: Project Manual

A hotel booking API. Guests hold rooms, book them, pay, check in, check out.
Staff clean rooms so they can sell again. We built it with FastAPI, Postgres, and Redis.

This file is a learning manual. It explains what the system does, the patterns
behind it, and what broke along the way. For endpoint details, open `/docs`
on a running server. Swagger shows live examples for every query.

## Run It

You need Docker running, or Python with `uv` for host side runs.

```bash
# Start everything (database, cache, API on http://localhost:8000)
docker compose up -d --build

# Or run the API on your machine (needs Postgres and Redis up)
make dev

# Check the API is alive
curl http://localhost:8000/health
```

Seed demo data (only when you want a fresh start, because it wipes first):

```bash
make migrate
make seed        # asks first; use make seed-yes to skip the prompt
```

Demo logins (all use password `Password123!`):

| Who | Email | For |
|---|---|---|
| Guest Adaeze | `adaeze.okafor@example.ng` | booking, paying |
| Guest Tunde | `tunde.bakare@example.ng` | booking, paying |
| Front desk | `frontdesk.lagos@naijastay.ng` | check in, check out, offline pay |
| Manager | `manager.ade@naijastay.ng` | staff accounts, room types |
| Housekeeping | `housekeep.funke@naijastay.ng` | marking rooms clean |

One side note on seeding. Seed wipes tables before it fills them, and plain
restarts never seed. `SEED_ON_BOOT` stays `"false"` in compose for this reason.
Turn it on only for a fresh demo database, then turn it back off.

One side note on addresses. Your `.env` points at `localhost` for local runs.
Inside Docker, the same settings point at service names (`postgres`, `redis`).
Same database, different hostname per context. This is normal Compose behavior.

Run tests with:

```bash
uv run pytest -q
```

One side note on tests. Tests share your dev database and wipe it per test.
Seed after testing, not before. A separate test database is still open work.

## The Journey of a Booking

Follow one room from free to sellable again. Every concept appears exactly
when the story needs it.

**Hold.** A guest holds a room for 10 minutes with `POST /holds/{room_id}`.
One room holds one guest at a time. The hold expires on its own if unused.

**Book.** The guest books with room, dates, and (for staff bookings) the guest
email: `POST /bookings/`. Guests booking for themselves send no email. The
system reads it from their login. Receptionists booking for someone else must
send it. Checkout must be after check in, and check in cannot be in the past.

**Pay.** Three paths lead to confirmed. Online pay runs the mock provider and
confirms through a signed webhook. Offline pay lets front desk record cash with
the exact amount and no hold needed. The webhook path verifies the signature
first, confirms once, and safely ignores retries and unknown references.

**Stay.** Check in only on arrival day and only for confirmed bookings.
Check out only on departure day. Same day in and out is not possible,
because every stay lasts at least one night.

**Clean.** Check out leaves the room dirty and unsellable. Housekeeping marks
it clean with `PATCH /rooms/{room_id}/clean`. Only then can you sell it again.

**How the API talks back.** Success responses share one shape with a past
tense message, for example `"Booking created."` or `"Guest checked in."`
Repeated actions answer 200 with plain words like `"Guest already checked
out."` instead of errors, because real clients retry. Three endpoints stay
outside this shape for good reasons: login follows the login standard so docs
page logins keep working, webhooks speak a fixed machine vocabulary, and the
live stream is a stream, not a response.

**Time.** All date rules use UTC through one shared helper. A booking date
means the same thing on every machine. Future frontends will handle display
in local time.

## Patterns We Settled On

**Domain folders.** Each area (auth, rooms, bookings, payments, users) owns
its routes, logic, and data shapes. Logic functions never touch HTTP or Redis.
Routes handle that layer. This split is why later fixes stayed small.

**Database keys as business rules.** We enforce some rules in the database itself,
where no race condition can dodge them. One hold per room (the hold key is the
room). One row per room night (a night cannot sell twice, the database refuses
before our code even decides). One payment per booking (a double pay dies on
the unique key, then our code turns it into clear words). When two requests
race, the keys decide correctly every time.

**Cheap checks before irreversible ones.** Check dates and holds before you
write anything. Move money and flip statuses last, inside one commit. Overlap
checks reject double booking attempts. Key clashes catch the races that slip
past the checks.

**Side effects never fail a response.** Treat live dashboard events and cache
writes as best effort. If Redis is down, the guest's booking still succeeds and
the dashboard catches up. Short expiry times bound any staleness.

**Cache reads, expire writes.** The room list caches for 30 seconds and room
search for 60. A missed read queries Postgres and stores the answer with an
expiry. State changes clear the room list notes right away. Search notes and
background sweeper changes heal by expiry instead. Short lifetimes bound any
staleness, so a missed clear costs seconds, never correctness.

## Things That Broke Us

**Paid bookings could not check in.** Payment flipped a flag that check in
requires, so every paid booking failed check in. We removed the flip from
payment and left flag writes to check in, check out, and cleaning. Search
kept working because booking dates already exclude paid rooms for their
dates. We added one end to end test so the break never hides again.

**Failed payments answered 200.** The pay endpoint trusted the provider script
instead of reading the booking afterward. Now it reads the final state and
answers 409 honestly when the booking was cancelled mid flight.

**Docs page login looped forever.** Wrapping the login response broke the
standard login handshake, so the authorize button never worked. Login stays
standard shaped, noted as the exception.

**Midnight broke date logic.** Local and server clocks disagreed on what day
it is for one hour daily. One shared clock helper fixed it everywhere.

**Room reads validated twice per hit.** Building the response adapter inside
the route rebuilt its schema on every request, then the response model
validated the same rows again on the way out. We moved both adapters module
wide (`_ROOMS_ADAPTER`, `_SEARCH_ADAPTER`) so they compile once on import,
and the two cached reads return raw JSON so the rows validate exactly once
per cache miss, never per hit.

## Still Open

Separate test database so suites stop wiping dev data. Real payment provider
(the mock ships in the image, marked for removal). Health checks that verify
the database, not just the process. Live stream events for cleaning and room
type changes. Envelope shape for the two cached room reads. API versioning
so clients can pin a contract (only the webhook is versioned today).

## The API at a Glance

Endpoints group by area. Swagger on a running server shows examples for every
query and remains the full reference. This table only orients you.

| Area | Endpoints | Who |
|---|---|---|
| Auth | register, login | open |
| Users | my profile, create/disable/enable staff | self, manager only for staff |
| Holds | hold a room | guests |
| Bookings | create, check in, check out | guests or front desk to create; front desk for stay moves |
| Payments | online pay, offline pay, provider webhook | guests, front desk, provider |
| Rooms | list, available, search, occupancy, clean, room types, live stream | mixed; stream and health need no login |

Requests pass three layers before reaching any endpoint. CORS answers browser
rules first. Rate limiting counts next: tight budgets on login, register, and
pay; webhooks, the live stream, and health checks stay exempt so automation
never trips them. A timing middleware then stamps every request with an ID,
measures it, and logs it (health probes stay quiet by design). Over limit
requests get a 429 with a retry hint from a custom handler.

## Quick Reference

```bash
# Hold, book, pay, check in (replace TOKEN with a guest login token).
# Dates are computed relative to today so the example never goes stale.
IN=$(date -v+7d +%F 2>/dev/null || date -d "+7 days" +%F)
OUT=$(date -v+9d +%F 2>/dev/null || date -d "+9 days" +%F)
curl -X POST http://localhost:8000/holds/102 -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/bookings/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"room_id\":102,\"check_in\":\"$IN\",\"check_out\":\"$OUT\"}"
curl -X POST http://localhost:8000/payments/pay/1 -H "Authorization: Bearer $TOKEN"

# Watch live room events (blocks, prints each event as it lands)
curl -N http://localhost:8000/rooms/stream

# Tests and migrations through the makefile (run `make` alone to list all)
make test
make migrate
make makemigration m="add x"
```

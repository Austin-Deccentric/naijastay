"""Realism suite: one loop + lifespan on, concurrent clients, seeded-once DB.

Each test owns distinct rooms (301-306) so tests can't talk through shared
rows. Assertions lock the contract, not the race outcome: every response
must be an expected status (never 500), exactly-once effects exactly once.
"""

import asyncio
from datetime import timedelta

from app.core.time import utc_today
from app.domains.bookings.models import BookingStatus
from app.domains.rooms import streaming as stream
from app.integrations.redis import create_redis
from tests import helpers
from tests.realism.conftest import run

CHECK_IN = utc_today() + timedelta(days=7)
CHECK_OUT = utc_today() + timedelta(days=9)


def _statuses(responses):
    return [r.status_code for r in responses]


def test_concurrent_holds_one_winner(live_ctx):
    """20 racers, one room: exactly one 201, rest 409, zero 500s."""
    loop, client, guest = live_ctx["loop"], live_ctx["client"], live_ctx["guest"]

    async def _race():
        return await asyncio.gather(*[
            client.post("/api/v1/holds/301", headers=guest) for _ in range(20)
        ])

    codes = _statuses(run(loop, _race()))
    assert set(codes) <= {201, 409}, codes
    assert codes.count(201) == 1, codes


def test_concurrent_bookings_no_500(live_ctx):
    """15 racers, one hold, same dates: only 201/409, never 500.

    More than one 201 is possible (PROCESSING writes no RoomNights yet --
    the known overlap race); this locks the no-500 contract, not the count.
    """
    loop, client, guest = live_ctx["loop"], live_ctx["client"], live_ctx["guest"]
    run(loop, helpers.create_hold(302, helpers.GUEST_1))
    body = {"room_id": 302, "check_in": CHECK_IN.isoformat(),
            "check_out": CHECK_OUT.isoformat()}

    async def _race():
        return await asyncio.gather(*[
            client.post("/api/v1/bookings/", json=body, headers=guest)
            for _ in range(15)
        ])

    codes = _statuses(run(loop, _race()))
    assert set(codes) <= {201, 409}, codes
    assert 500 not in codes


def test_concurrent_offline_pay_single_payment(live_ctx):
    """10 staff taps, one booking: one 201 + nine 409s, exactly one Payment.

    (Replay answers 409 today -- the known non-idempotent gap. If offline
    pay ever becomes idempotent like online pay, flip the 409s to 200s.)
    """
    loop, client, rec = live_ctx["loop"], live_ctx["client"], live_ctx["receptionist"]
    run(loop, helpers.create_hold(303, helpers.GUEST_1))
    created = run(loop, helpers.create_booking(
        helpers.GUEST_1, 303, CHECK_IN, CHECK_OUT, BookingStatus.PROCESSING, 70000.0))

    async def _race():
        return await asyncio.gather(*[
            client.post(f"/api/v1/payments/offline/{created['booking_id']}",
                        json={"amount": 70000.0, "currency": "NGN"}, headers=rec)
            for _ in range(10)
        ])

    codes = _statuses(run(loop, _race()))
    assert codes.count(201) == 1, codes
    assert set(codes) <= {201, 409}, codes
    assert run(loop, helpers.count(
        "payments", f"WHERE booking_id = {created['booking_id']}")) == 1


def test_webhook_retry_storm_confirms_once(live_ctx):
    """10 concurrent identical deliveries: one confirmed, rest duplicate."""
    loop, client = live_ctx["loop"], live_ctx["client"]
    run(loop, helpers.create_hold(304, helpers.GUEST_1))
    created = run(loop, helpers.create_booking(
        helpers.GUEST_1, 304, CHECK_IN, CHECK_OUT, BookingStatus.PROCESSING, 130000.0))
    raw = helpers.encode_event(helpers.make_event(
        event_id="evt_storm_001", reference=created["ref"], amount=created["total"]))
    sig = helpers.sign_raw(raw)

    async def _storm():
        return await asyncio.gather(*[
            client.post("/api/v1/webhooks/payment", content=raw,
                        headers={"X-Signature": sig}) for _ in range(10)
        ])

    resps = run(loop, _storm())
    assert all(r.status_code == 200 for r in resps), [r.text for r in resps]
    outcomes = sorted(r.json()["status"] for r in resps)
    assert outcomes.count("confirmed") == 1, outcomes
    assert set(outcomes) <= {"confirmed", "duplicate"}, outcomes
    assert run(loop, helpers.count(
        "payments", f"WHERE booking_id = {created['booking_id']}")) == 1


def test_stream_receives_write_delta(live_ctx):
    """A live subscriber sees the check-in delta for room 305."""
    loop, client, rec = live_ctx["loop"], live_ctx["client"], live_ctx["receptionist"]
    today = utc_today()
    created = run(loop, helpers.create_booking(
        helpers.GUEST_1, 305, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 130000.0))

    async def _watch():
        sub = create_redis()
        ps = sub.pubsub()
        try:
            await ps.subscribe(stream.CHANNEL)
            await asyncio.sleep(0.2)
            resp = await client.post(
                f"/api/v1/bookings/{created['booking_id']}/check-in", headers=rec)
            assert resp.status_code == 200, resp.text
            end = loop.time() + 3.0
            while loop.time() < end:
                msg = await ps.get_message(ignore_subscribe_messages=True, timeout=0.2)
                if msg is not None and msg.get("type") == "message":
                    return msg["data"]
            return None
        finally:
            await ps.aclose()
            await sub.aclose()

    import json

    data = run(loop, _watch())
    assert data is not None, "no room_status delta within 3s"
    assert json.loads(data)["room_id"] == 305


def test_expired_hold_rejected_live(live_ctx):
    """A hold born expired answers 410 and creates nothing."""
    loop, client, guest = live_ctx["loop"], live_ctx["client"], live_ctx["guest"]
    run(loop, helpers.create_hold(306, helpers.GUEST_1, minutes=-5))
    body = {"room_id": 306, "check_in": CHECK_IN.isoformat(),
            "check_out": CHECK_OUT.isoformat()}

    async def _book():
        return await client.post("/api/v1/bookings/", json=body, headers=guest)

    resp = run(loop, _book())
    assert resp.status_code == 410, resp.text
    assert run(loop, helpers.count(
        "bookings", "WHERE room_id = 306")) == 0

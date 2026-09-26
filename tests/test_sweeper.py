"""Stale-PROCESSING sweeper tests.

`cancel_stale_processing` cancels (never deletes) abandoned PROCESSING
bookings: older than ``grace_minutes + HOLD_TIME`` (default 3 + 10 = 13 min),
or with a past check-in. The booking's own hold is freed; another guest's
hold is never touched.
"""

from datetime import timedelta

import pytest

pytestmark = pytest.mark.anyio

from app.core.time import utc_today
from app.domains.bookings.models import BookingStatus
from app.domains.bookings.sweeps import cancel_stale_processing, delete_expired_holds
from tests import helpers


async def _processing(room_id: int = 201, guest: str = helpers.GUEST_1,
                check_in: date | None = None, nights: int = 2) -> dict:
    check_in = check_in or (utc_today() + timedelta(days=7))
    return await helpers.create_booking(
        guest, room_id, check_in, check_in + timedelta(days=nights),
        BookingStatus.PROCESSING, 130000.0,
    )


async def test_stale_by_age_cancelled_and_hold_freed(client):
    created = await _processing()
    await helpers.create_hold(201, helpers.GUEST_1)
    await helpers.backdate_booking(created["booking_id"], minutes_ago=15)
    assert await (cancel_stale_processing()) == 1
    assert await helpers.get_booking_status(created["booking_id"]) == "cancelled"
    assert await helpers.count("holds", "WHERE room_id = 201") == 0
    # Row preserved for audit, not deleted.
    assert await helpers.count("bookings", f"WHERE booking_id = {created['booking_id']}") == 1


async def test_fresh_processing_untouched(client):
    created = await _processing()
    await helpers.create_hold(201, helpers.GUEST_1)
    assert await (cancel_stale_processing()) == 0
    assert await helpers.get_booking_status(created["booking_id"]) == "processing"
    assert await helpers.count("holds", "WHERE room_id = 201") == 1


async def test_confirmed_untouched(client):
    today = utc_today()
    created = await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    await helpers.backdate_booking(created["booking_id"], minutes_ago=120)
    assert await (cancel_stale_processing()) == 0
    assert await helpers.get_booking_status(created["booking_id"]) == "confirmed"


async def test_past_check_in_cancelled_even_if_fresh(client):
    # Two days back (not one): belt-and-braces alongside the shared
    # utc_today() clock, so this stays green at any wall-clock time.
    check_in = utc_today() - timedelta(days=2)
    created = await _processing(check_in=check_in)
    assert await (cancel_stale_processing()) == 1
    assert await helpers.get_booking_status(created["booking_id"]) == "cancelled"


async def test_other_guest_hold_preserved(client):
    created = await _processing()  # guest1's booking on room 201
    await helpers.create_hold(201, helpers.GUEST_2)  # guest2's newer hold
    await helpers.backdate_booking(created["booking_id"], minutes_ago=15)
    assert await (cancel_stale_processing()) == 1
    assert await helpers.get_booking_status(created["booking_id"]) == "cancelled"
    assert await helpers.count("holds", "WHERE room_id = 201") == 1


async def test_custom_grace_minutes(client):
    created = await _processing()
    await helpers.backdate_booking(created["booking_id"], minutes_ago=15)
    assert await (cancel_stale_processing(grace_minutes=30)) == 0
    assert await (cancel_stale_processing(grace_minutes=3)) == 1


async def test_hold_window_included_in_cutoff(client):
    # 10 min old exceeds grace_minutes=3 alone, but the effective cutoff is
    # grace_minutes + HOLD_TIME (3 + 10 = 13), so this booking survives.
    created = await _processing()
    await helpers.backdate_booking(created["booking_id"], minutes_ago=10)
    assert await (cancel_stale_processing(grace_minutes=3)) == 0
    assert await helpers.get_booking_status(created["booking_id"]) == "processing"


async def test_room_searchable_after_sweep(client, guest_headers):
    created = await _processing()
    check_in = (utc_today() + timedelta(days=7)).isoformat()
    check_out = (utc_today() + timedelta(days=9)).isoformat()
    params = {"check_in": check_in, "check_out": check_out, "room_type": "deluxe"}
    before = await client.get("/api/v1/rooms/search", params=params, headers=guest_headers)
    assert before.status_code == 200, before.text
    assert all(r["id"] != 201 for r in before.json())
    await helpers.backdate_booking(created["booking_id"], minutes_ago=15)
    assert await (cancel_stale_processing()) == 1
    # Known gap (app/integrations/cache.py): the sweeper has no Redis access,
    # so rooms:search:* heals by 60s TTL, not by invalidation. Expire it here
    # so this test asserts sweep correctness, not cache TTL.
    from app.integrations.cache import invalidate_prefix
    from app.main import app as _app

    await invalidate_prefix(_app.state.redis, "rooms:search:")
    after = await client.get("/api/v1/rooms/search", params=params, headers=guest_headers)
    assert after.status_code == 200, after.text
    assert any(r["id"] == 201 for r in after.json())


async def test_hold_sweeper_still_works(client):
    await helpers.create_hold(202, helpers.GUEST_2, minutes=-60)  # already expired
    assert await (delete_expired_holds()) == 1
    assert await helpers.count("holds", "WHERE room_id = 202") == 0

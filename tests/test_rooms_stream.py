"""Dashboard stream (SSE) tests — real redis, per plan.

Requires `docker compose up -d redis`. Redis-dependent tests skip
gracefully when unreachable so CI without redis stays green.
"""

import asyncio
import json

import pytest

from app.domains.rooms import streaming as m
from app.domains.rooms.models import Room
from app.domains.rooms.schemas import RoomDashboardRead
from app.main import app

pytestmark = [pytest.mark.redis, pytest.mark.anyio]


async def _needs_redis():
    """Skip unless the real docker redis answers. Awaited (no fresh loop)."""
    from redis import asyncio as aioredis

    c = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
    try:
        await c.ping()
    except Exception:
        pytest.skip("redis unreachable — start with: docker compose up -d redis")
    finally:
        await c.aclose()


def _loop_client():
    from app.integrations.redis import create_redis

    return create_redis()


async def _poll(pubsub, timeout=3.0):
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if msg is not None and msg.get("type") == "message":
            return msg
        await asyncio.sleep(0.05)
    return None


async def test_payload_shape_has_room_id_and_no_guest_data():
    room = Room(id=101, room_type="standard", is_available=True, room_state="clean")
    payload = m.room_status_payload(room)
    body = json.loads(payload)
    assert body["room_id"] == 101
    assert "guest" not in payload.lower()
    assert RoomDashboardRead.model_validate(room, from_attributes=True).room_id == 101


@pytest.mark.anyio
async def test_publish_round_trip():
    await _needs_redis()

    sub = _loop_client()
    pub = _loop_client()
    ps = sub.pubsub()
    try:
        await ps.subscribe(m.CHANNEL)
        await asyncio.sleep(0.2)
        room = Room(id=102, room_type="standard", is_available=True, room_state="dirty")
        ok = await m.publish_room_status(pub, room)
        msg = await _poll(ps)
    finally:
        await ps.aclose()
        await sub.aclose()
        await pub.aclose()
    assert ok is True
    assert msg is not None
    assert json.loads(msg["data"])["room_id"] == 102


@pytest.mark.anyio
async def test_publish_without_subscriber_returns_false():
    await _needs_redis()

    pub = _loop_client()
    try:
        room = Room(id=102, room_type="standard", is_available=True, room_state="clean")
        assert await m.publish_room_status(pub, room) is False
    finally:
        await pub.aclose()


@pytest.mark.anyio
async def test_generator_yields_and_disconnects():
    await _needs_redis()

    sub = _loop_client()
    pub = _loop_client()
    received = []

    class Req:
        def __init__(self):
            self.done = False

        async def is_disconnected(self):
            return self.done

    req = Req()

    async def _feed():
        await asyncio.sleep(0.3)
        room = Room(id=201, room_type="deluxe", is_available=True, room_state="clean")
        await m.publish_room_status(pub, room)
        await asyncio.sleep(0.5)
        req.done = True

    task = asyncio.create_task(_feed())
    try:
        async for event in m.room_event_generator(sub, req):
            assert event["event"] == "room_status"
            received.append(event)
            if received:
                req.done = True
                break
    finally:
        await task
        await sub.aclose()
        await pub.aclose()
    assert len(received) == 1


async def test_stream_endpoint_no_redis_fallback(client, manager_headers):
    app.state.redis = None
    resp = await client.get("/api/v1/rooms/stream", headers=manager_headers)
    assert resp.status_code == 200, resp.text
    assert "live updates unavailable" in resp.text


@pytest.mark.anyio
async def test_stream_endpoint_with_redis_returns_sse(client):
    """Locks transport: with redis attached the endpoint returns an SSE
    response (not the unavailable fallback). Body is infinite by design,
    so assert on the response object without consuming the stream."""
    from tests import helpers as _helpers

    await _needs_redis()
    from sse_starlette.sse import EventSourceResponse

    from app.domains.rooms.router import stream_rooms
    from app.domains.users.models import User, UserRole

    scope = {"type": "http", "app": app}
    req = __import__("starlette.requests", fromlist=["Request"]).Request(scope)
    manager = User(
        email=_helpers.MANAGER, password_hash="x", role=UserRole.MANAGER, is_active=True
    )

    resp = await stream_rooms(req, manager)
    assert isinstance(resp, EventSourceResponse)


async def test_router_publishes_on_checkin_and_offline(
    client, receptionist_headers, monkeypatch
):
    from datetime import timedelta

    from app.core.time import utc_today
    from app.domains.bookings.models import BookingStatus
    from tests import helpers

    calls = []

    async def _spy(request, session, room_id):
        calls.append(room_id)

    monkeypatch.setattr("app.domains.bookings.router.publish_booking_room", _spy)
    monkeypatch.setattr("app.domains.payments.router.publish_booking_room", _spy)

    today = utc_today()
    created = await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    assert (
        await client.post(
            f"/api/v1/bookings/{created['booking_id']}/check-in", headers=receptionist_headers
        )
        ).status_code == 200
    assert 101 in calls

    created2 = await helpers.create_booking(
        helpers.GUEST_1, 102, today, today + timedelta(days=2),
        BookingStatus.PROCESSING, 70000.0,
    )
    resp = await client.post(
        f"/api/v1/payments/offline/{created2['booking_id']}",
        json={"amount": 70000.0, "currency": "NGN"},
        headers=receptionist_headers,
    )
    assert resp.status_code == 201, resp.text
    assert 102 in calls

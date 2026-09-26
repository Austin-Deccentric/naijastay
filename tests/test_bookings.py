"""Hold / booking / check-in tests via TestClient."""

from datetime import timedelta

import pytest

pytestmark = pytest.mark.anyio

from app.core.time import utc_today
from app.domains.bookings.models import BookingStatus
from tests import helpers


async def test_guest_can_hold_room(client, guest_headers):
    resp = await client.post("/api/v1/holds/102", headers=guest_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["room_id"] == 102


async def test_hold_unavailable_room_returns_400(client, guest_headers):
    assert (await client.post("/api/v1/holds/105", headers=guest_headers)).status_code == 400


async def test_hold_missing_room_returns_404(client, guest_headers):
    assert (await client.post("/api/v1/holds/9999", headers=guest_headers)).status_code == 404


async def test_receptionist_cannot_hold(client, receptionist_headers):
    assert (await client.post("/api/v1/holds/102", headers=receptionist_headers)).status_code == 403


async def test_booking_with_active_hold_returns_201(client, guest_headers):
    await helpers.create_hold(201, helpers.GUEST_1)
    check_in = (utc_today() + timedelta(days=7)).isoformat()
    check_out = (utc_today() + timedelta(days=9)).isoformat()
    resp = await client.post(
        "/api/v1/bookings/",
        json={"room_id": 201, "check_in": check_in, "check_out": check_out},
        headers=guest_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["room_id"] == 201


async def test_booking_without_hold_returns_409(client, guest_headers):
    check_in = (utc_today() + timedelta(days=7)).isoformat()
    check_out = (utc_today() + timedelta(days=9)).isoformat()
    resp = await client.post(
        "/api/v1/bookings/",
        json={"room_id": 102, "check_in": check_in, "check_out": check_out},
        headers=guest_headers,
    )
    assert resp.status_code == 409, resp.text


async def test_booking_bad_dates_returns_422(client, guest_headers):
    today = utc_today().isoformat()
    resp = await client.post(
        "/api/v1/bookings/",
        json={"room_id": 102, "check_in": today, "check_out": today},
        headers=guest_headers,
    )
    assert resp.status_code == 422


async def test_receptionist_check_in_confirmed_today_booking(client, receptionist_headers):
    today = utc_today()
    created = await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    resp = await client.post(f"/api/v1/bookings/{created['booking_id']}/check-in", headers=receptionist_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["booking_id"] == created["booking_id"]


async def test_guest_cannot_check_in(client, guest_headers):
    today = utc_today()
    created = await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    resp = await client.post(f"/api/v1/bookings/{created['booking_id']}/check-in", headers=guest_headers)
    assert resp.status_code == 403


async def test_check_in_non_confirmed_returns_409(client, receptionist_headers):
    today = utc_today()
    created = await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.PROCESSING, 70000.0,
    )
    resp = await client.post(f"/api/v1/bookings/{created['booking_id']}/check-in", headers=receptionist_headers)
    assert resp.status_code == 409

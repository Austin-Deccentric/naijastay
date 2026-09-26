"""Housekeeping/occupancy/room-type tests — locks current behaviour."""

from datetime import timedelta

import pytest

pytestmark = pytest.mark.anyio

from app.core.time import utc_today
from app.domains.bookings.models import BookingStatus
from tests import helpers


async def test_mark_dirty_clean_200(client, housekeeper_headers):
    await helpers.set_room_state(101, "dirty")
    assert (await client.patch("/api/v1/rooms/101/clean", headers=housekeeper_headers)).status_code == 200


async def test_mark_already_clean_returns_200(client, housekeeper_headers):
    """Current: idempotent no-op success, NOT 409 (guard commented out)."""
    await helpers.set_room_state(101, "clean")
    assert (await client.patch("/api/v1/rooms/101/clean", headers=housekeeper_headers)).status_code == 200


async def test_mark_clean_missing_404(client, housekeeper_headers):
    assert (
        (await client.patch("/api/v1/rooms/9999/clean", headers=housekeeper_headers)).status_code == 404
    )


async def test_guest_cannot_mark_clean_403(client, guest_headers):
    assert (await client.patch("/api/v1/rooms/101/clean", headers=guest_headers)).status_code == 403


async def test_occupancy_counts_only_checked_in(client, manager_headers):
    """COMPLETED/CONFIRMED/PROCESSING/CANCELLED overlapping report_date are
    NOT counted; available = total - occupied so includes dirty rooms."""
    today = utc_today()
    await helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CHECKED_IN, 70000.0,
    )
    await helpers.create_booking(
        helpers.GUEST_2, 102, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    await helpers.create_booking(
        helpers.GUEST_2, 201, today, today + timedelta(days=2),
        BookingStatus.COMPLETED, 65000.0,
    )
    resp = await client.get(
        "/api/v1/rooms/occupancy",
        params={"report_date": today.isoformat()},
        headers=manager_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["occupied_rooms"] == 1
    assert body["data"]["available_rooms"] == body["data"]["total_rooms"] - 1


async def test_guest_cannot_view_occupancy_403(client, guest_headers):
    assert (
        await client.get(
            "/api/v1/rooms/occupancy",
            params={"report_date": utc_today().isoformat()},
            headers=guest_headers,
        )
        ).status_code == 403


async def test_manager_patches_rate_200(client, manager_headers):
    resp = await client.patch(
        "/api/v1/rooms/room-types/standard", json={"base_rate": 40000}, headers=manager_headers
    )
    assert resp.status_code == 200, resp.text


async def test_patch_room_type_empty_422(client, manager_headers):
    assert (
        await client.patch("/api/v1/rooms/room-types/standard", json={}, headers=manager_headers)
    ).status_code == 422


async def test_patch_room_type_missing_404(client, manager_headers):
    assert (
        await client.patch(
            "/api/v1/rooms/room-types/nope", json={"base_rate": 1}, headers=manager_headers
        )
        ).status_code == 404

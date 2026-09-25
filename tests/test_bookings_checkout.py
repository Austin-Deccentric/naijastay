"""Checkout tests — locks current behaviour: dirty+unavailable, repeat=200."""

from datetime import timedelta

from app.core.time import utc_today
from app.domains.bookings.models import BookingStatus
from tests import helpers


def _checked_in(room=101, checkout_today=True):
    today = utc_today()
    created = helpers.create_booking(
        helpers.GUEST_1,
        room,
        today - timedelta(days=1),
        today if checkout_today else today + timedelta(days=2),
        BookingStatus.CHECKED_IN,
        35000.0,
    )
    # A checked-in guest physically occupies the room.
    helpers.set_room_availability(room, False)
    return created


def test_receptionist_checkout_happy(client, receptionist_headers):
    created = _checked_in()
    resp = client.post(
        f"/bookings/{created['booking_id']}/check-out", headers=receptionist_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["message"] == "Guest checked out."
    assert body["data"]["booking_status"] == "completed"
    assert body["data"]["room_available"] is False
    assert body["data"]["room_state"] == "dirty"
    assert helpers.get_booking_status(created["booking_id"]) == "completed"


def test_checkout_missing_404(client, receptionist_headers):
    assert (
        client.post("/bookings/999999/check-out", headers=receptionist_headers).status_code
        == 404
    )


def test_checkout_confirmed_not_checked_in_409(client, receptionist_headers):
    today = utc_today()
    created = helpers.create_booking(
        helpers.GUEST_1,
        101,
        today,
        today + timedelta(days=2),
        BookingStatus.CONFIRMED,
        70000.0,
    )
    assert (
        client.post(
            f"/bookings/{created['booking_id']}/check-out", headers=receptionist_headers
        ).status_code
        == 409
    )


def test_checkout_wrong_date_422(client, receptionist_headers):
    created = _checked_in(checkout_today=False)
    assert (
        client.post(
            f"/bookings/{created['booking_id']}/check-out", headers=receptionist_headers
        ).status_code
        == 422
    )


def test_guest_cannot_checkout_403(client, guest_headers):
    created = _checked_in()
    assert (
        client.post(
            f"/bookings/{created['booking_id']}/check-out", headers=guest_headers
        ).status_code
        == 403
    )


def test_repeat_checkout_idempotent_200(client, receptionist_headers):
    """Repeat checkout is a no-op success with a distinct message."""
    created = _checked_in()
    url = f"/bookings/{created['booking_id']}/check-out"
    assert client.post(url, headers=receptionist_headers).status_code == 200
    repeat = client.post(url, headers=receptionist_headers)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["message"] == "Guest already checked out."
    assert repeat.json()["data"]["booking_status"] == "completed"


def test_checkout_then_clean_makes_available(
    client, receptionist_headers, housekeeper_headers
):
    created = _checked_in(room=102)
    assert (
        client.post(
            f"/bookings/{created['booking_id']}/check-out", headers=receptionist_headers
        ).status_code
        == 200
    )
    resp = client.patch("/rooms/102/clean", headers=housekeeper_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_available"] is True

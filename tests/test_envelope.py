"""Envelope contract tests: every wrapped success response is
{status, message, data} with status == "success", including the
idempotent-replay messages for repeat check-out and already-clean rooms."""

from datetime import timedelta

from app.domains.bookings.models import BookingStatus
from app.core.time import utc_today
from tests import helpers


def _envelope(resp, *, status_code=200):
    assert resp.status_code == status_code, resp.text
    body = resp.json()
    assert set(body.keys()) == {"status", "message", "data"}, body.keys()
    assert body["status"] == "success"
    assert isinstance(body["message"], str) and body["message"]
    return body


def test_register_envelope_shape(client):
    body = _envelope(
        client.post(
            "/auth/register",
            json={"email": "env.guest@example.ng", "password": "Password123!"},
        ),
        status_code=201,
    )
    assert body["message"] == "Guest registered."
    assert body["data"]["email"] == "env.guest@example.ng"


def test_login_stays_bare_for_oauth2_clients(client):
    """POST /auth/login is exempt from the envelope: the OAuth2 password
    flow (e.g. Swagger UI Authorize) requires top-level access_token."""
    resp = client.post(
        "/auth/login",
        data={"username": helpers.GUEST_1, "password": helpers.PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"access_token", "token_type", "user"}, body.keys()
    assert body["access_token"]


def test_hold_and_book_envelope_messages(client, guest_headers):
    hold = _envelope(client.post("/holds/102", headers=guest_headers), status_code=201)
    assert hold["message"] == "Room held."
    assert hold["data"]["room_id"] == 102

    helpers.create_hold(201, helpers.GUEST_1)
    check_in = (utc_today() + timedelta(days=7)).isoformat()
    check_out = (utc_today() + timedelta(days=9)).isoformat()
    book = _envelope(
        client.post(
            "/bookings/",
            json={"room_id": 201, "check_in": check_in, "check_out": check_out},
            headers=guest_headers,
        ),
        status_code=201,
    )
    assert book["message"] == "Booking created."
    assert book["data"]["room_id"] == 201


def test_check_in_envelope_message(client, receptionist_headers):
    today = utc_today()
    created = helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    body = _envelope(
        client.post(
            f"/bookings/{created['booking_id']}/check-in",
            headers=receptionist_headers,
        )
    )
    assert body["message"] == "Guest checked in."
    assert body["data"]["booking_id"] == created["booking_id"]


def test_repeat_checkout_idempotent_message(client, receptionist_headers):
    today = utc_today()
    created = helpers.create_booking(
        helpers.GUEST_1, 101, today - timedelta(days=1), today,
        BookingStatus.CHECKED_IN, 35000.0,
    )
    helpers.set_room_availability(101, False)
    url = f"/bookings/{created['booking_id']}/check-out"
    first = _envelope(client.post(url, headers=receptionist_headers))
    assert first["message"] == "Guest checked out."
    repeat = _envelope(client.post(url, headers=receptionist_headers))
    assert repeat["message"] == "Guest already checked out."
    assert repeat["data"]["booking_status"] == "completed"


def test_already_clean_idempotent_message(client, manager_headers):
    email = "env.keep@naijastay.ng"
    assert (
        client.post(
            "/users/staff",
            json={"email": email, "password": "Password123!", "role": "housekeeper"},
            headers=manager_headers,
        ).status_code
        == 201
    )
    login = client.post(
        "/auth/login", data={"username": email, "password": "Password123!"}
    )
    hk = {"Authorization": f"Bearer {login.json()['access_token']}"}

    helpers.set_room_state(101, "dirty")
    first = _envelope(client.patch("/rooms/101/clean", headers=hk))
    assert first["message"] == "Room marked clean."
    repeat = _envelope(client.patch("/rooms/101/clean", headers=hk))
    assert repeat["message"] == "Room already clean."
    assert repeat["data"]["is_available"] is True


def test_offline_payment_envelope_message(client, receptionist_headers):
    check_in = utc_today() + timedelta(days=7)
    check_out = utc_today() + timedelta(days=9)
    created = helpers.create_booking(
        helpers.GUEST_1, 201, check_in, check_out, BookingStatus.PROCESSING, 130000.0
    )
    body = _envelope(
        client.post(
            f"/payments/offline/{created['booking_id']}",
            json={"amount": created["total"]},
            headers=receptionist_headers,
        ),
        status_code=201,
    )
    assert body["message"] == "Offline payment recorded."
    assert body["data"]["booking_status"] == "confirmed"

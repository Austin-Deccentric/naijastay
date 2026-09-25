"""Offline (staff-recorded) payment tests via TestClient.

No hold required, exact amount only, receptionists only. Offline payments
write no ProcessedEvent row — those remain provider-only.
"""

from datetime import timedelta

from app.domains.bookings.models import BookingStatus
from app.core.time import utc_today
from tests import helpers

URL = "/payments/offline"


def _processing_booking(room_id: int = 201, guest: str = helpers.GUEST_1) -> dict:
    check_in = utc_today() + timedelta(days=7)
    check_out = utc_today() + timedelta(days=9)
    return helpers.create_booking(
        guest, room_id, check_in, check_out, BookingStatus.PROCESSING, 130000.0
    )


def test_receptionist_records_offline_payment(client, receptionist_headers):
    created = _processing_booking()
    events_before = helpers.count("processed_events")
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"]},
        headers=receptionist_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["booking_id"] == created["booking_id"]
    assert body["data"]["reference"] == created["ref"]
    assert body["data"]["booking_status"] == "confirmed"
    assert body["data"]["method"] == "offline"
    assert helpers.get_booking_status(created["booking_id"]) == "confirmed"
    assert helpers.count("payments", f"WHERE booking_id = {created['booking_id']}") == 1
    assert helpers.count("room_nights", f"WHERE booking_id = {created['booking_id']}") == 2
    # No provider event row for offline payments.
    assert helpers.count("processed_events") == events_before


def test_offline_without_hold_confirms_walk_in(client, receptionist_headers):
    # Deliberately no hold on room 102 — walk-ins are confirmable offline.
    created = _processing_booking(room_id=102)
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"]},
        headers=receptionist_headers,
    )
    assert resp.status_code == 201, resp.text
    assert helpers.get_booking_status(created["booking_id"]) == "confirmed"


def test_offline_wrong_amount_returns_422(client, receptionist_headers):
    created = _processing_booking()
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"] + 1000},
        headers=receptionist_headers,
    )
    assert resp.status_code == 422, resp.text
    assert helpers.get_booking_status(created["booking_id"]) == "processing"


def test_offline_non_processing_returns_409(client, receptionist_headers):
    today = utc_today()
    created = helpers.create_booking(
        helpers.GUEST_1, 101, today, today + timedelta(days=2),
        BookingStatus.CONFIRMED, 70000.0,
    )
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": 70000.0},
        headers=receptionist_headers,
    )
    assert resp.status_code == 409, resp.text


def test_offline_unknown_booking_returns_404(client, receptionist_headers):
    resp = client.post(
        f"{URL}/9999", json={"amount": 1000}, headers=receptionist_headers
    )
    assert resp.status_code == 404, resp.text


def test_guest_cannot_record_offline(client, guest_headers):
    created = _processing_booking()
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"]},
        headers=guest_headers,
    )
    assert resp.status_code == 403, resp.text


def test_manager_cannot_record_offline(client, manager_headers):
    created = _processing_booking()
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"]},
        headers=manager_headers,
    )
    assert resp.status_code == 403, resp.text


def test_online_then_offline_returns_409(client, receptionist_headers):
    created = _processing_booking()
    helpers.create_hold(201, helpers.GUEST_1)  # online confirm requires the hold
    event = helpers.make_event(
        event_id="evt_onoff_001", reference=created["ref"], amount=created["total"]
    )
    raw = helpers.encode_event(event)
    resp = client.post(
        "/api/v1/webhooks/payment",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": helpers.sign_raw(raw)},
    )
    assert resp.json() == {"status": "confirmed"}
    resp = client.post(
        f"{URL}/{created['booking_id']}",
        json={"amount": created["total"]},
        headers=receptionist_headers,
    )
    assert resp.status_code == 409, resp.text
    assert helpers.count("payments", f"WHERE booking_id = {created['booking_id']}") == 1

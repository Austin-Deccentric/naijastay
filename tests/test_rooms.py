"""Room listing / search tests via TestClient."""

from datetime import date, timedelta

from tests import helpers


def test_get_all_rooms_lists_seeded_rooms(client):
    resp = client.get("/rooms/")
    assert resp.status_code == 200, resp.text
    ids = {room["room_id"] for room in resp.json()}
    assert {101, 102, 201} <= ids
    assert all("room_state" in room for room in resp.json())


def test_get_all_rooms_open_without_auth(client):
    # No auth dependency by design (dashboard + SSE clients).
    assert client.get("/rooms/").status_code == 200


def test_get_all_rooms_room_state_filter(client):
    helpers.set_room_state(101, "dirty")
    clean = client.get("/rooms/", params={"room_state": "clean"})
    assert clean.status_code == 200, clean.text
    assert all(r["room_state"] == "clean" for r in clean.json())
    assert all(r["room_id"] != 101 for r in clean.json())
    dirty = client.get("/rooms/", params={"room_state": "dirty"})
    assert dirty.status_code == 200, dirty.text
    assert [r["room_id"] for r in dirty.json()] == [101]


def test_get_all_rooms_invalid_room_state_returns_422(client):
    assert client.get("/rooms/", params={"room_state": "muddy"}).status_code == 422


def test_search_returns_free_standard_room(client, guest_headers):
    check_in = (date.today() + timedelta(days=30)).isoformat()
    check_out = (date.today() + timedelta(days=32)).isoformat()
    resp = client.get(
        "/rooms/search",
        params={"check_in": check_in, "check_out": check_out, "room_type": "standard"},
        headers=guest_headers,
    )
    assert resp.status_code == 200, resp.text
    assert any(room["room_type"] == "standard" for room in resp.json())


def test_search_rejects_bad_dates(client, guest_headers):
    today = date.today().isoformat()
    resp = client.get(
        "/rooms/search",
        params={"check_in": today, "check_out": today, "room_type": "standard"},
        headers=guest_headers,
    )
    assert resp.status_code == 422


def test_search_excludes_unavailable_room(client, guest_headers):
    # Room 105 is seeded with is_available=False; it must never appear.
    check_in = (date.today() + timedelta(days=30)).isoformat()
    check_out = (date.today() + timedelta(days=32)).isoformat()
    resp = client.get(
        "/rooms/search",
        params={"check_in": check_in, "check_out": check_out, "room_type": "standard"},
        headers=guest_headers,
    )
    assert resp.status_code == 200, resp.text
    assert all(room["id"] != 105 for room in resp.json())


def test_receptionist_can_list_rooms(client, receptionist_headers):
    resp = client.get("/rooms/", headers=receptionist_headers)
    assert resp.status_code == 200, resp.text
    assert {101, 102, 201} <= {room["room_id"] for room in resp.json()}

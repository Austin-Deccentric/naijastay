"""Room listing / search tests via TestClient."""

from datetime import date, timedelta


def test_get_all_rooms_lists_seeded_rooms(client, guest_headers):
    resp = client.get("/rooms/", headers=guest_headers)
    assert resp.status_code == 200, resp.text
    ids = {room["id"] for room in resp.json()}
    assert {101, 102, 201} <= ids


def test_get_all_rooms_requires_auth(client):
    assert client.get("/rooms/").status_code == 401


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
    assert client.get("/rooms/", headers=receptionist_headers).status_code == 200

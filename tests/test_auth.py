"""Auth + profile tests via TestClient."""

from tests import helpers


def test_register_returns_201(client):
    resp = client.post(
        "/auth/register",
        json={"email": "newguest@example.ng", "password": "Password123!"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "newguest@example.ng"
    assert body["role"] == "guest"


def test_register_duplicate_returns_409(client):
    payload = {"email": "dup@example.ng", "password": "Password123!"}
    assert client.post("/auth/register", json=payload).status_code == 201
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_returns_token(client):
    resp = client.post(
        "/auth/login", data={"username": helpers.GUEST_1, "password": helpers.PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_returns_401(client):
    resp = client.post(
        "/auth/login", data={"username": helpers.GUEST_1, "password": "wrong-pass-x"}
    )
    assert resp.status_code == 401


def test_users_me_with_token(client, guest_headers):
    resp = client.get("/users/me", headers=guest_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == helpers.GUEST_1


def test_users_me_without_token_returns_401(client):
    assert client.get("/users/me").status_code == 401

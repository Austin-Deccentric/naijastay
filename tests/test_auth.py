"""Auth + profile tests via TestClient."""

import pytest

from tests import helpers

pytestmark = pytest.mark.anyio


async def test_register_returns_201(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "newguest@example.ng", "password": "Password123!"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["email"] == "newguest@example.ng"
    assert body["data"]["role"] == "guest"


async def test_register_duplicate_returns_409(client):
    payload = {"email": "dup@example.ng", "password": "Password123!"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_returns_token(client):
    resp = await client.post(
        "/api/v1/auth/login", data={"username": helpers.GUEST_1, "password": helpers.PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # OAuth2 token endpoint: bare shape (no envelope) so spec-bound
    # clients like Swagger UI's Authorize button can harvest the token.
    assert "status" not in body and "data" not in body
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password_returns_401(client):
    resp = await client.post(
        "/api/v1/auth/login", data={"username": helpers.GUEST_1, "password": "wrong-pass-x"}
    )
    assert resp.status_code == 401


async def test_users_me_with_token(client, guest_headers):
    resp = await client.get("/api/v1/users/me", headers=guest_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["email"] == helpers.GUEST_1


async def test_users_me_without_token_returns_401(client):
    assert (await client.get("/api/v1/users/me")).status_code == 401

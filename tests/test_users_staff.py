"""Staff management tests via TestClient.

Locks current behaviour: only receptionist/housekeeper creatable,
disable is idempotent (re-disable -> 200, stays inactive).
"""

STAFF_PW = "Password123!"


def _create(client, headers, email, password=STAFF_PW, role="receptionist"):
    return client.post(
        "/users/staff",
        json={"email": email, "password": password, "role": role},
        headers=headers,
    )


def test_manager_creates_receptionist_201(client, manager_headers):
    resp = _create(client, manager_headers, "new.front@naijastay.ng")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["message"] == "Staff account created."
    assert body["data"]["email"] == "new.front@naijastay.ng"
    assert body["data"]["role"] == "receptionist"
    assert body["data"]["is_active"] is True


def test_manager_creates_housekeeper_201(client, manager_headers):
    resp = _create(
        client, manager_headers, "new.keep@naijastay.ng", role="housekeeper"
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["role"] == "housekeeper"


def test_create_duplicate_email_400(client, manager_headers):
    assert _create(client, manager_headers, "dup.staff@naijastay.ng").status_code == 201
    resp = _create(client, manager_headers, "dup.staff@naijastay.ng")
    assert resp.status_code == 400, resp.text


def test_create_duplicate_email_case_insensitive_400(client, manager_headers):
    assert _create(client, manager_headers, "case.staff@naijastay.ng").status_code == 201
    resp = _create(client, manager_headers, "CASE.STAFF@naijastay.ng")
    assert resp.status_code == 400, resp.text


def test_create_guest_or_manager_role_400(client, manager_headers):
    assert (
        _create(client, manager_headers, "g@naijastay.ng", role="guest").status_code
        == 400
    )
    assert (
        _create(client, manager_headers, "m@naijastay.ng", role="manager").status_code
        == 400
    )


def test_guest_and_receptionist_cannot_create_403(
    client, guest_headers, receptionist_headers
):
    assert (
        _create(client, guest_headers, "x1@naijastay.ng").status_code == 403
    )
    assert (
        _create(client, receptionist_headers, "x2@naijastay.ng").status_code == 403
    )


def test_unauthenticated_cannot_create_401(client):
    assert _create(client, {}, "x3@naijastay.ng").status_code == 401


def test_manager_disables_staff_200_and_login_forbidden(client, manager_headers):
    created = _create(client, manager_headers, "doomed@naijastay.ng").json()["data"]
    resp = client.patch(
        f"/users/staff/{created['id']}/disable", headers=manager_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_active"] is False
    login = client.post(
        "/auth/login",
        data={"username": "doomed@naijastay.ng", "password": STAFF_PW},
    )
    assert login.status_code == 401, login.text


def test_disable_missing_404(client, manager_headers):
    assert (
        client.patch("/users/staff/999999/disable", headers=manager_headers).status_code
        == 404
    )


def test_disable_guest_or_manager_404(client, manager_headers):
    from tests import helpers

    guest_id = helpers.run(
        _user_id_by_email(helpers.GUEST_1),
    )
    assert (
        client.patch(
            f"/users/staff/{guest_id}/disable", headers=manager_headers
        ).status_code
        == 404
    )


def test_redisable_returns_200_idempotent(client, manager_headers):
    """Locked contract: re-disabling an inactive account is a no-op 200."""
    created = _create(client, manager_headers, "twice@naijastay.ng").json()["data"]
    url = f"/users/staff/{created['id']}/disable"
    assert client.patch(url, headers=manager_headers).status_code == 200
    resp = client.patch(url, headers=manager_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_active"] is False


async def _user_id_by_email(email: str) -> int:
    from sqlalchemy import text

    from app.db.session import AsyncSessionMaker

    async with AsyncSessionMaker() as session:
        return (
            await session.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": email}
            )
        ).scalar()

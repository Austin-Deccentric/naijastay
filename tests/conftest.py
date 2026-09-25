"""Pytest fixtures for the TestClient suite.

- Rate limiting is disabled (`limiter.enabled = False`) so auth tests never
  flake on `5/minute` login / `10/hour` register limits.
- The DB is the same docker Postgres the app uses; every test starts from a
  truncated + minimally seeded state (see `tests/helpers.py`).
- `TestClient(app)` is used *without* a context manager so the app lifespan
  (scheduler + engine dispose + redis connect) does not run inside tests;
  `app.state.redis` is attached directly to the real docker redis instead.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.integrations.redis import create_redis
from app.main import app
from tests import helpers

limiter.enabled = False


@pytest.fixture()
def client():
    helpers.reset_db()
    helpers.seed_base()
    # Fresh client per test: the shared object must never hop event loops
    # (each TestClient owns a portal loop; lifespan never runs in tests).
    # Publishing paths no-op gracefully if Redis is unreachable.
    redis_client = create_redis()
    try:
        # GET /rooms/ is cached in Redis while Postgres is re-seeded per
        # test — flush so no cached rows leak across tests. Best-effort:
        # the suite must still run if Redis is down. Uses a throwaway
        # client: a redis client must never hop event loops (each
        # TestClient owns a portal loop), so the shared client below is
        # left unconnected until first use inside the request loop.
        async def _flush() -> None:
            tmp = create_redis()
            try:
                await tmp.flushdb()
            finally:
                await tmp.aclose()

        helpers.run(_flush())
    except Exception:
        pass
    app.state.redis = redis_client
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def guest_headers(client):
    return helpers.login_headers(client, helpers.GUEST_1)


@pytest.fixture()
def guest2_headers(client):
    return helpers.login_headers(client, helpers.GUEST_2)


@pytest.fixture()
def receptionist_headers(client):
    return helpers.login_headers(client, helpers.RECEPTIONIST)


@pytest.fixture()
def manager_headers(client):
    return helpers.login_headers(client, helpers.MANAGER)


@pytest.fixture()
def housekeeper_headers(client):
    return helpers.login_headers(client, helpers.HOUSEKEEPER)

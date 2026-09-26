"""Pytest fixtures for the async (anyio) suite.

- Rate limiting is disabled (`limiter.enabled = False`) so auth tests never
  flake on `5/minute` login / `10/hour` register limits.
- Tests run against a DEDICATED test database (`TEST_DATABASE_URL`), never
  the dev DB: the env switch below runs before any `app.*` import so the
  single global engine, helpers, and seed all follow it. A guard aborts the
  session unless the active db name contains "test".
- Test Redis is isolated by index (`TEST_REDIS_URL`, db 1); per-test flushdb
  therefore never touches dev cache (db 0).
- HTTP goes through `httpx.AsyncClient` + `ASGITransport` on the test's own
  event loop (anyio, asyncio backend): one loop per test, no portal hopping.
  Lifespan stays off (no scheduler/engine-dispose in tests); `app.state.redis`
  is attached directly to the real docker redis instead.
"""

import logging
import os
from urllib.parse import urlparse

os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL", "").strip()
    or "postgresql+psycopg://naijastay:PADE1234@localhost:5432/9jastay_test"
)
os.environ["REDIS_URL"] = (
    os.environ.get("TEST_REDIS_URL", "").strip() or "redis://localhost:6379/1"
)

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.integrations.redis import create_redis
from app.main import app
from tests import helpers

logger = logging.getLogger("naijastay")

_test_db = urlparse(settings.database_url).path.lstrip("/")
if "test" not in _test_db:
    raise RuntimeError(
        f"Refusing to run tests against non-test database '{_test_db}'. "
        "Set TEST_DATABASE_URL to a *-test database (see make test-db)."
    )

limiter.enabled = False


@pytest.fixture
def anyio_backend():
    """Pin the anyio pytest plugin to asyncio (trio isn't installed).

    The plugin already scopes this at module level internally; the
    per-test event loop is deliberate isolation, not overhead.
    """
    return "asyncio"


@pytest.fixture(scope="session")
def password_hash() -> str:
    """Bcrypt cost (~0.35s) paid once per session, not once per test.

    Loop-free deterministic value, so session scope is safe. Login
    verifies stay per-test (they double as login coverage).
    """
    return hash_password(helpers.PASSWORD)


@pytest.fixture()
async def client(password_hash):
    await helpers.reset_db()
    await helpers.seed_base(password_hash)
    # Real docker redis, flushed per test so no cached rows leak across
    # tests. Best-effort: the suite must still run if Redis is down.
    # Publishing paths no-op gracefully when unreachable.
    redis_client = create_redis()
    try:
        await redis_client.flushdb()
    except Exception:
        logger.warning("Redis flushdb failed; cached rows may leak across tests",
                       exc_info=True)
    app.state.redis = redis_client
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            logger.warning("Redis close failed", exc_info=True)


@pytest.fixture()
async def guest_headers(client):
    return await helpers.login_headers(client, helpers.GUEST_1)


@pytest.fixture()
async def guest2_headers(client):
    return await helpers.login_headers(client, helpers.GUEST_2)


@pytest.fixture()
async def receptionist_headers(client):
    return await helpers.login_headers(client, helpers.RECEPTIONIST)


@pytest.fixture()
async def manager_headers(client):
    return await helpers.login_headers(client, helpers.MANAGER)


@pytest.fixture()
async def housekeeper_headers(client):
    return await helpers.login_headers(client, helpers.HOUSEKEEPER)

"""Pytest fixtures for the TestClient suite.

- Rate limiting is disabled (`limiter.enabled = False`) so auth tests never
  flake on `5/minute` login / `10/hour` register limits.
- The DB is the same docker Postgres the app uses; every test starts from a
  truncated + minimally seeded state (see `tests/helpers.py`).
- `TestClient(app)` is used *without* a context manager so the app lifespan
  (scheduler + engine dispose) does not run inside tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.main import app
from tests import helpers

limiter.enabled = False


@pytest.fixture()
def client():
    helpers.reset_db()
    helpers.seed_base()
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

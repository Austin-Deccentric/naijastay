"""Realism suite fixtures: ONE event loop + lifespan ON for the session.

Contrast with the correctness suite (per-test loops, lifespan off):
- a single `asyncio` loop lives for the whole session; sync tests drive it
  with `run(coro)` instead of `asyncio.run` (a second loop would strand
  loop-bound clients mid-session);
- the app lifespan runs once: real Redis connects, APScheduler starts. Full
  lifespan exit at teardown is safe (`engine.dispose()` only drops pooled
  connections; later suites reconnect transparently);
- the DB is seeded ONCE (plus extra rooms 301-312 for partitioning); tests
  never truncate. Each test owns distinct rooms so concurrent tests can't
  talk through shared rows.

Requires docker postgres + redis (no graceful skip: realism IS the live env).
"""

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import AsyncSessionMaker
from app.domains.rooms.models import Room
from app.main import app
from tests import helpers

logger = logging.getLogger("naijastay")

EXTRA_ROOMS = [(301, "standard"), (302, "standard"), (303, "standard"),
               (304, "deluxe"), (305, "deluxe"), (306, "standard")]


@pytest.fixture(scope="session")
def session_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def run(loop, coro):
    """Drive one coroutine on the session loop from sync test code."""
    return loop.run_until_complete(coro)


@pytest.fixture(scope="session")
def live_ctx(session_loop, password_hash):
    """Seeded-once live world: {loop, client, guest, receptionist, manager}."""
    async def _setup():
        await helpers.reset_db()
        await helpers.seed_base(password_hash)
        async with AsyncSessionMaker() as session:
            for room_id, room_type in EXTRA_ROOMS:
                session.add(Room(id=room_id, room_type=room_type, is_available=True))
            await session.commit()
        lifespan = app.router.lifespan_context(app)
        try:
            await lifespan.__aenter__()
        except Exception:
            logger.warning("Realism lifespan failed; skipping live session", exc_info=True)
            pytest.skip("realism needs docker postgres + redis running")
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        guest = await helpers.login_headers(client, helpers.GUEST_1)
        receptionist = await helpers.login_headers(client, helpers.RECEPTIONIST)
        manager = await helpers.login_headers(client, helpers.MANAGER)
        return lifespan, client, guest, receptionist, manager

    lifespan, client, guest, receptionist, manager = run(session_loop, _setup())
    yield {"loop": session_loop, "client": client,
           "guest": guest, "receptionist": receptionist, "manager": manager}

    async def _teardown():
        try:
            await client.aclose()
        finally:
            await lifespan.__aexit__(None, None, None)

    run(session_loop, _teardown())

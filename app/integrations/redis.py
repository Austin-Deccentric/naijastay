"""Redis integration: client factory and lifespan helpers.

The connected client lives on ``app.state.redis`` (see ``app.core.utils``).
All room-status messaging lives in ``app.domains.rooms.streaming``; this
module only owns the connection lifecycle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("naijastay")

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI


def create_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def init_redis(app: FastAPI) -> None:
    """Connect and stash the client on ``app.state.redis``."""
    client = create_redis()
    await client.ping()
    app.state.redis = client
    logger.info("Redis connected (%s)", settings.redis_url)


async def close_redis(app: FastAPI) -> None:
    """Close the shared client, if one was initialised."""
    client = getattr(app.state, "redis", None)
    if client is not None:
        await client.aclose()
        app.state.redis = None
        logger.info("Redis closed.")

"""Read-through JSON cache over the shared Redis client.

Cache never raises: every Redis failure falls
through to Postgres.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.integrations.redis import TRedis

logger = logging.getLogger("naijastay")

DEFAULT_TTL = 30
ROOMS_LIST_TTL = 30


def make_key(namespace: str, *parts: object) -> str:
    """Single builder for every endpoint"""
    segments = [namespace, *(str(p) for p in parts if p is not None)]
    return ":".join(segments) if segments else "default"


async def get_or_set_json(
    client: TRedis | None,
    key: str,
    ttl_seconds: int,
    producer: Callable[[], Awaitable[str]],
) -> str:
    """Return cached JSON string, else run producer(), cache it, return it.

    - client None (no redis / tests) -> run producer directly.
    - hit -> return stored string, producer never runs.
    - miss -> fresh = await producer(); SETEX key ttl fresh; return fresh.
    - ANY redis error -> log + run producer. Never raises.
    """
    if client is None:
        return await producer()
    try:
        cached = await client.get(key)
        if cached is not None:
            return cached if isinstance(cached, str) else cached.decode()
        fresh = await producer()
        try:
            await client.setex(key, ttl_seconds, fresh)
        except Exception:
            logger.warning("Redis SETEX failed; returning fresh value", exc_info=True)
        return fresh
    except Exception:
        logger.warning("Redis GET failed; falling through to Postgres", exc_info=True)
        return await producer()


async def invalidate_prefix(client: TRedis | None, prefix: str) -> int:
    """Delete every key under ``prefix`` (SCAN-based). Best-effort: never raises.

    Call next to each state-change publish so cached views can't serve stale
    rows for a full TTL after check-in / check-out / payment.
    """
    if client is None:
        return 0
    removed = 0
    try:
        async for key in client.scan_iter(match=f"{prefix}*"):
            await client.delete(key)
            removed += 1
    except Exception:
        logger.warning("Redis invalidate failed for prefix %s", prefix, exc_info=True)
    return removed

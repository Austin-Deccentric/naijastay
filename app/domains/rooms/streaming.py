"""Room-status messaging: channel, serialization, publish, subscribe.

Ownership map for the dashboard stream:
- ``app.integrations.redis`` owns the connection (``app.state.redis``).
- This module owns the protocol: channel name, delta payload shape, the
  subscribe loop, and best-effort publishing.
- ``app.domains.rooms.router`` owns transport (the thin SSE endpoint).
- Routers publish after successful state changes; services stay
  transport-agnostic.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from redis import asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domains.rooms.models import Room
from app.domains.rooms.schemas import RoomDashboardRead

logger = logging.getLogger("naijastay")

CHANNEL = "room_status"


def room_status_payload(room: Room) -> str:
    """Serialize a room row into the SSE payload (``room_id`` key)."""
    return RoomDashboardRead.model_validate(room, from_attributes=True).model_dump_json()


async def publish_room_status(client: aioredis.Redis, room: Room) -> bool:
    """Publish one ``room_status`` delta. Best-effort: never raises"""
    try:
        received = await client.publish(CHANNEL, room_status_payload(room))
    except RedisConnectionError:
        logger.warning("Redis unavailable; dropping room_status delta for room %s", room.id)
        return False
    return received > 0


async def publish_booking_room(request: Request, session: AsyncSession, room_id: int) -> None:
    """Publish the dashboard delta for a booking's room. Best-effort: never
    raises and never fails the calling response.

    Skipped when Redis was never initialised. Routers call this after a successful
    state change.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        return
    room = await session.get(Room, room_id)
    if room is not None:
        await publish_room_status(redis_client, room)


async def unavailable_events():
    yield {"event": "error", "data": "live updates unavailable", "retry": 500}
    

async def room_event_generator(client: aioredis.Redis, request: Request) -> AsyncIterator[dict[str, Any]]:
    """Yield ``room_status`` events until disconnect or Redis loss"""
    
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        while True:
            if await request.is_disconnected():
                break

            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
            except RedisConnectionError:
                break  # Redis went away; let the client reconnect

            if msg is not None and msg["type"] == "message":
                yield {"event": "room_status", "data": msg["data"]}
            # msg is None -> timeout elapsed, loop back and re-check disconnect
    finally:
        await pubsub.aclose()  # unsubscribes and releases the connection

"""Shared DB + webhook-signing helpers for the TestClient suite.

The webhook secret is read from `.env` via `app.core.config.settings`
(`WEBHOOK_SECRET`), never hardcoded — see `tests/README.md`.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionMaker
from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.rooms.models import Room, RoomType
from app.domains.users.models import User, UserRole

PASSWORD = "Password123!"

GUEST_1 = "guest1@example.ng"
GUEST_2 = "guest2@example.ng"
RECEPTIONIST = "frontdesk.lagos@naijastay.ng"
MANAGER = "manager.ade@naijastay.ng"
HOUSEKEEPER = "housekeep.funke@naijastay.ng"

TABLES = [
    "payments",
    "room_nights",
    "bookings",
    "holds",
    "rooms",
    "processed_events",
    "users",
    "room_types",
]


def webhook_secret() -> str:
    secret = settings.webhook_secret
    assert len(secret) >= 8, "WEBHOOK_SECRET in .env must be at least 8 chars"
    return secret


def sign_raw(raw: bytes, secret: str | None = None) -> str:
    """HMAC-SHA256 hex over the exact raw bytes, mirroring the provider."""
    return hmac.new((secret or webhook_secret()).encode(), raw, hashlib.sha256).hexdigest()


def encode_event(payload: dict) -> bytes:
    """Serialize exactly like mock_payment_provider (compact separators)."""
    return json.dumps(payload, separators=(",", ":")).encode()


def make_event(
    *,
    event_id: str,
    reference: str,
    amount: float,
    event_type: str = "payment.succeeded",
    currency: str = "NGN",
    paid_at: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "type": event_type,
        "reference": reference,
        "amount": amount,
        "currency": currency,
        "paid_at": paid_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _run(coro):
    return asyncio.run(coro)


def run(coro):
    """Await an async callable from sync test code."""
    return _run(coro)


async def _reset_db() -> None:
    async with AsyncSessionMaker() as session:
        for table in TABLES:
            regclass = (await session.execute(text(f"SELECT to_regclass('{table}')"))).scalar()
            if regclass is None:
                continue
            await session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        await session.commit()


def reset_db() -> None:
    _run(_reset_db())


def set_room_state(room_id: int, state: str) -> None:
    """Set a room's housekeeping state ('clean' | 'dirty')."""
    assert state in {"clean", "dirty"}, state
    _run(
        _execute(
            "UPDATE rooms SET room_state = :state WHERE id = :rid",
            {"state": state.upper(), "rid": int(room_id)},
        )
    )


def set_room_availability(room_id: int, available: bool) -> None:
    """Flip a room's is_available flag (e.g. simulate an occupied room)."""
    _run(
        _execute(
            "UPDATE rooms SET is_available = :av WHERE id = :rid",
            {"av": bool(available), "rid": int(room_id)},
        )
    )


async def _seed_base() -> dict:
    async with AsyncSessionMaker() as session:
        session.add(RoomType(name="standard", base_rate=35000.0, capacity=2))
        session.add(RoomType(name="deluxe", base_rate=65000.0, capacity=3))
        await session.commit()
        pw = hash_password(PASSWORD)
        for email, role in [
            (GUEST_1, UserRole.GUEST),
            (GUEST_2, UserRole.GUEST),
            (RECEPTIONIST, UserRole.RECEPTIONIST),
            (MANAGER, UserRole.MANAGER),
            (HOUSEKEEPER, UserRole.HOUSEKEEPER),
        ]:
            session.add(User(email=email, password_hash=pw, role=role, is_active=True))
        await session.commit()
        for room_id, room_type, available in [
            (101, "standard", True),
            (102, "standard", True),
            (105, "standard", False),
            (201, "deluxe", True),
            (202, "deluxe", True),
        ]:
            session.add(Room(id=room_id, room_type=room_type, is_available=available))
        await session.commit()
    return {"guest1": GUEST_1, "guest2": GUEST_2}


def seed_base() -> dict:
    return _run(_seed_base())


async def _create_hold(
    room_id: int,
    guest_email: str,
    *,
    minutes: int = 10,
    consumed: bool = False,
) -> None:
    async with AsyncSessionMaker() as session:
        session.add(
            Hold(
                room_id=room_id,
                guest_email=guest_email,
                expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
                consumed=consumed,
            )
        )
        await session.commit()


def create_hold(room_id: int, guest_email: str, *, minutes: int = 10, consumed: bool = False) -> None:
    _run(_create_hold(room_id, guest_email, minutes=minutes, consumed=consumed))


async def _create_booking(
    guest_email: str,
    room_id: int,
    check_in: date,
    check_out: date,
    status: BookingStatus,
    total: float,
) -> dict:
    async with AsyncSessionMaker() as session:
        booking = Booking(
            guest_email=guest_email,
            room_id=room_id,
            check_in=check_in,
            check_out=check_out,
            booking_status=status,
            total_amount=total,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return {
            "booking_id": int(booking.booking_id),
            "ref": booking.ref,
            "total": float(booking.total_amount),
        }


def create_booking(
    guest_email: str,
    room_id: int,
    check_in: date,
    check_out: date,
    status: BookingStatus,
    total: float,
) -> dict:
    return _run(_create_booking(guest_email, room_id, check_in, check_out, status, total))


async def _execute(sql: str, params: dict | None = None) -> None:
    async with AsyncSessionMaker() as session:
        await session.execute(text(sql), params or {})
        await session.commit()


def backdate_booking(booking_id: int, minutes_ago: int) -> None:
    """Move a booking's created_at into the past (sweeper fixtures)."""
    _run(
        _execute(
            "UPDATE bookings SET created_at = NOW() - make_interval(mins => :mins) "
            "WHERE booking_id = :bid",
            {"mins": minutes_ago, "bid": int(booking_id)},
        )
    )


async def _scalar(sql: str):
    async with AsyncSessionMaker() as session:
        return (await session.execute(text(sql))).scalar()


def count(table: str, where: str = "") -> int:
    return int(_run(_scalar(f"SELECT COUNT(*) FROM {table} {where}")) or 0)


def get_booking_status(booking_id: int) -> str | None:
    value = _run(_scalar(f"SELECT booking_status FROM bookings WHERE booking_id = {int(booking_id)}"))
    # Postgres returns the enum *label* (e.g. 'PROCESSING'); normalize to the
    # lowercase values the API exposes (e.g. 'processing').
    return str(value).lower() if value is not None else None


def login_headers(client, email: str, password: str = PASSWORD) -> dict:
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, f"login failed for {email}: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

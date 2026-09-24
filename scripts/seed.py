"""Destructive dev seeder for NaijaStay (Docker Postgres).

Wipes test data and inserts a small, realistic fixture set covering the
current booking flow: users per role, room types/rooms, holds
(active/expired/consumed), bookings (processing/confirmed/cancelled) and
room_nights + payment rows when those tables exist.

Usage (see docs/SEED.md):
    docker compose up -d postgres
    uv run alembic upgrade head
    uv run python scripts/seed.py --reset
    uv run python scripts/seed.py --reset --yes   # skip confirm prompt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Allow `python scripts/seed.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utc_today
from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.rooms.models import Room, RoomNight, RoomState, RoomType
from app.domains.users.models import User, UserRole

SEED_PASSWORD = "Password123!"

# Realistic fixtures. Emails are lowercase because auth/booking lookups
# normalize with .strip().lower().
GUESTS = [
    ("adaeze.okafor@example.ng", "Adaeze Okafor"),
    ("tunde.bakare@example.ng", "Tunde Bakare"),
    ("ngozi.eze@example.ng", "Ngozi Eze"),
]
STAFF = [
    ("frontdesk.lagos@naijastay.ng", UserRole.RECEPTIONIST, "Front Desk Lagos"),
    ("manager.ade@naijastay.ng", UserRole.MANAGER, "Ade (Manager)"),
    ("housekeep.funke@naijastay.ng", UserRole.HOUSEKEEPER, "Funke (Housekeeping)"),
]

ROOM_TYPES = [
    # (name, base_rate NGN/night, capacity)
    ("standard", 35000.0, 2),
    ("deluxe", 65000.0, 3),
    ("executive-suite", 150000.0, 4),
]

# (id, room_type, is_available) — hotel-style numbering.
ROOMS = [
    (101, "standard", True),
    (102, "standard", True),
    (103, "standard", True),
    (104, "standard", True),
    (105, "standard", False),  # intentionally unavailable for negative tests
    (201, "deluxe", True),
    (202, "deluxe", True),
    (203, "deluxe", True),
    (204, "deluxe", True),
    (301, "executive-suite", True),
    (302, "executive-suite", True),
    (303, "executive-suite", True),
]

# Tables in the current alembic head (f544d03a5ec7) plus the newer
# payments tables. Payments tables are truncated/inserted only if they
# actually exist, because the checked-in migration does not create them yet.
KNOWN_TABLES = [
    "payments",
    "room_nights",
    "bookings",
    "holds",
    "rooms",
    "processed_events",
    "users",
    "room_types",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Destructively seed the dev database.")
    p.add_argument(
        "--reset",
        action="store_true",
        help="REQUIRED. Confirm you want to wipe seed tables (TRUNCATE ... CASCADE).",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    p.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL from .env (default: settings.database_url).",
    )
    return p.parse_args()


def resolve_database_url(override: str | None) -> str:
    url = override or settings.database_url
    if not url:
        raise ValueError("DATABASE_URL is not set (use .env or --database-url).")
    scheme = url.split("://", 1)[0]
    if scheme in {"postgres", "postgresql"}:
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


async def reset_tables(session: AsyncSession) -> None:
    """TRUNCATE each known table if it exists. CASCADE handles FK order."""
    for table in KNOWN_TABLES:
        regclass = (await session.execute(text(f"SELECT to_regclass('{table}')"))).scalar()
        if regclass is None:
            print(f"  skip reset: table '{table}' does not exist yet")
            continue
        await session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        print(f"  truncated: {table}")
    await session.commit()


async def seed(session: AsyncSession) -> dict:
    today = utc_today()  # UTC everywhere: matches server-side date boundaries.
    now = datetime.now(UTC)

    # --- room types ---
    rates = {}
    for name, base_rate, capacity in ROOM_TYPES:
        rt = RoomType(name=name, base_rate=base_rate, capacity=capacity)
        session.add(rt)
        rates[name] = base_rate
    await session.commit()

    # --- users ---
    password_hash = hash_password(SEED_PASSWORD)
    for email, _name in GUESTS:
        session.add(
            User(email=email, password_hash=password_hash, role=UserRole.GUEST, is_active=True)
        )
    for email, role, _name in STAFF:
        session.add(
            User(email=email, password_hash=password_hash, role=role, is_active=True)
        )
    await session.commit()

    adaeze, tunde, ngozi = (e for e, _ in GUESTS)

    # --- rooms (explicit hotel-style ids) ---
    for room_id, room_type, is_available in ROOMS:
        session.add(Room(id=room_id, room_type=room_type, is_available=is_available))
    await session.commit()

    # --- holds ---
    # Room 201: active hold owned by Tunde (used by the PROCESSING booking below).
    # Room 202: expired hold (sweeper scenario).
    # Room 203: consumed hold (already used scenario).
    session.add(Hold(room_id=201, guest_email=tunde, expires_at=now + timedelta(minutes=10), consumed=False))
    session.add(Hold(room_id=202, guest_email=ngozi, expires_at=now - timedelta(hours=1), consumed=False))
    session.add(Hold(room_id=203, guest_email=adaeze, expires_at=now + timedelta(minutes=10), consumed=True))
    await session.commit()

    # --- bookings ---
    def total(room_type: str, check_in: date, check_out: date) -> float:
        return rates[room_type] * (check_out - check_in).days

    # 1. CONFIRMED booking checking in TODAY (receptionist check-in test).
    #    Room 101 (standard), guest Adaeze, 2 nights.
    check_in_today = today
    check_out_today = today + timedelta(days=2)
    confirmed = Booking(
        guest_email=adaeze,
        room_id=101,
        check_in=check_in_today,
        check_out=check_out_today,
        booking_status=BookingStatus.CONFIRMED,
        total_amount=total("standard", check_in_today, check_out_today),
    )
    session.add(confirmed)
    await session.commit()
    await session.refresh(confirmed)
    confirmed_id = int(confirmed.booking_id)
    confirmed_total = float(confirmed.total_amount)
    confirmed_ref = confirmed.ref  # plain value snapshot; may be None pre-migration

    # Room-night rows for the confirmed stay (one per night in [check_in, check_out)).
    night = check_in_today
    while night < check_out_today:
        session.add(
            RoomNight(
                room_id=101,
                night_date=night,
                booking_id=confirmed_id,
                room_state=RoomState.CLEAN,
            )
        )
        night += timedelta(days=1)
    # NOTE: check_in_guest rejects rooms with is_available=False as
    # "already occupied", so the confirmed room is deliberately left
    # available for the check-in test. The payments webhook would normally
    # flip it to False on confirm.
    await session.commit()

    # 2. PROCESSING booking (pay flow test). Room 201 (deluxe), guest Tunde,
    #    future dates, backed by the active hold above.
    pay_in = today + timedelta(days=7)
    pay_out = today + timedelta(days=9)
    processing = Booking(
        guest_email=tunde,
        room_id=201,
        check_in=pay_in,
        check_out=pay_out,
        booking_status=BookingStatus.PROCESSING,
        total_amount=total("deluxe", pay_in, pay_out),
    )
    session.add(processing)
    await session.commit()
    await session.refresh(processing)
    processing_id = int(processing.booking_id)

    # 3. CANCELLED booking overlapping the PROCESSING dates on another room,
    #    proving room search ignores cancelled bookings.
    session.add(
        Booking(
            guest_email=ngozi,
            room_id=204,
            check_in=pay_in,
            check_out=pay_out,
            booking_status=BookingStatus.CANCELLED,
            total_amount=total("deluxe", pay_in, pay_out),
        )
    )
    await session.commit()

    summary: dict = {
        "today": today.isoformat(),
        "confirmed_booking_id": confirmed_id,
        "confirmed_room": 101,
        "processing_booking_id": processing_id,
        "processing_room": 201,
        "pay_dates": (pay_in.isoformat(), pay_out.isoformat()),
    }

    # --- payments (only if the tables exist in this DB) ---
    has_events = (await session.execute(text("SELECT to_regclass('processed_events')"))).scalar()
    has_payments = (await session.execute(text("SELECT to_regclass('payments')"))).scalar()
    if has_events is not None and has_payments is not None:
        from app.domains.payments.models import Payment, ProcessedEvent

        event_id = f"evt_seed_{today.strftime('%Y%m%d')}_101"
        session.add(
            ProcessedEvent(
                event_id=event_id,
                event_type="payment.succeeded",
                reference=confirmed_ref or f"BOOK-{confirmed_id}",
            )
        )
        await session.commit()
        session.add(
            Payment(
                booking_id=confirmed_id,
                amount=confirmed_total,
                currency="NGN",
                provider_event_id=event_id,
                recorded_by=None,
            )
        )
        await session.commit()
        summary["payment_event_id"] = event_id
    else:
        print("  skip payments: tables 'payments'/'processed_events' not migrated yet")
        print("  run: uv run alembic revision --autogenerate -m \"add payments\" && uv run alembic upgrade head")

    return summary


async def main_async(args: argparse.Namespace) -> int:
    if not args.reset:
        print("Refusing to wipe without --reset. Re-run as:")
        print("  uv run python scripts/seed.py --reset")
        return 2
    if not args.yes:
        answer = input("This will DELETE all rows in seed tables. Continue? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1

    url = resolve_database_url(args.database_url)
    engine = create_async_engine(url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            print("Resetting tables (destructive)...")
            await reset_tables(session)
            print("Seeding...")
            summary = await seed(session)
    finally:
        await engine.dispose()

    print("\nSeed complete.")
    print(f"  All users share password: {SEED_PASSWORD}")
    print("  Guests: " + ", ".join(e for e, _ in GUESTS))
    print("  Staff:  " + ", ".join(e for e, _, _ in STAFF))
    print(f"  CONFIRMED booking {summary['confirmed_booking_id']} room 101 "
          f"check_in={summary['today']} (use for receptionist check-in test)")
    print(f"  PROCESSING booking {summary['processing_booking_id']} room 201 "
          f"{summary['pay_dates'][0]} -> {summary['pay_dates'][1]} (use for pay/webhook test)")
    if "payment_event_id" in summary:
        print(f"  Payment event: {summary['payment_event_id']}")
    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

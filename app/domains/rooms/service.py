from datetime import UTC, date, datetime

from app.domains.bookings.models import Booking, BookingStatus, Holds
from app.domains.rooms.models import Room
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def search_available_rooms(
    session: AsyncSession,
    check_in: date,
    check_out: date,
    room_type: str,
) -> list[Room]:

    rooms_result = await session.exec(
        select(Room).where(
            Room.room_type == room_type,
            Room.is_available == True,
        )
    )

    rooms = rooms_result.all()

    if not rooms:
        return []

    available_rooms = []

    for room in rooms:
        booking_result = await session.exec(
            select(Booking).where(
                Booking.room_id == room.id,
                Booking.booking_status != BookingStatus.CANCELLED,
                Booking.check_in < check_out,
                Booking.check_out > check_in,
            )
        )

        if booking_result.first() is not None:
            continue

        hold_result = await session.exec(
            select(Holds).where(
                Holds.room_id == room.id,
                Holds.consumed == False,
                Holds.expires_at > datetime.now(UTC),
            )
        )

        if hold_result.first() is not None:
            continue

        available_rooms.append(room)

    return available_rooms
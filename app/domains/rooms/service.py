from datetime import UTC, date, datetime

from pydantic import TypeAdapter
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.rooms.models import Room, RoomNight, RoomState, RoomType
from app.domains.rooms.schemas import (
    AvailableRoomResponse,
    OccupancyReport,
    RoomDashboardRead,
    RoomTypeUpdate,
)

_ROOMS_ADAPTER = TypeAdapter(list[RoomDashboardRead])
_SEARCH_ADAPTER = TypeAdapter(list[AvailableRoomResponse])


class RoomNotFound(Exception):
    pass


async def mark_room_clean(
    room_id: int,
    session: AsyncSession,
) -> tuple[Room, bool]:
    """Mark a room clean. Returns (room, already_clean).

    Idempotent: already-clean rooms are a no-op success so the router
    can message the replay distinctly.
    """
    room = await get_room(
        room_id=room_id,
        session=session,
    )

    already_clean = room.room_state == RoomState.CLEAN
    room.room_state = RoomState.CLEAN
    room.is_available = True

    session.add(room)
    await session.commit()
    await session.refresh(room)

    return room, already_clean

async def search_available_rooms(
    session: AsyncSession,
    check_in: date,
    check_out: date,
    room_type: str,
) -> list[Room]:
    conflicting_bookings = select(Booking.room_id).where(
        Booking.booking_status != BookingStatus.CANCELLED,
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )

    active_holds = select(Hold.room_id).where(
        Hold.consumed == False,
        Hold.expires_at > datetime.now(UTC),
    )

    query = select(Room).where(
        Room.room_type == room_type,
        Room.is_available == True,
        Room.id.not_in(conflicting_bookings),
        Room.id.not_in(active_holds),
    )

    result = await session.exec(query)

    return list(result.all())


async def get_room(
    room_id: int,
    session: AsyncSession,
) -> Room:
    result = await session.exec(
        select(Room).where(
            Room.id == room_id,
        )
    )

    room = result.first()

    if not room:
        raise ValueError("Room not found")

    return room


async def get_rooms(session, room_state: RoomState | None = None) -> list[Room]:
    query = select(Room.id, Room.room_type, Room.is_available, Room.room_state)
    if room_state:
        query = query.where(Room.room_state == room_state)
    result = await session.execute(query.order_by(Room.id))
    return result.all()
    


async def get_available_rooms(
    session: AsyncSession,
    room_date: date | None = None,
    room_type: str | None = None,
) -> list[Room]:
    if room_date is None:
        room_date = date.today()

    conflicting_bookings = select(Booking.room_id).where(
        Booking.booking_status != BookingStatus.CANCELLED,
        Booking.check_in <= room_date,
        Booking.check_out > room_date,
    )
    
    active_holds = select(Hold.room_id).where(
            Hold.consumed == False,
            Hold.expires_at > datetime.now(UTC),
    )
    

    query = select(Room).where(
        Room.is_available == True,
        Room.id.not_in(conflicting_bookings),
        Room.id.not_in(active_holds),
    )

    if room_type:
        query = query.where(
            Room.room_type == room_type,
        )

    result = await session.exec(query)

    return list(result.all())


async def nights_taken(
    session: AsyncSession,
    room_id: int,
    check_in: date,
    check_out: date,
) -> list[date]:
    """Return occupied nights for a room within [check_in, check_out]."""

    result = await session.exec(
        select(RoomNight.night_date).where(
            RoomNight.room_id == room_id,
            RoomNight.night_date >= check_in,
            RoomNight.night_date < check_out,
        )
    )

    return list(result.all())


class RoomTypeMissing(ValueError):
    pass


async def _get_room_type(session: AsyncSession, name: str,) -> RoomType:
    result = await session.exec(
        select(RoomType).where(
            RoomType.name == name,
        )
    )

    room_type = result.first()

    if room_type is None:
        raise RoomTypeMissing(f"Room type '{name}' not found")

    return room_type


async def update_room_type(
    session: AsyncSession,
    name: str,
    data: RoomTypeUpdate,
) -> RoomType:
    room_type = await _get_room_type(
        session=session,
        name=name,
    )

    patch = data.model_dump(exclude_unset=True)

    room_type.sqlmodel_update(patch)

    session.add(room_type)

    await session.commit()

    await session.refresh(room_type)

    return room_type


async def get_occupancy_report(
    session: AsyncSession,
    report_date: date | None = None,
) -> OccupancyReport:
    if report_date is None:
        report_date = date.today()
    total_result = await session.exec(select(func.count(Room.id)))

    total_rooms = total_result.one()

    occupied_result = await session.exec(
       select(func.count(func.distinct(Booking.room_id)))
        .where(
            Booking.check_in <= report_date,
            Booking.check_out > report_date,
            Booking.booking_status == BookingStatus.CHECKED_IN,
        )
    )

    occupied_rooms = occupied_result.one()

    available_rooms = max(total_rooms - occupied_rooms,0,)

    occupancy_percentage = (
        (occupied_rooms / total_rooms) * 100
        if total_rooms > 0
        else 0.0
    )

    return OccupancyReport.model_validate({
        "report_date": report_date,
        "total_rooms": total_rooms,
        "occupied_rooms": occupied_rooms,
        "available_rooms": available_rooms,
        "occupancy_percentage": round(occupancy_percentage, 2)
    })
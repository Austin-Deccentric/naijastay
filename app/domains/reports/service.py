from datetime import date

from app.domains.bookings.models import Booking, BookingStatus
from app.domains.reports.schemas import OccupancyReport
from app.domains.rooms.models import Room, RoomState
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession


async def get_occupancy_report(
    session: AsyncSession,
    report_date: date,
) -> OccupancyReport:

    total_result = await session.exec(
        select(func.count(Room.id))
    )

    total_rooms = total_result.one()

    occupied_result = await session.exec(
        select(func.count(Room.id))
        .join(
            Booking,
            Booking.room_id == Room.id,
        )
        .where(
            Booking.booking_status != BookingStatus.CANCELLED,
            Booking.check_in <= report_date,
            Booking.check_out > report_date,
        )
    )

    occupied_rooms = occupied_result.one()

    dirty_result = await session.exec(
        select(func.count(Room.id)).where(
            Room.room_state == RoomState.DIRTY,
        )
    )

    dirty_rooms = dirty_result.one()

    available_rooms = max(
        total_rooms - occupied_rooms - dirty_rooms,
        0,
    )

    occupancy_rate = (
        (occupied_rooms / total_rooms) * 100
        if total_rooms
        else 0.0
    )

    return OccupancyReport(
        report_date=report_date,
        total_rooms=total_rooms,
        occupied_rooms=occupied_rooms,
        available_rooms=available_rooms,
        dirty_rooms=dirty_rooms,
        occupancy_rate=round(
            occupancy_rate,
            2,
        ),
    )
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domains.rooms.models import Room, RoomNight, RoomType
from app.domains.rooms.schema import RoomTypeUpdate


class RoomTypeMissing(ValueError): ...

async def get_room(room_id: int, session: AsyncSession) -> Room:
    result = await session.exec(
        select(Room).where(Room.id == room_id)
    )
    result = result.first()
    if not result:
        raise ValueError("Room not found")
        
    return result


async def get_rooms(session: AsyncSession) -> list[Room]:
    result = await session.exec(
        select(Room)
    )
    return list(result.all())

# rooms/service.py (append)
async def nights_taken(session: AsyncSession, room_id: int, check_in: date, check_out: date) -> list[date]:
    """Confirmed-occupied nights for a room in [check_in, check_out)."""
    result = await session.exec(
        select(RoomNight.night_date).where(
            RoomNight.room_id == room_id,
            RoomNight.night_date >= check_in,
            RoomNight.night_date < check_out,   # checkout day is not occupied
        )
    )
    return list(result.all())

async def _get_room_type(session: AsyncSession, name: str) -> RoomType:
    result = await session.exec(
        select(RoomType).where(RoomType.name == name)
    )
    room_type = result.first()
    if room_type is None:
        raise RoomTypeMissing(f"Room type '{name}' not found")
    return room_type


async def update_room_type(
    session: AsyncSession, name: str, data: RoomTypeUpdate
) -> RoomType:
    room_type = await _get_room_type(session, name)
    patch = data.model_dump(exclude_unset=True)
    room_type.sqlmodel_update(patch)

    session.add(room_type)
    await session.commit()
    await session.refresh(room_type)
    return room_type
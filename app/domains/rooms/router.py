from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis import asyncio as aioredis
from sse_starlette.sse import EventSourceResponse

from app.core.permissions import (
    require_guest_or_receptionist,
    require_housekeeper,
    require_manager,
)
from app.core.rate_limit import limiter
from app.db.session import SessionDep
from app.domains.rooms.models import Room, RoomState
from app.domains.rooms.schemas import (
    AvailableRoomResponse,
    OccupancyReport,
    RoomDashboardRead,
    RoomResponse,
    RoomTypeOut,
    RoomTypeUpdate,
)
from app.domains.rooms.service import (
    RoomTypeMissing,
    get_available_rooms,
    get_occupancy_report,
    get_rooms,
    mark_room_clean,
    search_available_rooms,
    update_room_type,
)
from app.domains.rooms.streaming import room_event_generator, unavailable_events
from app.domains.users.models import User

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.get("/", response_model=list[RoomDashboardRead])
async def get_all_rooms(
    session: SessionDep,
    room_state: Annotated[RoomState | None, Query(description="Filter by housekeeping state: clean|dirty")] = None,
) -> list[Room]:
    return await get_rooms(session, room_state=room_state)


@router.get(
    "/available",
    response_model=list[RoomResponse],
)
async def get_available_rooms_for_day(
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
    room_date: Annotated[date | None, Query(description="Date to check room availability. Defaults to today.")] = None,
    room_type: Annotated[str | None, Query(description="Optional room type")] = None,
) -> list[RoomResponse]:
    rooms = await get_available_rooms(
        session=session,
        room_date=room_date,
        room_type=room_type,
    )

    return [
        RoomResponse(id=room.id, room_type=room.room_type, is_available=room.is_available)
        for room in rooms
    ]

@router.get("/search", response_model=list[AvailableRoomResponse])
async def search_rooms(
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
    check_in: Annotated[date, Query(description="Check-in date")],
    check_out: Annotated[date, Query(description="Check-out date")],
    room_type: Annotated[str, Query(description="Room type to search for")],
) -> list[AvailableRoomResponse]:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-out date must be after check-in date.",
        )

    rooms = await search_available_rooms(
        session=session,
        check_in=check_in,
        check_out=check_out,
        room_type=room_type,
    )

    return [
        AvailableRoomResponse(
            id=room.id,
            room_type=room.room_type,
        )
        for room in rooms
    ]

@router.get("/occupancy", response_model=OccupancyReport)
async def occupancy_report(
    session: SessionDep,
    _: Annotated[User, Depends(require_manager)],
    report_date: Annotated[date, Query(description="Date for the occupancy report")],
) -> OccupancyReport:
    return await get_occupancy_report(
        session=session,
        report_date=report_date,
    )

@router.patch("/{room_id}/clean", response_model=RoomResponse)
async def mark_clean(
    room_id: Annotated[
        int,
        Path(gt=0),
    ],
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_housekeeper),
    ],
) -> RoomResponse:
    try:
        room = await mark_room_clean(room_id=room_id, session=session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
   
    return RoomResponse(id=room.id, room_type=room.room_type, is_available=room.is_available)

@router.patch("/room-types/{name}", response_model=RoomTypeOut)
async def patch_room_type(
    name: Annotated[str,Path(min_length=3, max_length=128)],
    data: RoomTypeUpdate,
    session: SessionDep,
    _: Annotated[User, Depends(require_manager)]
):
    if not data.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail="Provide at least one of: base_rate, capacity"
        )

    try:
        return await update_room_type(
            session=session, name=name, 
            data=data
        )
    except RoomTypeMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/stream")
@limiter.exempt  # long-lived SSE: must not count against the 10/min rate limit
async def stream_rooms(request: Request):
    """Live changes only. Snapshot comes from GET /rooms (Postgres)"""
    client: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        return EventSourceResponse(unavailable_events(), send_timeout=30)
    return EventSourceResponse(
        room_event_generator(request.app.state.redis, request), send_timeout=30
    )

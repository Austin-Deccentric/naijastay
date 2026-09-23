from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.core.permissions import (
    require_guest_or_receptionist,
    require_manager,
)
from app.core.rate_limit import limiter
from app.db.session import SessionDep
from app.domains.rooms.models import RoomState, RoomType
from app.domains.rooms.schemas import (
    AvailableRoomResponse,
    RoomDashboardRead,
    RoomResponse,
    RoomTypeOut,
    RoomTypeUpdate,
)
from app.domains.rooms.service import (
    RoomTypeMissing,
    get_available_rooms,
    get_rooms,
    search_available_rooms,
    update_room_type,
)
from app.domains.rooms.streaming import room_event_generator
from app.domains.users.models import User

router = APIRouter(
    prefix="/rooms",
    tags=["Rooms"],
)


@router.get("/", response_model=list[RoomDashboardRead])
async def get_all_rooms(
    *,
    room_state: Annotated[RoomState | None, Query(description="Filter by housekeeping state: clean|dirty")] = None,
    session: SessionDep
):
    return await get_rooms(session, room_state=room_state)



@router.get(
    "/available",
    response_model=list[RoomResponse],
)
async def get_available_rooms_for_day(
    *,
    room_date: Annotated[date | None, Query(description="Date to check room availability. Defaults to today.")] = None,
    room_type: Annotated[str | None, Query(description="Optional room type")] = None,
    session: SessionDep,
) -> list[RoomResponse]:

    rooms = await get_available_rooms(
        session=session,
        room_date=room_date,
        room_type=room_type,
    )

    return [
        RoomResponse(
            id=room.id,
            room_type=room.room_type,
            is_available=room.is_available,
        )
        for room in rooms
    ]


@router.get("/search", response_model=list[AvailableRoomResponse])
async def search_rooms(check_in: Annotated[date, Query(description="Check-in date")],
    check_out: Annotated[date, Query(description="Check-out date")],
    room_type: Annotated[str, Query(description="Room type to search for"),],
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
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


room_types_router = APIRouter(prefix="/room-types",tags=["Room Types"])


@room_types_router.patch("/{name}", response_model=RoomTypeOut)
async def patch_room_type(name: Annotated[str, Path(min_length=3, max_length=128),
    ],
    data: RoomTypeUpdate,
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_manager),
    ],
) -> RoomType:

    if not data.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of: base_rate, capacity",
        )

    try:
        return await update_room_type(
            session=session,
            name=name,
            data=data,
        )

    except RoomTypeMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.get("/stream")
@limiter.exempt  # long-lived SSE: must not count against the 10/min rate limit
async def stream_rooms(request: Request):
    """Live chnages only. Snapshot comes from GET /rooms (Postgres)"""
    return EventSourceResponse(
        room_event_generator(request.app.state.redis, request), send_timeout=30
    )
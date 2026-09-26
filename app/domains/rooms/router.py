from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from redis import asyncio as aioredis
from sse_starlette.sse import EventSourceResponse

from app.core.permissions import (
    require_guest_or_receptionist,
    require_housekeeper,
    require_manager,
)
from app.core.rate_limit import limiter
from app.core.response import ApiResponse
from app.db.session import SessionDep
from app.domains.rooms.models import RoomState
from app.domains.rooms.schemas import (
    AvailableRoomResponse,
    OccupancyReport,
    RoomDashboardRead,
    RoomResponse,
    RoomTypeOut,
    RoomTypeUpdate,
)
from app.domains.rooms.service import (
    _ROOMS_ADAPTER,
    _SEARCH_ADAPTER,
    RoomTypeMissing,
    get_available_rooms,
    get_occupancy_report,
    get_rooms,
    mark_room_clean,
    search_available_rooms,
    update_room_type,
)
from app.domains.rooms.streaming import (
    publish_booking_room,
    room_event_generator,
    unavailable_events,
)
from app.domains.users.models import User
from app.integrations.cache import (
    ROOMS_LIST_TTL,
    ROOMS_SEARCH_TTL,
    get_or_set_json,
    make_key,
)
from app.integrations.redis import RedisDep

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.get("/", response_model=list[RoomDashboardRead])  # for docs only
async def get_all_rooms(
    session: SessionDep,
    redis: RedisDep,
    room_state: Annotated[
        RoomState | None,
        Query(
            description="Filter by housekeeping state: clean | dirty",
            examples=["clean"],
        ),
    ] = None,
) -> Response:
    async def producer() -> str:
        rooms = await get_rooms(session, room_state=room_state)
        return _ROOMS_ADAPTER.dump_json(
            _ROOMS_ADAPTER.validate_python(rooms)
        ).decode()

    cached = await get_or_set_json(
        redis,
        make_key("rooms", "list", room_state.value if room_state else "all"),
        ROOMS_LIST_TTL,
        producer,
    )
    return Response(content=cached, media_type="application/json")


@router.get(
    "/available",
    response_model=ApiResponse[list[RoomResponse]],
)
async def get_available_rooms_for_day(
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
    room_date: Annotated[
        date | None,
        Query(
            description="Date to check room availability. Defaults to today.",
            examples=["2026-09-25"],
        ),
    ] = None,
    room_type: Annotated[
        str | None,
        Query(
            description="Optional room type",
            examples=["standard", "deluxe", "executive-suite"],
        ),
    ] = None,
) -> ApiResponse[list[RoomResponse]]:
    rooms = await get_available_rooms(
        session=session,
        room_date=room_date,
        room_type=room_type,
    )

    return ApiResponse(
        status="success",
        message="Available rooms retrieved.",
        data=[
            RoomResponse(id=room.id, room_type=room.room_type, is_available=room.is_available)
            for room in rooms
        ],
    )

@router.get("/search", response_model=list[AvailableRoomResponse])
async def search_rooms(
    session: SessionDep,
    redis: RedisDep,
    _: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
    check_in: Annotated[date, Query(description="Check-in date", examples=["2026-09-25"])],
    check_out: Annotated[date, Query(description="Check-out date", examples=["2026-09-27"])],
    room_type: Annotated[str, Query(description="Room type to search for", examples=["standard", "deluxe", "executive-suite"])]
) -> Response:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-out date must be after check-in date.",
        )

    async def producer() -> str:
        rooms = await search_available_rooms(
            session=session,
            check_in=check_in,
            check_out=check_out,
            room_type=room_type,
        )
        return _SEARCH_ADAPTER.dump_json(
            _SEARCH_ADAPTER.validate_python(rooms)
        ).decode()
        
    cached = await get_or_set_json(
        redis,
        make_key("rooms", "search", check_in.isoformat(), check_out.isoformat(), room_type),
        ROOMS_SEARCH_TTL,
        producer
    )
    return Response(content=cached, media_type="application/json")

@router.get("/occupancy", response_model=ApiResponse[OccupancyReport])
async def occupancy_report(
    session: SessionDep,
    _: Annotated[User, Depends(require_manager)],
    report_date: Annotated[
        date | None,
        Query(
            description="Date for the occupancy report",
            examples=["2026-09-25"],
        ),
    ] = None,
) -> ApiResponse[OccupancyReport]:
    report = await get_occupancy_report(
        session=session,
        report_date=report_date,
    )
    return ApiResponse(
        status="success",
        message="Occupancy report generated.",
        data=report,
    )

@router.patch("/{room_id}/clean", response_model=ApiResponse[RoomResponse])
async def mark_clean(
    room_id: Annotated[
        int,
        Path(gt=0),
    ],
    session: SessionDep,
    request: Request,
    _: Annotated[
        User,
        Depends(require_housekeeper),
    ],
) -> ApiResponse[RoomResponse]:
    try:
        room, already_clean = await mark_room_clean(room_id=room_id, session=session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await publish_booking_room(request, session, room.id)
    return ApiResponse(
        status="success",
        message="Room already clean." if already_clean else "Room marked clean.",
        data=RoomResponse(id=room.id, room_type=room.room_type, is_available=room.is_available),
    )

@router.patch("/room-types/{name}", response_model=ApiResponse[RoomTypeOut])
async def patch_room_type(
    name: Annotated[str,Path(min_length=3, max_length=128)],
    data: RoomTypeUpdate,
    session: SessionDep,
    _: Annotated[User, Depends(require_manager)]
) -> ApiResponse[RoomTypeOut]:
    if not data.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail="Provide at least one of: base_rate, capacity"
        )

    try:
        room_type = await update_room_type(
            session=session, name=name, 
            data=data
        )
    except RoomTypeMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return ApiResponse(
        status="success",
        message="Room type updated.",
        data=RoomTypeOut(
            name=room_type.name,
            base_rate=room_type.base_rate,
            capacity=room_type.capacity,
        ),
    )


@router.get("/stream")
@limiter.exempt  # long-lived SSE: must not count against the 10/min rate limit
async def stream_rooms(
    request: Request,
    _: Annotated[User, Depends(require_manager)]
):
    """Live changes only. Snapshot comes from GET /rooms (Postgres)"""
    client: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        return EventSourceResponse(unavailable_events(), send_timeout=30)
    return EventSourceResponse(
        room_event_generator(request.app.state.redis, request), send_timeout=30
    )

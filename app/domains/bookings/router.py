from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.core.permissions import require_guest, require_guest_or_receptionist
from app.core.rate_limit import limiter
from app.db.session import SessionDep
from app.domains.bookings.models import Holds
from app.domains.bookings.schema import BookingCreate, BookingOut
from app.domains.bookings.service import (
    BadDates,
    BookingError,
    GuestNotFound,
    HoldExpired,
    HoldMismatch,
    HoldMissing,
    NotAGuest,
    RoomMissing,
    RoomUnavailable,
    create_booking,
)
from app.domains.rooms.service import get_room
from app.domains.users.models import User

_ERROR_STATUS = {
    RoomMissing: status.HTTP_404_NOT_FOUND,
    GuestNotFound: status.HTTP_404_NOT_FOUND,
    HoldMissing: status.HTTP_409_CONFLICT,
    RoomUnavailable: status.HTTP_409_CONFLICT,
    HoldMismatch: status.HTTP_403_FORBIDDEN,
    HoldExpired: status.HTTP_410_GONE,
    BadDates: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NotAGuest: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


router = APIRouter(prefix="/bookings", tags=["Bookings"])
root_router = APIRouter(tags=["Holds"])

@root_router.post("/holds/{room_id}")
async def hold_room(
    room_id: Annotated[int, Path(gt=0)],
    session: SessionDep,
    guest:Annotated[User, Depends(require_guest)]
) -> Holds:
    try: 
        room = await get_room(
            room_id=room_id, 
            session=session
        )
    except ValueError as exec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exec)
        ) from exec

    if not room.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room is not available"
        )

    registered_hold = Holds(
        room_id=room_id,
        guest_email=guest.email,
    )

    session.add(registered_hold)
    await session.commit()
    await session.refresh(registered_hold)
    
    return registered_hold
    

@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def book_room(
    request: Request,
    data: BookingCreate,
    session: SessionDep,
    client: Annotated[User, Depends(require_guest_or_receptionist)],
):
    try:
        return await create_booking(session=session, data=data, client=client)
    except BookingError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(
                type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=str(exc),
        ) from exc

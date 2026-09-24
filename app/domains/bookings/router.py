from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.core.permissions import (
    require_guest,
    require_guest_or_receptionist,
    require_receptionist,
)
from app.db.session import SessionDep
from app.domains.bookings.models import Hold
from app.domains.bookings.schema import (
    BookingCreate,
    BookingOut,
    CheckInOut,
    CheckOutOut,
)
from app.domains.bookings.service import (
    AlreadyCheckedIn,
    AlreadyCheckedOut,
    BadDates,
    BookingError,
    BookingNotCheckedIn,
    BookingNotConfirmed,
    BookingNotFound,
    CheckInDateMismatch,
    CheckOutDateMismatch,
    GuestNotFound,
    HoldExpired,
    HoldMismatch,
    HoldMissing,
    NotAGuest,
    RateMissing,
    RoomMissing,
    RoomUnavailable,
    check_existing_hold,
    check_in_guest,
    check_out_guest,
    create_booking,
)
from app.domains.rooms.service import get_room
from app.domains.rooms.streaming import publish_booking_room
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
    RateMissing: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


router = APIRouter(
    prefix="/bookings",
    tags=["Bookings"],
)

root_router = APIRouter(tags=["Holds"])

@root_router.post("/holds/{room_id}", status_code=status.HTTP_201_CREATED)
async def hold_room(
    room_id: Annotated[int, Path(gt=0)],
    session: SessionDep,
    guest: Annotated[
        User,
        Depends(require_guest),
    ],
) -> Hold:
    try:
        room = await get_room(room_id=room_id, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not room.is_available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room is not available")

    is_held = await check_existing_hold(session, room_id)
    if is_held:
        raise HTTPException(status_code=409, detail="Room already held")
        
    registered_hold = Hold(room_id=room_id, guest_email=guest.email)

    session.add(registered_hold)

    await session.commit()
    await session.refresh(registered_hold)

    return registered_hold


@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def book_room(
    data: BookingCreate,
    session: SessionDep,
    client: Annotated[
        User,
        Depends(require_guest_or_receptionist),
    ],
):
    try:
        return await create_booking(
            session=session,
            data=data,
            client=client,
        )
    except BookingError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(
                type(exc),
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
            detail=str(exc),
        ) from exc


@router.post("/{booking_id}/check-in", response_model=CheckInOut)
async def check_in(
    booking_id: Annotated[
        int,
        Path(gt=0),
    ],
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_receptionist),
    ],
    request: Request,
) -> CheckInOut:
    try:
        booking = await check_in_guest(session=session, booking_id=booking_id)
    except BookingNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BookingNotConfirmed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CheckInDateMismatch as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except AlreadyCheckedIn as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RoomMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await publish_booking_room(request, session, booking.room_id)

    return CheckInOut(
        booking_id=booking.booking_id,
        guest_email=booking.guest_email,
        room_id=booking.room_id,
        check_in=booking.check_in,
        check_out=booking.check_out,
        booking_status=booking.booking_status.value,
        room_available=False,
    )

@router.post("/{booking_id}/check-out", response_model=CheckOutOut)
async def check_out(
    booking_id: Annotated[
        int,
        Path(gt=0),
    ],
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_receptionist),
    ],
    request: Request,
) -> CheckOutOut:
    try:
        booking = await check_out_guest(
            session=session,
            booking_id=booking_id,
        )
    except BookingNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BookingNotCheckedIn as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CheckOutDateMismatch as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
   
    except RoomMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await publish_booking_room(request, session, booking.room_id)

    return CheckOutOut(
        booking_id=booking.booking_id,
        guest_email=booking.guest_email,
        room_id=booking.room_id,
        check_out=booking.check_out,
        booking_status=booking.booking_status.value,
        room_available=False,
        room_state="dirty",
    )
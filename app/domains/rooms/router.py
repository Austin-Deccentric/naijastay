from datetime import date
from typing import Annotated

from app.core.permissions import require_roles
from app.db.session import SessionDep
from app.domains.rooms.schemas import AvailableRoomResponse
from app.domains.rooms.service import search_available_rooms
from app.domains.users.models import User, UserRole
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(
    prefix="/rooms",
    tags=["Rooms"],
)

rooms_user_dependency = Depends(
    require_roles(
        UserRole.GUEST,
        UserRole.RECEPTIONIST,
    )
)

@router.get("/search", response_model=list[AvailableRoomResponse])
async def search_rooms(
    check_in: Annotated[date, Query(description="Check-in date")],
    check_out: Annotated[date, Query(description="Check-out date")],
    room_type: Annotated[str, Query(description="Room type to search for")],
    session: SessionDep,
    current_user: User = rooms_user_dependency,
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
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.core.permissions import require_manager
from app.db.session import SessionDep
from app.domains.rooms.models import RoomTypes
from app.domains.rooms.schema import RoomTypeOut, RoomTypeUpdate
from app.domains.rooms.service import RoomTypeMissing, update_room_type
from app.domains.users.models import User

router = APIRouter(prefix="/room-types", tags=["Room Types"])


@router.patch("/{name}", response_model=RoomTypeOut)
async def patch_room_type(
    name: Annotated[str, Path(min_length=3, max_length=128)],
    data: RoomTypeUpdate,
    session: SessionDep,
    _: Annotated[User, Depends(require_manager)],
) -> RoomTypes:
    if not data.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of: base_rate, capacity",
        )
    try:
        return await update_room_type(session=session, name=name, data=data)
    except RoomTypeMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

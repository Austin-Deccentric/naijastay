from app.domains.rooms.models import RoomState
from pydantic import BaseModel, Field


class RoomResponse(BaseModel):
    id: int
    room_type: str
    is_available: bool
    room_state: RoomState

class AvailableRoomResponse(BaseModel):
    id: int
    room_type: str

class RoomTypeOut(BaseModel):
    name: str
    base_rate: float
    capacity: int

class RoomTypeUpdate(BaseModel):
    base_rate: float | None = Field(
        default=None,
        gt=0,
    )

    capacity: int | None = Field(
        default=None,
        gt=0,
    )
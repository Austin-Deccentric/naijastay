from datetime import date
from enum import Enum

from sqlmodel import Field, SQLModel


class RoomState(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"

class RoomNight(SQLModel, table=True):
    __tablename__ = "room_nights"
    
    room_id: int = Field(primary_key=True, foreign_key="rooms.id")
    night_date: date = Field(primary_key=True)
    booking_id: int = Field(foreign_key="bookings.booking_id")    
    room_state: RoomState = RoomState.CLEAN



class RoomType(SQLModel, table=True):
    __tablename__ = "room_types"
    
    name: str = Field(primary_key=True, min_length=3, max_length=128)
    base_rate: float
    capacity: int


class Room(SQLModel, table=True):
    __tablename__ = "rooms"
    
    id: int | None = Field(default=None, primary_key=True)
    room_type: str = Field(foreign_key="room_types.name")
    is_available: bool = Field(default=True)
    room_state: RoomState = Field(default=RoomState.CLEAN)
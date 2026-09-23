from datetime import date

from pydantic import BaseModel, Field, PositiveFloat, model_validator


class RoomSearchRequest(BaseModel):
    check_in: date
    check_out: date
    room_type: str

    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("Check-out date must be after check-in date.")
        return self

class RoomResponse(BaseModel):
    id: int
    room_type: str
    is_available: bool

class AvailableRoomResponse(BaseModel):
    id: int
    room_type: str

class RoomTypeOut(BaseModel):
    name: str
    base_rate: int
    capacity: int

class RoomTypeUpdate(BaseModel):
    base_rate: PositiveFloat | None = None
    capacity: PositiveFloat | None = None

    model_config = {"extra": "forbid"}
    
class OccupancyReport(BaseModel):
    report_date: date
    total_rooms: int = Field(ge=0)
    occupied_rooms: int = Field(ge=0)
    available_rooms: int = Field(ge=0)
    occupancy_percentage: float = Field(ge=0, le=100)
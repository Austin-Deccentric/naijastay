from datetime import date

from pydantic import BaseModel, model_validator


class RoomSearchRequest(BaseModel):
    check_in: date
    check_out: date
    room_type: str

    @model_validator(mode="after")
    async def validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("Check-out date must be after check-in date.")

        return self


class AvailableRoomResponse(BaseModel):
    id: int
    room_type: str
from datetime import date

from pydantic import BaseModel, EmailStr, Field, model_validator

# class HoldCreate(BaseModel):
#     room_id: int = Field(gt=0)
    
    

class BookingCreate(BaseModel):
    guest_email: EmailStr | None = None # requied only for receptionist
    room_id: int = Field(gt=0)
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def check_dates(self) -> BookingCreate:
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in.")
        return self

class BookingOut(BookingCreate):
    booking_id: int
    total_amount: float
    
class CheckInOut(BaseModel):
    booking_id: int
    guest_email: EmailStr
    room_id: int
    check_in: date
    check_out: date
    booking_status: str
    room_available: bool
    
class CheckOutOut(BaseModel):
    booking_id: int
    guest_email: EmailStr
    room_id: int
    check_out: date
    booking_status: str
    room_available: bool
    room_state: str
    
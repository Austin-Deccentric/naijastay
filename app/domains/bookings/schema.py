from datetime import date

from pydantic import BaseModel, EmailStr, Field

# class HoldCreate(BaseModel):
#     room_id: int = Field(gt=0)
    
    

class BookingCreate(BaseModel):
    guest_email: EmailStr | None = None # requied only for receptionist
    room_id: int = Field(gt=0)
    check_in: date
    check_out: date


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
    
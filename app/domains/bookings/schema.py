from datetime import date

from pydantic import BaseModel, EmailStr, Field


class BookingCreate(BaseModel):
    guest_email: EmailStr 
    room_id: int 
    check_in: date
    num_of_nights: int = Field(gt=0)
    total_amount: float
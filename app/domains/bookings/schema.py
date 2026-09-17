from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel


class Holds(SQLModel, table=True):
    room_id: int = Field(primary_key=True, foreign_key="rooms.id")
    guest_email: EmailStr = Field(foreign_key="users.email")
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))
    consumed: bool = Field(default=False)


class BookingStatus(str, Enum):
    HOLD = "hold"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Bookings(SQLModel, table=True):
    booking_id: int = Field(primary_key=True)
    guest_email: EmailStr = Field(foreign_key="users.email")
    room_id: int = Field(foreign_key="rooms.id")
    check_in: datetime
    check_out: datetime
    booking_status: BookingStatus
    total_amount: float

    guest:Users = Relationship(back_populates="bookings")

    
from datetime import UTC, date, datetime, timedelta
from enum import Enum

from sqlmodel import DateTime, Field, SQLModel, text


class Holds(SQLModel, table=True):

    room_id: int = Field(primary_key=True, foreign_key="rooms.id", index=True)
    guest_email: str = Field(foreign_key="users.email")
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10), 
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
        index=True
    )
    consumed: bool = Field(default=False)


class BookingStatus(str, Enum):
    # HOLD = "hold"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(SQLModel, table=True):
    __tablename__ = "bookings"
    
    booking_id: int | None = Field(default=None, primary_key=True)
    guest_email: str = Field(foreign_key="users.email")
    room_id: int = Field(foreign_key="rooms.id")
    check_in: date
    check_out: date
    booking_status: BookingStatus
    total_amount: float
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )

    # guest:User = Relationship(back_populates="bookings")


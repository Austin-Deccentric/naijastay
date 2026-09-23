from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import (
    Column,
    Computed,
    DateTime,
    Field,
    Relationship,
    SQLModel,
    String,
    text,
)

if TYPE_CHECKING:
    from app.domains.rooms.models import Room, RoomNight
    from app.domains.users.models import User


HOLD_TIME = 10


class Hold(SQLModel, table=True):
    __tablename__ = "holds"

    room_id: int = Field(primary_key=True, foreign_key="rooms.id", index=True)

    guest_email: str = Field(foreign_key="users.email")

    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
        + timedelta(minutes=HOLD_TIME),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": text("CURRENT_TIMESTAMP"),
        },
        index=True,
    )

    consumed: bool = Field(default=False)

class BookingStatus(str, Enum):
    HOLD = "hold"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
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

    ref: str | None = Field(default=None, sa_column=Column(String(32), Computed("'BOOK-' || booking_id", persisted=True), unique=True, index=True))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": text("CURRENT_TIMESTAMP"),
        },
    )

    guest: "User" = Relationship(back_populates="bookings")

    room: "Room" = Relationship(back_populates="bookings")

    room_nights: list["RoomNight"] = Relationship(back_populates="booking")
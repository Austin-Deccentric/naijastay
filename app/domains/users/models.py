from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import DateTime, Field, Relationship, SQLModel, text

if TYPE_CHECKING:
    from app.domains.bookings.models import Booking


class UserRole(str, Enum):
    GUEST = "guest"
    RECEPTIONIST = "receptionist"
    HOUSEKEEPER = "housekeeper"
    MANAGER = "manager"

class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, nullable=False, max_length=255)
    password_hash: str = Field(nullable=False, max_length=255)
    role: UserRole = Field(default=UserRole.GUEST, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )

    # One user can have many bookings
    bookings: list["Booking"] = Relationship(back_populates="guest")
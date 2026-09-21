from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class PaymentMethod(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"

class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    
    id: int | None = Field(primary_key=True)
    booking_id: int = Field(foreign_key="bookings.booking_id", unique=True, nullable=False)
    amount: float
    method: PaymentMethod
    provider_event_id: str = Field(unique=True, max_length=64, foreign_key="processed_events.event_id")
    recorded_by: int | None = Field(foreign_key="users.id") 
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProcessedEvent(SQLModel, table=True):
    """For the webhook"""
    __tablename__ = "processed_events"
    
    event_id: str = Field(primary_key=True)
    reference: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


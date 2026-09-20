from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class PaymentMethod(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"

class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    
    id: int | None = Field(primary_key=True)
    booking_id: int = Field(foreign_key="bookings.id", unique=True)
    amount: float
    method: PaymentMethod
    recorded_by: int = Field(foreign_key="users.id") 
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProcessedEvent(SQLModel, table=True):
    """For the webhook"""
    __tablename__ = "processed_events"
    
    event_id: int = Field(primary_key=True)
    reference: str
    processed_at: datetime


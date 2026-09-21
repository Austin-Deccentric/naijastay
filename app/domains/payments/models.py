from datetime import UTC, datetime
from enum import Enum

from pydantic import PositiveFloat
from sqlmodel import Field, SQLModel


class PaymentMethod(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"

class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    
    id: int | None = Field(default=None, primary_key=True)
    booking_id: int = Field(foreign_key="bookings.booking_id", unique=True, nullable=False)
    amount: PositiveFloat
    currency: str = Field(default="NGN", max_length=8)
    method: PaymentMethod =  Field(default=PaymentMethod.ONLINE)
    provider_event_id: str = Field(unique=True, max_length=64, foreign_key="processed_events.event_id")
    recorded_by: int | None = Field(foreign_key="users.id") 
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paid_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ProcessedEvent(SQLModel, table=True):
    """For the webhook"""
    __tablename__ = "processed_events"
    
    event_id: str = Field(primary_key=True)
    event_type: str = Field(max_length=64)
    reference: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


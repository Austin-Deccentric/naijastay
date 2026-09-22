from datetime import datetime

from pydantic import BaseModel, Field
from pydantic.types import PositiveFloat


class PaymentWebhookEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    type: str
    reference: str = Field(min_length=1, max_length=32)
    amount: PositiveFloat = Field(gt=0)            
    currency: str = "NGN"
    paid_at: datetime


class PayOut(BaseModel):
    booking_id: int
    reference: str
    amount: float
    booking_status: str
    method: str = "online"


class OfflinePaymentIn(BaseModel):
    """Body for recording a staff-collected payment. Exact amount only."""

    amount: PositiveFloat = Field(gt=0)
    currency: str = "NGN"

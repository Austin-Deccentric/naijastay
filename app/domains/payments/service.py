import asyncio
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.bookings.service import (
    BookingError,
    BookingMissing,
    HoldGone,
    NotProcessing,
    NotYours,
)
from app.domains.payments.schema import PaymentWebhookEvent, PayOut
from app.domains.users.models import User

SCRIPT = Path(__file__).resolve().parents[3] / "mock_payment_provider.py"
WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhooks/payment"


async def pay_booking(booking_id: int, guest: User, session: AsyncSession) -> PayOut:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise BookingMissing("Booking not found.")
    if booking.booking_status != BookingStatus.PROCESSING:
        raise NotProcessing("Only processing bookings can be paid for.")
    if booking.guest_email != guest.email:
        raise NotYours("You can only pay for your own booking.")

    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(SCRIPT),
        "--url", WEBHOOK_URL,
        "--secret", settings.webhook_secret,
        "--reference", booking.ref,
        "--amount", str(round(booking.total_amount)),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    await proc.wait()          # script runs, webhook gets served meanwhile (separate process)
    if proc.returncode != 0:
        raise HTTPException(502, "Payment provider unreachable.")  # or a BookingError

    await session.refresh(booking)
    return PayOut(booking_id=booking.booking_id, reference=booking.ref,
                  amount=booking.total_amount,
                  booking_status=booking.booking_status.value)

import asyncio
import hashlib
import hmac
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.bookings.service import (
    BookingMissing,
    HoldGone,
    NotProcessing,
    NotYours,
    RoomUnavailable,
)
from app.domains.payments.models import Payment, PaymentMethod, ProcessedEvent
from app.domains.payments.schema import PaymentWebhookEvent, PayOut
from app.domains.rooms.models import Room, RoomNight
from app.domains.users.models import User

logger = logging.getLogger("naijastay")

SCRIPT = Path(__file__).resolve().parents[3] / "mock_payment_provider.py"
WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhooks/payment"

class WebhookError(Exception):
    """Base for webhook failures (mirrors BookingError pattern)."""


class WebhookAuthError(WebhookError): ...      # -> 401
class AmountMismatch(WebhookError): ...        # -> 422, wrong money, never confirm


async def pay_booking(
    booking_id: int, 
    guest: User, 
    session: AsyncSession
) -> tuple[PayOut, bool]:
    """Pay for a booking. Returns (payout, already_paid).

    already_paid is True when the booking was already CONFIRMED, so the
    router can message the idempotent replay distinctly.
    """
    booking = await session.get(Booking, booking_id)
   
    if booking is None:
        raise BookingMissing("Booking not found.")

    if booking.guest_email != guest.email: raise NotYours("You can only pay for your own booking.")
    if booking.booking_status == BookingStatus.CONFIRMED:
        return PayOut(booking_id=booking.booking_id, reference=booking.ref,
                      amount=booking.total_amount,
                      booking_status=booking.booking_status.value), True
    if booking.booking_status != BookingStatus.PROCESSING:
        raise NotProcessing("Only processing bookings can be paid for, ")
    

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
    if booking.booking_status == BookingStatus.CANCELLED:
        raise HoldGone("Hold expired before payment; booking cancelled.")
    if booking.booking_status != BookingStatus.CONFIRMED:
        raise NotProcessing("Payment attempt did not confirm the booking.")
    return PayOut(booking_id=booking.booking_id, reference=booking.ref,
                  amount=booking.total_amount,
                  booking_status=booking.booking_status.value), False


def verify_signature(raw_body: bytes, signature: str) -> None:
    """ Verify the signature passed in the header """
    expected = hmac.new(settings.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise WebhookAuthError("Invalid webhook signature.")

def _add_room_nights(session: AsyncSession, booking: Booking) -> None:
    """Stage one RoomNight per night in [check_in, check_out). Shared by
    the online (webhook) and offline confirm paths."""
    night = booking.check_in
    while night < booking.check_out:
        session.add(RoomNight(room_id=booking.room_id, night_date=night,
                              booking_id=booking.booking_id))
        night += timedelta(days=1)


async def record_offline_payment(
    session: AsyncSession,
    booking_id: int,
    staff: User,
    amount: float,
    currency: str = "NGN",
) -> Payment:
    """Record a staff-collected (cash/bank transfer) payment and confirm.

    Receptionist-only (enforced at the router). No hold is required, so
    walk-ins are confirmable. Exact amount only. Writes no ProcessedEvent
    row — those remain provider-only.
    """
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise BookingMissing("Booking not found.")
    if booking.booking_status != BookingStatus.PROCESSING:
        raise NotProcessing("Only processing bookings can be paid for.")
    if currency != "NGN" or abs(amount - booking.total_amount) > 0.01:
        raise AmountMismatch("Paid amount does not match booking total.")

    room = await session.get(Room, booking.room_id)
    if room is None:
        raise RoomUnavailable("Room for booking no longer exists.")

    booking.booking_status = BookingStatus.CONFIRMED
    _add_room_nights(session, booking)
    payment = Payment(booking_id=booking.booking_id, amount=amount,
                      currency=currency, method=PaymentMethod.OFFLINE,
                      provider_event_id=None, recorded_by=staff.id)
    session.add(payment)
    try:
        await session.commit()
        logger.info("Recorded offline %s for booking %s by %s",
                    amount, booking.booking_id, staff.email)
    except IntegrityError:
        await session.rollback()
        # Either a double-pay race (payments.booking_id unique) or a night
        # clash with another stay (room_nights PK). Offline writes no event
        # row, so unlike the webhook path there is no duplicate to return.
        raise RoomUnavailable(
            "Room is no longer available for these dates."
        )
    await session.refresh(payment)
    return payment


# Main payment and Booking confirmation logic flow
async def process_payment_event(session: AsyncSession, event: PaymentWebhookEvent) -> str:

    if await session.get(ProcessedEvent, event.event_id) is not None:
        return "duplicate"   

    if event.type != "payment.succeeded":
        session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                                   reference=event.reference))
        await session.commit()
        return "ignored"
        

    booking = (await session.exec(
        select(Booking).where(Booking.ref == event.reference).with_for_update()
    )).first()                              # row lock: second reader waits for first writer
    if booking is None:
        # NOTE: with_for_update found nothing, so no lock held; plain insert below.
        session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                                   reference=event.reference))
        await session.commit()
        return "orphan"                     # 200 so the provider stops retrying (log at router)

    if booking.booking_status == BookingStatus.CONFIRMED:
        session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                                   reference=event.reference))
        await session.commit()
        return "duplicate"
    if booking.booking_status != BookingStatus.PROCESSING:
        session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                                   reference=event.reference))
        await session.commit()
        return "duplicate"                  # CANCELLED stays cancelled

    if event.currency != "NGN" or abs(event.amount - booking.total_amount) > 0.01:
        logger.error("Amount mismatch on %s: event %s vs booking %s",
                            event.reference, event.amount, booking.total_amount)
        raise AmountMismatch("Paid amount does not match booking total.")

    hold = await session.get(Hold, booking.room_id)
    if (hold is None or hold.consumed
            or hold.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
            or hold.guest_email.strip().lower() != booking.guest_email.strip().lower()):
        booking.booking_status = BookingStatus.CANCELLED
        session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                                   reference=event.reference))
        await session.commit()
        logger.error("Paid booking %s lost its hold; cancelled, refund flow needed.",
                     event.reference)
        raise HoldGone("Hold expired before payment; booking cancelled.")

    # defensive check
    room = await session.get(Room, booking.room_id)
    if room is None:
        raise AmountMismatch("Room for booking no longer exists.") # TODO Chamge error raised

    booking.booking_status = BookingStatus.CONFIRMED
    await session.delete(hold)
    _add_room_nights(session, booking)

    # The event row must exist before the payment row: payments.provider_event_id
    # references processed_events.event_id, so flush the parent first.
    session.add(ProcessedEvent(event_id=event.event_id, event_type=event.type,
                               reference=event.reference))
    await session.flush()
    session.add(Payment(booking_id=booking.booking_id, amount=event.amount,
                        currency=event.currency, recorded_by=None,
                        provider_event_id=event.event_id,
                        paid_at=event.paid_at))

    try:
        await session.commit()
        logger.info("Confirmed %s %s for %s (event %s)",
                        event.amount, event.currency, event.reference, event.event_id)
    except IntegrityError:
        await session.rollback()
        if await session.get(ProcessedEvent, event.event_id) is not None:
            return "duplicate"              
        raise                               # genuine night clash -> 409
    return "confirmed"
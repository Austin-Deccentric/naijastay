import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import ValidationError
from sqlmodel import select

from app.core.permissions import require_guest, require_receptionist
from app.core.rate_limit import limiter
from app.db.session import SessionDep
from app.domains.bookings.models import Booking
from app.domains.bookings.service import (
    BookingError,
    BookingMissing,
    HoldGone,
    NotProcessing,
    NotYours,
    RoomUnavailable,
)
from app.domains.payments.schema import OfflinePaymentIn, PaymentWebhookEvent, PayOut
from app.domains.payments.service import (
    AmountMismatch,
    WebhookAuthError,
    WebhookError,
    pay_booking,
    process_payment_event,
    record_offline_payment,
    verify_signature,
)
from app.domains.rooms.streaming import publish_booking_room
from app.domains.users.models import User

logger = logging.getLogger("naijastay")
router = APIRouter(prefix="/payments", tags=["Payments"])

_PAY_STATUS = {BookingMissing: 404, NotProcessing: 409, NotYours: 403}
_OFFLINE_STATUS = {
    BookingMissing: 404,
    NotProcessing: 409,
    RoomUnavailable: 409,
    AmountMismatch: 422,
}
_ERROR_STATUS = {
    BookingMissing: 404,
    NotProcessing: 409,
    NotYours: 403,
    HoldGone: 409,
    WebhookAuthError: 401,
    AmountMismatch: 422,
}

@router.post("/pay/{booking_id}", response_model=PayOut)
@limiter.limit("5/minute")
async def pay_for_booking(
    request: Request,                                    
    booking_id: Annotated[int, Path(gt=0)],
    session: SessionDep,
    guest: Annotated[User, Depends(require_guest)],      # guests only, per spec
):
    """Run the mock provider script against this guest's booking."""
    try:
        return await pay_booking(booking_id, guest, session)
    except BookingError as exc:
        raise HTTPException(
            status_code=_PAY_STATUS.get(type(exc), 500), detail=str(exc)
        ) from exc


root_router = APIRouter(tags=["Webhooks"])


@router.post("/offline/{booking_id}", response_model=PayOut, status_code=status.HTTP_201_CREATED)
async def record_offline_payment_for_booking(
    request: Request,
    booking_id: Annotated[int, Path(gt=0)],
    data: OfflinePaymentIn,
    session: SessionDep,
    staff: Annotated[User, Depends(require_receptionist)],  # receptionists only
):
    """Record a cash/bank-transfer payment collected by front-desk staff.

    No hold required (walk-ins confirmable). Exact amount only. Writes no
    ProcessedEvent row — those remain provider-only.
    """
    try:
        payment = await record_offline_payment(
            session, booking_id, staff, amount=data.amount, currency=data.currency
        )
    except BookingError as exc:
        raise HTTPException(
            status_code=_OFFLINE_STATUS.get(type(exc), 500), detail=str(exc)
        ) from exc
    except WebhookError as exc:
        raise HTTPException(
            status_code=_OFFLINE_STATUS.get(type(exc), 500), detail=str(exc)
        ) from exc
    booking = await session.get(Booking, payment.booking_id)
    if booking is not None:
        await publish_booking_room(request, session, booking.room_id)
    return PayOut(
        booking_id=payment.booking_id,
        reference=booking.ref if booking and booking.ref else f"BOOK-{payment.booking_id}",
        amount=payment.amount,
        booking_status="confirmed",
        method=payment.method.value,
    )


@root_router.post("/api/v1/webhooks/payment")
@limiter.exempt                                            # webhooks must never 429
async def payment_webhook(request: Request, session: SessionDep):
    """Consume provider deliveries: verify seal, then confirm once."""
    raw = await request.body()                            # exact bytes for seal math
    try:
        verify_signature(raw, request.headers.get("X-Signature", ""))
    except WebhookAuthError as exc:
        logger.warning("Rejected webhook: bad signature")
        raise HTTPException(status_code=_ERROR_STATUS.get(type(exc), 500), detail=str(exc)) from exc
        
    try:
        event = PaymentWebhookEvent.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc.errors())) from exc

        
    try:
        result = await process_payment_event(session, event)
    except (BookingError, WebhookError) as exc:
        raise HTTPException(status_code=_ERROR_STATUS.get(type(exc), 500), detail=str(exc)) from exc
   
    if result == "confirmed":
        booking = (
            await session.exec(select(Booking).where(Booking.ref == event.reference))
        ).first()
        if booking is not None:
            await publish_booking_room(request, session, booking.room_id)

    if result == "orphan":
        logger.warning("Orphan webhook for unknown reference %s", event.reference)
    return {"status": result}
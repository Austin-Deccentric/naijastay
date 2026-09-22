import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.db.session import AsyncSessionMaker
from app.domains.bookings.models import HOLD_TIME, Booking, BookingStatus, Hold

logger = logging.getLogger("naijastay")


async def delete_expired_holds() -> int:
    """Delete expired holds and consumed holds. Returns rows removed."""
    now = datetime.now(UTC)
    async with AsyncSessionMaker() as session:
        result = await session.exec(
            select(Hold).where(
                (Hold.expires_at <= now) | (Hold.consumed == True)  
            )
        )
        stale = result.all()
        for hold in stale:
            await session.delete(hold)
        if stale:
            await session.commit()
            logger.info("Hold sweeper removed %d hold(s)", len(stale))
        return len(stale)


async def cancel_stale_processing(grace_minutes: int = 3) -> int:
    """Cancel abandoned PROCESSING bookings. Returns rows cancelled."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=grace_minutes + HOLD_TIME)
    today = now.date()
    async with AsyncSessionMaker() as session:
        result = await session.exec(
            select(Booking).where(
                Booking.booking_status == BookingStatus.PROCESSING,
                (Booking.created_at <= cutoff) | (Booking.check_in < today),
            )
        )
        stale = result.all()
        for booking in stale:
            booking.booking_status = BookingStatus.CANCELLED
            hold = await session.get(Hold, booking.room_id)
            if hold is not None and hold.guest_email.strip().lower() == booking.guest_email.strip().lower():
                await session.delete(hold)
        if stale:
            await session.commit()
            logger.info("Booking sweeper cancelled %d stale processing booking(s)", len(stale))
        return len(stale)

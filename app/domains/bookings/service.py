from datetime import UTC, date, datetime

from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.bookings.schema import BookingCreate
from app.domains.rooms.models import RoomType
from app.domains.rooms.service import get_room, nights_taken
from app.domains.users.models import User, UserRole
from app.domains.users.service import get_user_by_email
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


class BookingError(Exception):
    """Base for all booking failures."""
class RoomMissing(BookingError):
    pass
class RoomUnavailable(BookingError):
    pass
class HoldMissing(BookingError):
    pass
class HoldMismatch(BookingError):
    pass
class HoldExpired(BookingError):
    pass
class GuestNotFound(BookingError):
    pass
class NotAGuest(BookingError):
    pass
class BadDates(BookingError):
    pass
class RateMissing(BookingError):
    pass
class BookingNotFound(BookingError):
    pass
class BookingNotConfirmed(BookingError):
    pass
class AlreadyCheckedIn(BookingError):
    pass
class CheckInDateMismatch(BookingError):
    pass


async def _as_utc(value: datetime) -> datetime:
    return (
        value
        if value.tzinfo is not None
        else value.replace(tzinfo=UTC)
    )


async def create_booking(
    session: AsyncSession,
    data: BookingCreate,
    client: User,
) -> Booking:

    if client.role == UserRole.GUEST:
        guest_email = client.email

    else:
        if not data.guest_email:
            raise GuestNotFound(
                "guest_email is required when staff book for a guest."
            )

        guest_email = str(data.guest_email).strip().lower()

        guest = await get_user_by_email(
            session,
            guest_email,
        )

        if guest is None:
            raise GuestNotFound(
                "No user with that guest email."
            )

        if guest.role != UserRole.GUEST:
            raise NotAGuest(
                "Only guest accounts can be booked for."
            )

    if data.check_out <= data.check_in:
        raise BadDates(
            "check_out must be after check_in."
        )

    try:
        room = await get_room(
            room_id=data.room_id,
            session=session,
        )
    except ValueError as exc:
        raise RoomMissing(
            "Room not found."
        ) from exc

    if not room.is_available:
        raise RoomUnavailable(
            "Room is not available."
        )

    hold = await session.get(
        Hold,
        data.room_id,
    )

    if hold is None:
        raise HoldMissing(
            "No active hold for this room."
        )

    if hold.guest_email.strip().lower() != guest_email:
        raise HoldMismatch(
            "This hold belongs to a different guest."
        )

    if (
        hold.consumed
        or _as_utc(hold.expires_at) <= datetime.now(UTC)
    ):
        await session.delete(hold)
        await session.commit()

        raise HoldExpired(
            "Hold has expired."
        )

    nights = (
        data.check_out - data.check_in
    ).days

    taken = await nights_taken(
        session,
        data.room_id,
        data.check_in,
        data.check_out,
    )

    if taken:
        raise RoomUnavailable(
            f"Room already booked for: {taken}"
        )

    room_type = await session.get(
        RoomType,
        room.room_type,
    )

    if room_type is None:
        raise RateMissing(
            "Room type has no rate configured."
        )

    total = room_type.base_rate * nights

    booking = Booking(
        guest_email=guest_email,
        room_id=data.room_id,
        check_in=data.check_in,
        check_out=data.check_out,
        booking_status=BookingStatus.PROCESSING,
        total_amount=total,
    )

    session.add(booking)

    await session.commit()

    await session.refresh(booking)

    return booking


async def check_in_guest(
    session: AsyncSession,
    booking_id: int,
) -> Booking:

    booking = await session.get(
        Booking,
        booking_id,
    )

    if booking is None:
        raise BookingNotFound(
            "Booking not found."
        )

    if booking.booking_status != BookingStatus.CONFIRMED:
        raise BookingNotConfirmed(
            "Only confirmed bookings can be checked in."
        )

    today = date.today()

    if booking.check_in != today:
        raise CheckInDateMismatch(
            "Guest can only be checked in on the booking check-in date."
        )

    try:
        room = await get_room(
            room_id=booking.room_id,
            session=session,
        )
    except ValueError as exc:
        raise RoomMissing(
            "Room assigned to this booking was not found."
        ) from exc

    if not room.is_available:
        raise AlreadyCheckedIn(
            "Room is already occupied."
        )

    room.is_available = False

    session.add(room)

    await session.commit()

    await session.refresh(booking)

    return booking
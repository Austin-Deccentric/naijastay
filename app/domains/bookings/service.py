from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utc_today
from app.domains.bookings.models import Booking, BookingStatus, Hold
from app.domains.bookings.schema import BookingCreate
from app.domains.rooms.models import RoomState, RoomType
from app.domains.rooms.service import get_room, nights_taken
from app.domains.users.models import User, UserRole
from app.domains.users.service import get_user_by_email


class BookingError(Exception):
    """Base for all booking failures."""
class RoomMissing(BookingError): ...
class RoomUnavailable(BookingError): ...
class HoldMissing(BookingError): ...      # -> 409, no active hold
class HoldMismatch(BookingError): ...     # -> 403, hold belongs to someone else
class HoldExpired(BookingError): ...      # -> 410, hold gone (deleted first)
class GuestNotFound(BookingError): ...    # -> 404, receptionist's email unknown
class NotAGuest(BookingError): ...        # -> 422, email belongs to staff
class BadDates(BookingError): ...         # -> 422
class RateMissing(BookingError): ...      # -> 500, room_type has no rate row

class BookingMissing(BookingError): ...   # -> 404
class NotProcessing(BookingError): ...    # -> 409, not payable/confirmable
class NotYours(BookingError): ...         # -> 403,  booking
class HoldGone(BookingError): ...     
class BookingNotFound(BookingError):
    pass
class BookingNotConfirmed(BookingError):
    pass
class AlreadyCheckedIn(BookingError):
    pass
class CheckInDateMismatch(BookingError):
    pass
class BookingNotCheckedIn(BookingError):
    pass
class AlreadyCheckedOut(BookingError):
    pass
class CheckOutDateMismatch(BookingError):
    pass


def _as_utc(value: datetime) -> datetime:
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
            raise GuestNotFound("guest_email is required when staff book for a guest.")

        guest_email = str(data.guest_email).strip().lower()

        guest = await get_user_by_email(session, guest_email)

        if guest is None:
            raise GuestNotFound("No user with that guest email.")

        if guest.role != UserRole.GUEST:
            raise NotAGuest("Only guest accounts can be booked for.")

    if (data.check_out <= data.check_in) or (data.check_in < utc_today()):
        raise BadDates("check_out must be after check_in. and check_in cannot happen in the past")

    try:
        room = await get_room(room_id=data.room_id, session=session)
    except ValueError as exc:
        raise RoomMissing("Room not found.") from exc

    if not room.is_available:
        raise RoomUnavailable("Room is not available.")

    hold = await session.get(
        Hold,
        data.room_id,
    )

    if hold is None:
        raise HoldMissing("No active hold for this room.")

    if hold.guest_email.strip().lower() != guest_email:
        raise HoldMismatch(
            "This hold belongs to a different guest."
        )

    if (hold.consumed or _as_utc(hold.expires_at) <= datetime.now(UTC)):
        await session.delete(hold)
        await session.commit()

        raise HoldExpired("Hold has expired.")

    nights = (data.check_out - data.check_in).days

    taken = await nights_taken(
        session,
        data.room_id,
        data.check_in,
        data.check_out,
    )

    if taken:
        raise RoomUnavailable(f"Room already booked for: {taken}")

    room_type = await session.get(RoomType, room.room_type)

    if room_type is None:
        raise RateMissing("Room type has no rate configured.")

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
        raise BookingNotFound("Booking not found.")

    if booking.booking_status == BookingStatus.CHECKED_IN:
        raise AlreadyCheckedIn("Guest has already been checked in.")

    if booking.booking_status != BookingStatus.CONFIRMED:
        raise BookingNotConfirmed("Only confirmed bookings can be checked in.")

    today = utc_today()

    if booking.check_in != today:
        raise CheckInDateMismatch("Guest can only be checked in on the booking check-in date.")

    try:
        room = await get_room(room_id=booking.room_id, session=session)
    except ValueError as exc:
        raise RoomMissing(
            "Room assigned to this booking was not found."
        ) from exc

    if not room.is_available:
        raise AlreadyCheckedIn("Room is already occupied.")

    booking.booking_status = BookingStatus.CHECKED_IN
    room.is_available = False
    # room.room_state = RoomState.OCCUPIED

    session.add(booking)
    session.add(room)

    await session.commit()
    await session.refresh(booking)

    return booking

async def check_out_guest(
    session: AsyncSession,
    booking_id: int,
) -> tuple[Booking, bool]:
    """Check out a booking. Returns (booking, already_completed).

    Idempotent: already-COMPLETED bookings are a no-op success so the
    router can message the replay distinctly.
    """
    booking = await session.get(
        Booking,
        booking_id,
    )

    if booking is None:
        raise BookingNotFound(
            "Booking not found."
        )

    if booking.booking_status == BookingStatus.COMPLETED:
        return booking, True

    if booking.booking_status != BookingStatus.CHECKED_IN:
        raise BookingNotCheckedIn(
            "Guest has not been checked in."
        )

    today = utc_today()

    if booking.check_out != today:
        raise CheckOutDateMismatch(
            "Guest can only be checked out on the booking check-out date."
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


    room.is_available = False
    room.room_state = RoomState.DIRTY

    booking.booking_status = BookingStatus.COMPLETED

    session.add(room)
    session.add(booking)

    await session.commit()
    await session.refresh(booking)

    return booking, False

async def check_existing_hold(session: AsyncSession, room_id: int) -> bool:
    existing_hold = await session.get(Hold, room_id)
    return bool(existing_hold)
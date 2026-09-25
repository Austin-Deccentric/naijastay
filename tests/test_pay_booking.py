"""pay_booking outcome honesty tests (service-level).

POST /pay/ cannot run under TestClient (the mock provider posts back to
a live listener), so these call pay_booking directly with a stubbed
provider subprocess and assert the post-refresh status checks.
"""

import asyncio
from datetime import date, timedelta

import pytest

from app.core.time import utc_today
from app.db.session import AsyncSessionMaker
from app.domains.bookings.models import BookingStatus
from app.domains.bookings.service import HoldGone, NotProcessing
from app.domains.payments.service import pay_booking
from app.domains.users.service import get_user_by_email
from tests import helpers
from tests.helpers import run as _await


class _FakeProc:
    returncode = 0

    async def wait(self):
        return 0


def _cancel_sync(booking_id: int) -> None:
    """Blocking cancel, simulating the webhook's concurrent commit."""
    import psycopg

    from app.core.config import settings

    url = settings.database_url
    for prefix in ("postgresql+psycopg://", "postgres://", "postgresql://"):
        url = url.replace(prefix, "postgresql://")
    conn = psycopg.connect(url, autocommit=True)
    conn.execute(
        "UPDATE bookings SET booking_status = 'CANCELLED' WHERE booking_id = %s",
        (int(booking_id),),
    )
    conn.close()


async def _stub_subprocess(*args, **kwargs):
    return _FakeProc()


async def _stub_subprocess_cancelling(*args, **kwargs):
    """Provider stub that races like the real flow: the webhook cancels
    the booking (hold lost) while pay_booking awaits the script."""
    ref = args[args.index("--reference") + 1]  # "BOOK-<id>"
    _cancel_sync(int(str(ref).split("-")[-1]))
    return _FakeProc()


def _processing_booking() -> dict:
    check_in = utc_today() + timedelta(days=7)
    return helpers.create_booking(
        helpers.GUEST_1, 201, check_in, check_in + timedelta(days=2),
        BookingStatus.PROCESSING, 130000.0,
    )


async def _pay(booking_id: int):
    async with AsyncSessionMaker() as session:
        guest = await get_user_by_email(session, helpers.GUEST_1)
        return await pay_booking(booking_id, guest, session)


def test_cancelled_after_provider_raises_holdgone(client, monkeypatch):
    """Webhook cancelled the booking mid-flight (hold lost): 409, not 200."""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _stub_subprocess_cancelling)
    created = _processing_booking()
    with pytest.raises(HoldGone, match="Hold expired before payment"):
        _await(_pay(created["booking_id"]))
    assert helpers.get_booking_status(created["booking_id"]) == "cancelled"
    assert helpers.count("payments", f"WHERE booking_id = {created['booking_id']}") == 0


def test_unconfirmed_after_provider_raises_not_processing(client, monkeypatch):
    """Provider round-trip left the booking PROCESSING: distinct 409 message."""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _stub_subprocess)
    created = _processing_booking()
    with pytest.raises(NotProcessing, match="did not confirm"):
        _await(_pay(created["booking_id"]))
    assert helpers.get_booking_status(created["booking_id"]) == "processing"

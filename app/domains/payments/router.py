from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.core.permissions import require_guest
from app.core.rate_limit import limiter
from app.db.session import SessionDep
from app.domains.bookings.service import (
    BookingError,
    BookingMissing,
    NotProcessing,
    NotYours,
)
from app.domains.payments.schema import PayOut
from app.domains.payments.service import (
    pay_booking,
)
from app.domains.users.models import User

router = APIRouter(prefix="payments", tags=["Payments"])

_PAY_STATUS = {BookingMissing: 404, NotProcessing: 409, NotYours: 403}


@router.post("/pay/{booking_id}", response_model=PayOut)
@limiter.limit("5/minute")
async def pay_for_booking(
    _: Request,                                    
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


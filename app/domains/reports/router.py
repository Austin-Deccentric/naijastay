from datetime import date
from typing import Annotated

from app.core.permissions import require_manager
from app.db.session import SessionDep
from app.domains.reports.schemas import OccupancyReport
from app.domains.reports.service import get_occupancy_report
from app.domains.users.models import User
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/occupancy", response_model=OccupancyReport)
async def occupancy_report(
    session: SessionDep,
    _: Annotated[
        User,
        Depends(require_manager),
    ],
    report_date: Annotated[
        date | None,
        Query(
            description="Date for the occupancy report. Defaults to today.",
        ),
    ] = None,
) -> OccupancyReport:

    if report_date is None:
        report_date = date.today()

    return await get_occupancy_report(
        session=session,
        report_date=report_date,
    )
import logging
from datetime import UTC, datetime

from sqlmodel import select

from app.db.session import AsyncSessionMaker
from app.domains.bookings.models import Holds

logger = logging.getLogger("naijastay")


async def delete_expired_holds() -> int:
    """Delete expired holds and consumed holds. Returns rows removed."""
    now = datetime.now(UTC)
    async with AsyncSessionMaker() as session:
        result = await session.exec(
            select(Holds).where(
                (Holds.expires_at <= now) | (Holds.consumed == True)  # noqa: E712
            )
        )
        stale = result.all()
        for hold in stale:
            await session.delete(hold)
        if stale:
            await session.commit()
            logger.info("Hold sweeper removed %d hold(s)", len(stale))
        return len(stale)

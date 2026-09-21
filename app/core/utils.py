from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.db.session import engine
from app.domains.bookings.sweeps import delete_expired_holds


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        delete_expired_holds,
        "interval",
        seconds=60,
        id="expire_holds",
        replace_existing=True,
        max_instances=1,      # never run two copies at once
        misfire_grace_time=30,  # if late by >30s, skip instead of piling up
    )
    scheduler.start()
    
    yield

    scheduler.shutdown()

    print("Disposing engine...")
    await engine.dispose()
    print("Engine disposed.")


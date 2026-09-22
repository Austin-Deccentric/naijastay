from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.db.session import engine
from app.domains.bookings.sweeps import cancel_stale_processing, delete_expired_holds
from app.integrations.redis import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis(app)
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
    scheduler.add_job(
        cancel_stale_processing,
        "interval",
        seconds=300,
        id="cancel_stale_processing",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.start()
    
    yield

    scheduler.shutdown()
    await close_redis(app)

    print("Disposing engine...")
    await engine.dispose()
    print("Engine disposed.")


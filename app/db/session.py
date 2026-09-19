from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.domains.bookings.sweeps import delete_expired_holds

DATABASE_URL = settings.database_url

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL is not set")

# Accept plain postgres URLs (e.g. Render's managed DB) and coerce them to the
# async psycopg3 driver that SQLAlchemy's async engine requires.
if DATABASE_URL.split("://", 1)[0] in {"postgres", "postgresql"}:
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

AsyncSessionMaker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionMaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


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

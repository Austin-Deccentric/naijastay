from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

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




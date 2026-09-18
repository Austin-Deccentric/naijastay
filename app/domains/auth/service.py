from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.domains.auth.schemas import RegisterRequest
from app.domains.users.models import User, UserRole


async def register_user(
    session: AsyncSession,
    data: RegisterRequest,
) -> User:
    """Create and persist a new user account."""
    
    email = data.email.strip().lower()
    result = await session.exec(
        select(User).where(User.email == email)
    )
    existing_user = result.first()
    if existing_user:
        raise ValueError("A user with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        role=UserRole.GUEST,
        is_active=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ValueError("A user with this email already exists.")
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Authenticate a user using email and password."""
    email = email.strip().lower()
    result = await session.exec(
        select(User).where(User.email == email)
    )
    user = result.first()
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

async def generate_access_token(user: User) -> str:
    """Generate a JWT access token for an authenticated user."""
    return create_access_token(str(user.id), user.role.value)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.domains.auth.schemas import RegisterRequest
from app.domains.users.models import User, UserRole
from sqlmodel import Session, select


async def register_user(
    session: Session,
    data: RegisterRequest,
) -> User:
    """Create and persist a new user account."""

    existing_user = session.exec(
        select(User).where(User.email == data.email)
    ).first()
    if existing_user:
        raise ValueError("A user with this email already exists.")
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.GUEST,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

async def authenticate_user(
    session: Session,
    email: str,
    password: str,
) -> User | None:
    """Authenticate a user using email and password."""
    user = session.exec(
        select(User).where(User.email == email)
    ).first()
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
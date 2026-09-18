from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.security import hash_password
from app.db.session import SessionDep
from app.domains.users.models import User, UserRole
from app.domains.users.schema import CreateStaffRequest


async def create_staff(
    session: SessionDep,
    data: CreateStaffRequest,
) -> User:
    """Create a new staff account."""

    if data.role not in {
        UserRole.RECEPTIONIST,
        UserRole.HOUSEKEEPER,
    }:
        raise ValueError(
            "Only receptionist or housekeeper accounts can be created as staff."
        )

    email = data.email.strip().lower()
    result = await session.exec(
        select(User).where(User.email == email)
    )
    existing_user = result.first()

    if existing_user:
        raise ValueError(
            "A user with this email already exists."
        )
    staff = User(
        email=email,
        password_hash=hash_password(data.password.get_secret_value()),
        role=data.role,
        is_active=True,
    )
    session.add(staff)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ValueError("A user with this email already exists.")
    await session.refresh(staff)
    return staff

async def disable_staff(
    session: SessionDep,
    staff_id: int,
) -> User:
    """Disable an existing staff account."""
    staff = await session.get(User, staff_id)
    if staff is None:
        raise ValueError("Staff account not found.")

    if staff.role not in {
        UserRole.RECEPTIONIST,
        UserRole.HOUSEKEEPER,
    }:
        raise ValueError(
            "Only staff accounts can be disabled."
        )
    staff.is_active = False

    session.add(staff)
    await session.commit()
    await session.refresh(staff)

    return staff
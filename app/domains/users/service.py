from app.core.security import hash_password
from app.domains.users.models import User, UserRole
from app.domains.users.schemas import CreateStaffRequest
from sqlmodel import Session, select


async def create_staff(
    session: Session,
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

    existing_user = session.exec(
        select(User).where(User.email == data.email)
    ).first()

    if existing_user:
        raise ValueError(
            "A user with this email already exists."
        )
    staff = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
    )
    session.add(staff)
    session.commit()
    session.refresh(staff)
    return staff

async def disable_staff(
    session: Session,
    staff_id: int,
) -> User:
    """Disable an existing staff account."""
    staff = session.get(User, staff_id)
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
    session.commit()
    session.refresh(staff)

    return staff
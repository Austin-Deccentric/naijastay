from enum import Enum
from sqlmodel import Field, Relationship, SQLModel

class UserRole(str, Enum):
    GUEST = "guest"
    RECEPTIONIST = "receptionist"
    HOUSEKEEPER = "housekeeper"
    MANAGER = "manager"

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, nullable=False, max_length=255)
    password_hash: str = Field(nullable=False, max_length=255)
    role: UserRole = Field(default=UserRole.GUEST, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    # One user can have many bookings
  
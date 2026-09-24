from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.domains.users.models import UserRole


class CreateStaffRequest(BaseModel):
    """Data required for a manager to create a staff account."""
    email: EmailStr
    password: SecretStr = Field(
        min_length=8,
        max_length=128,
    )
    role: UserRole

class StaffResponse(BaseModel):
    """Public information returned for a staff account."""
    id: int
    email: EmailStr
    role: UserRole
    is_active: bool


class UserProfile(BaseModel):
    """Authenticated user's own profile (GET /users/me)."""
    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
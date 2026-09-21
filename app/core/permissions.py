from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.domains.users.models import User, UserRole


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Create a dependency that restricts access to specific user roles."""

    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return role_checker


require_guest = require_roles(UserRole.GUEST)
require_manager = require_roles(UserRole.MANAGER)
require_guest_or_receptionist = require_roles(UserRole.GUEST, UserRole.RECEPTIONIST)
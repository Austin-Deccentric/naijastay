from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.core.permissions import require_manager
from app.core.response import ApiResponse
from app.db.session import SessionDep
from app.domains.users.models import User
from app.domains.users.schema import CreateStaffRequest, StaffResponse, UserProfile
from app.domains.users.service import create_staff, disable_staff, enable_staff

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=ApiResponse[UserProfile])
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[UserProfile]:
    """Return the currently authenticated user's profile."""
    return ApiResponse(
        status="success",
        message="Profile retrieved.",
        data=UserProfile(
            id=current_user.id,
            email=current_user.email,
            role=current_user.role,
            is_active=current_user.is_active,
        ),
    )
    
@router.post("/staff", response_model=ApiResponse[StaffResponse], status_code=status.HTTP_201_CREATED)
async def create_staff_account(
    data: CreateStaffRequest,
    session: SessionDep,
    current_user: Annotated[User, Depends(require_manager)],) -> ApiResponse[StaffResponse]:
    """Allow a manager to create a staff account."""
    try:
        staff = await create_staff(
            session=session,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ApiResponse(
        status="success",
        message="Staff account created.",
        data=StaffResponse(
            id=staff.id,
            email=staff.email,
            role=staff.role,
            is_active=staff.is_active,
        ),
    )

@router.patch(
    "/staff/{staff_id}/disable",
    response_model=ApiResponse[StaffResponse],
)
async def disable_staff_account(
    staff_id: int,
    session: SessionDep,
    current_user:Annotated[User, Depends(require_manager)],
) -> ApiResponse[StaffResponse]:
    """Allow a manager to disable a staff account."""

    try:
        staff = await disable_staff(
            session=session,
            staff_id=staff_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ApiResponse(
        status="success",
        message="Staff account disabled.",
        data=StaffResponse(
            id=staff.id,
            email=staff.email,
            role=staff.role,
            is_active=staff.is_active,
        ),
    )


@router.patch("/staff/{staff_id}/enable", response_model=ApiResponse[StaffResponse])
async def enable_staff_account(
    staff_id: int,
    session: SessionDep,
    current_user:Annotated[User, Depends(require_manager)],
) -> ApiResponse[StaffResponse]:
    """Allow a manager to re-enable a disabled staff account."""

    try:
        staff = await enable_staff(
            session=session,
            staff_id=staff_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ApiResponse(
        status="success",
        message="Staff account enabled.",
        data=StaffResponse(
            id=staff.id,
            email=staff.email,
            role=staff.role,
            is_active=staff.is_active,
        ),
    )

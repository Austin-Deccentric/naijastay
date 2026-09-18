from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.domains.auth.schemas import (
    LoginResponse,
    RegisterRequest,
    UserResponse,
)
from app.domains.auth.service import (
    authenticate_user,
    register_user,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Session = Depends(get_db),
) -> UserResponse:
    """Register a new guest user."""
    try:
        user = register_user(
            session=session,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )

@router.post("/login", response_model=LoginResponse)
def login(
    email: str,
    password: str,
    session: Session = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user and return a JWT access token."""
    user = authenticate_user(
        session=session,
        email=email,
        password=password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        ),
    )
    
    from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.domains.auth.schemas import UserResponse
from app.domains.users.models import User

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)
@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile of the currently authenticated user."""

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
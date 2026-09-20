from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import SessionDep
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

@limiter.limit("10/hour")
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    data: RegisterRequest,
    session: SessionDep,
) -> UserResponse:
    """Register a new guest user."""
    try:
        user = await register_user(
            session=session,
            data=data
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


@limiter.limit("5/minute")
@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> LoginResponse:
    """Authenticate a user and return a JWT access token."""
    user = await authenticate_user(
        session=session,
        email=form_data.username,
        password=form_data.password,
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

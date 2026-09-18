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
from fastapi import APIRouter, HTTPException, status

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: SessionDep,
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
    session: SessionDep,
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

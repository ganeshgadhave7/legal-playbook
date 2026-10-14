"""Authentication endpoints."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    Token,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.audit import log_action
from app.services.auth import (
    create_access_token,
    get_password_hash,
    require_admin,
    require_user,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Token:
    """Authenticate a user and return a JWT access token."""
    result = await db.execute(select(User).where(User.email == request.email.lower().strip()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(request.password, user.hashed_password):
        await log_action(
            db=db,
            action="login_failed",
            resource_type="user",
            resource_id=request.email.lower().strip(),
            details={"reason": "incorrect_email_or_password"},
            success=False,
            request=http_request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(user.id)
    await log_action(
        db=db,
        action="login_success",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": user.email},
        request=http_request,
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(require_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(user)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
) -> UserListResponse:
    """List users (admin only)."""
    result = await db.execute(select(User).limit(limit).offset(offset))
    items = [UserResponse.model_validate(u) for u in result.scalars().all()]
    total_result = await db.execute(select(User))
    total = len(total_result.scalars().all())
    return UserListResponse(items=items, total=total)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Create a new user (admin only)."""
    existing = await db.execute(select(User).where(User.email == request.email.lower().strip()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        id=uuid4(),
        email=request.email.lower().strip(),
        hashed_password=get_password_hash(request.password),
        role=request.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await log_action(
        db=db,
        action="user_create",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": user.email, "role": user.role},
        request=http_request,
    )
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    request: UserUpdateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Update a user's role or active status (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and request.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    await db.commit()
    await log_action(
        db=db,
        action="user_update",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        details={"role": user.role, "is_active": user.is_active},
        request=http_request,
    )
    return UserResponse.model_validate(user)

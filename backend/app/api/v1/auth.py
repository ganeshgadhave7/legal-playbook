"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserResponse
from app.services.audit import log_action
from app.services.auth import create_access_token, require_user, verify_password

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

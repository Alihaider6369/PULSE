from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import forgot_password_limiter, login_limiter
from app.core.security import create_access_token, hash_password
from app.database.session import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import user_service
from app.services.email_service import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For or direct connection."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, response: Response, db: DBSession = Depends(get_db)):
    """Register a new user account and return a signed JWT access token."""
    user = user_service.create_user(db, data)
    token = create_access_token({"sub": str(user.id), "email": user.email})

    # Set secure cookie for browser web dashboard
    response.set_cookie(
        key="pulse_access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
    )

    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(data: UserLogin, request: Request, response: Response, db: DBSession = Depends(get_db)):
    """Authenticate with email and password and return a signed JWT access token."""
    client_ip = _get_client_ip(request)
    rate_key = f"{client_ip}:{data.email}"

    # Rate limit: max 5 failed attempts per 15 minutes per (IP + email)
    if login_limiter.is_rate_limited(rate_key, max_attempts=5, window_seconds=900):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )

    user = user_service.authenticate_user(db, data)
    if not user:
        login_limiter.record_attempt(rate_key, window_seconds=900)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Successful login: reset rate limit attempts
    login_limiter.reset(rate_key)

    token = create_access_token({"sub": str(user.id), "email": user.email})

    response.set_cookie(
        key="pulse_access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
    )

    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    """Request password reset link. Always returns 200 with identical message."""
    client_ip = _get_client_ip(request)
    rate_key = f"{client_ip}:{data.email}"

    # Rate limit: max 3 requests per hour per (IP + email)
    if forgot_password_limiter.is_rate_limited(rate_key, max_attempts=3, window_seconds=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    forgot_password_limiter.record_attempt(rate_key, window_seconds=3600)

    user = db.query(User).filter(User.email == data.email).first()
    if user and user.is_active:
        now = datetime.now(timezone.utc)
        # Invalidate older unused tokens for this user
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({"expires_at": now})

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = now + timedelta(hours=1)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)
        db.commit()

        reset_link = f"{settings.app_base_url.rstrip('/')}/reset-password.html?token={raw_token}"
        background_tasks.add_task(send_password_reset_email, user.email, reset_link)

    return {"status": "ok", "message": "If this email is registered, a password reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: DBSession = Depends(get_db),
):
    """Reset user password using token."""
    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    token_record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()

    if not token_record or token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    token_expires = token_record.expires_at
    if token_expires.tzinfo is None:
        token_expires = token_expires.replace(tzinfo=timezone.utc)
    if token_expires < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    user = db.get(User, token_record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    # Update password using existing bcrypt hash_password
    user.hashed_password = hash_password(data.new_password)
    token_record.used_at = now

    # Invalidate all other unused tokens of that user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.id != token_record.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"expires_at": now})

    db.commit()

    return {"status": "ok", "message": "Password updated. You can now sign in."}


@router.post("/logout")
def logout(response: Response):
    """Clear session authentication cookies."""
    response.delete_cookie(key="pulse_access_token")
    return {"status": "ok", "message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Return the profile of the authenticated user."""
    return current_user

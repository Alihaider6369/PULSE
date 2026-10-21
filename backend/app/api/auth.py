from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
import sys
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import (
    forgot_password_limiter,
    get_client_ip,
    is_db_rate_limited,
    login_limiter,
    record_db_attempt,
)
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
from app.services.email_service import send_password_reset_email, send_welcome_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("pulse.auth")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setLevel(logging.INFO)
    _sh.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_sh)

# Alias for backward compatibility
_get_client_ip = get_client_ip


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, request: Request, response: Response, db: DBSession = Depends(get_db)):
    """Register a new user account and return a signed JWT access token."""
    client_ip = _get_client_ip(request)
    normalized_email = data.email.strip().lower()
    data.email = normalized_email

    ip_key = f"signup:ip:{client_ip}"
    email_key = f"signup:email:{normalized_email}"

    if is_db_rate_limited(db, ip_key, max_attempts=10, window_seconds=3600) or \
       is_db_rate_limited(db, email_key, max_attempts=3, window_seconds=3600):
        logger.warning("rate limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    record_db_attempt(db, ip_key)
    record_db_attempt(db, email_key)

    user = user_service.create_user(db, data)

    # Send welcome email synchronously after user is saved.
    # If sending fails, signup must still succeed.
    try:
        send_welcome_email(user.email, user.full_name)
    except Exception as exc:
        logger.error(f"Failed to send welcome email to {user.email}: {type(exc).__name__}: {str(exc)}")

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
    normalized_email = data.email.strip().lower()
    data.email = normalized_email
    rate_key = f"{client_ip}:{normalized_email}"

    # Rate limit: max 5 failed attempts per 15 minutes per (IP + email)
    if login_limiter.is_rate_limited(rate_key, max_attempts=5, window_seconds=900):
        logger.warning("rate limited")
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
    db: DBSession = Depends(get_db),
):
    """Request password reset link. Always returns 200 with identical message."""
    client_ip = _get_client_ip(request)
    normalized_email = data.email.strip().lower()
    data.email = normalized_email

    ip_key = f"forgot_password:ip:{client_ip}"
    email_key = f"forgot_password:email:{normalized_email}"
    rate_key = f"{client_ip}:{normalized_email}"

    # Rate limit check: in-memory limiter and database-backed sliding-window counters
    if forgot_password_limiter.is_rate_limited(rate_key, max_attempts=3, window_seconds=3600) or \
       is_db_rate_limited(db, ip_key, max_attempts=10, window_seconds=3600) or \
       is_db_rate_limited(db, email_key, max_attempts=3, window_seconds=3600):
        logger.warning("rate limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    forgot_password_limiter.record_attempt(rate_key, window_seconds=3600)
    record_db_attempt(db, ip_key)
    record_db_attempt(db, email_key)

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not user.is_active:
        logger.info("no account for this email")
        return {"status": "ok", "message": "If this email is registered, a password reset link has been sent."}

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
    # Send synchronously (no background tasks, because of Vercel serverless)
    # Forgot-password must send the reset email ONLY to the exact email the user entered, if an account exists.
    try:
        sent = send_password_reset_email(normalized_email, reset_link)
        logger.info(f"reset email sent result={sent}")
    except Exception as exc:
        logger.error(f"Failed to send reset email: {type(exc).__name__}: {str(exc)}")
        logger.info("reset email sent result=False")

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

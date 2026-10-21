"""Service layer for user registration, authentication, and user profile management."""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.security import DUMMY_BCRYPT_HASH, hash_password, verify_password
from app.models.setting import Setting
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin


def create_user(db: DBSession, data: UserCreate) -> User:
    """Register a new user and initialize their personal settings row."""
    normalized_email = data.email.strip().lower()
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists",
        )

    user = User(
        email=normalized_email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        is_active=True,
    )
    db.add(user)
    db.flush()  # Generates user.id

    # Create personal settings profile for new user
    user_settings = Setting(
        user_id=user.id,
        poor_posture_threshold_seconds=30.0,
        cooldown_seconds=300.0,
        warning_duration_seconds=5.0,
        sound_enabled=True,
        min_confidence=0.5,
    )
    db.add(user_settings)

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: DBSession, data: UserLogin) -> Optional[User]:
    """Verify credentials and return User if valid, None otherwise."""
    normalized_email = data.email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        verify_password(data.password, DUMMY_BCRYPT_HASH)
        return None
    if not verify_password(data.password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user

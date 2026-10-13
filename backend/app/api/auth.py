"""Authentication API router: Signup, Login, Logout, and Current User."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.database.session import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserOut
from app.services import user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
def login(data: UserLogin, response: Response, db: DBSession = Depends(get_db)):
    """Authenticate with email and password and return a signed JWT access token."""
    user = user_service.authenticate_user(db, data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email address or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


@router.post("/logout")
def logout(response: Response):
    """Clear session authentication cookies."""
    response.delete_cookie(key="pulse_access_token")
    return {"status": "ok", "message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Return the profile of the authenticated user."""
    return current_user

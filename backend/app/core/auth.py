"""Authentication dependencies for FastAPI routes."""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DBSession

from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """Extract token from Authorization Bearer header, URL query, or cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fallback to cookie (for web dashboard browsers)
    cookie_token = request.cookies.get("pulse_access_token")
    if cookie_token:
        return cookie_token

    return None


def get_current_user(
    token: Optional[str] = Depends(_extract_token_from_request),
    db: DBSession = Depends(get_db),
) -> User:
    """Validate JWT token and return authenticated User object."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_current_user(
    token: Optional[str] = Depends(_extract_token_from_request),
    db: DBSession = Depends(get_db),
) -> Optional[User]:
    """Optional authentication: returns User if valid token is provided, None otherwise."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
        user = db.get(User, user_id)
        return user if (user and user.is_active) else None
    except Exception:
        return None

"""Sessions API router: lifecycle, listing, and idempotent synchronization."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_current_user, get_optional_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.session import (
    SessionEnd,
    SessionOut,
    SessionStart,
    SyncPayload,
    SyncResponse,
)
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start(
    data: SessionStart,
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    return session_service.start_session(db, data, user_id=user_id)


@router.post("/{session_id}/end", response_model=SessionOut)
def end(
    session_id: int,
    data: SessionEnd,
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    session = session_service.end_session(db, session_id, data, user_id=user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or access denied")
    return session


@router.get("", response_model=List[SessionOut])
def list_all(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    return session_service.list_sessions(db, user_id=user_id, limit=limit, offset=offset)


@router.post("/sync", response_model=SyncResponse)
def sync(
    payload: SyncPayload,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotently synchronize a batch of offline sessions and posture events for the authenticated user."""
    return session_service.sync_sessions(db, current_user.id, payload)
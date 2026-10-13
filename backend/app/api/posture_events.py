from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_optional_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.posture_event import PostureEventIn, PostureEventOut
from app.services import posture_event_service

router = APIRouter(prefix="/api/posture", tags=["posture"])


@router.post("/events", response_model=PostureEventOut, status_code=status.HTTP_201_CREATED)
def create(
    data: PostureEventIn,
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    event = posture_event_service.create_event(db, data, user_id=user_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Session not found or access denied")
    return event
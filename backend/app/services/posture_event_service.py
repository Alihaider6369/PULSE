"""Service layer for recording posture events and warnings."""
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.models.posture_event import PostureEvent
from app.models.session import Session
from app.schemas.posture_event import PostureEventIn


def create_event(
    db: DBSession, data: PostureEventIn, user_id: Optional[int] = None
) -> Optional[PostureEvent]:
    session = db.get(Session, data.session_id)
    if session is None:
        return None

    # Enforce session ownership
    if user_id is not None and session.user_id is not None and session.user_id != user_id:
        return None

    event = PostureEvent(**data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
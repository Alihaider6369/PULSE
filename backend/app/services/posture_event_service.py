from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.models.posture_event import PostureEvent
from app.models.session import Session
from app.schemas.posture_event import PostureEventIn


def create_event(db: DBSession, data: PostureEventIn) -> Optional[PostureEvent]:
    # The session must exist before we attach events to it
    if db.get(Session, data.session_id) is None:
        return None

    event = PostureEvent(**data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
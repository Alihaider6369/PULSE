from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DBSession

from app.models.session import Session
from app.schemas.session import SessionEnd, SessionStart


def start_session(db: DBSession, data: SessionStart) -> Session:
    session = Session(session_code=data.session_code, started_at=datetime.now(timezone.utc))
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def end_session(db: DBSession, session_id: int, data: SessionEnd) -> Optional[Session]:
    session = db.get(Session, session_id)
    if session is None:
        return None

    total = data.good_seconds + data.poor_seconds
    session.ended_at = datetime.now(timezone.utc)
    session.duration_seconds = total
    session.good_seconds = data.good_seconds
    session.poor_seconds = data.poor_seconds
    session.warning_count = data.warning_count
    # PULSE Posture Awareness Score: project indicator, not a medical measure
    session.awareness_score = round(data.good_seconds / total * 100, 1) if total > 0 else None

    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: DBSession) -> List[Session]:
    return db.query(Session).order_by(Session.started_at.desc()).all()
"""Service layer for sessions and idempotent synchronization."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DBSession

from app.models.posture_event import PostureEvent
from app.models.session import Session
from app.schemas.session import (
    SessionEnd,
    SessionStart,
    SyncPayload,
    SyncResponse,
    SyncResultItem,
)


def start_session(db: DBSession, data: SessionStart, user_id: Optional[int] = None) -> Session:
    session = Session(
        user_id=user_id,
        session_code=data.session_code,
        client_uuid=data.client_uuid,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def end_session(
    db: DBSession, session_id: int, data: SessionEnd, user_id: Optional[int] = None
) -> Optional[Session]:
    session = db.get(Session, session_id)
    if session is None:
        return None

    # Enforce ownership if user_id is provided
    if user_id is not None and session.user_id is not None and session.user_id != user_id:
        return None

    total = data.good_seconds + data.poor_seconds
    session.ended_at = datetime.now(timezone.utc)
    session.duration_seconds = total
    session.good_seconds = data.good_seconds
    session.poor_seconds = data.poor_seconds
    session.warning_count = data.warning_count
    session.awareness_score = round(data.good_seconds / total * 100, 1) if total > 0 else None

    db.commit()
    db.refresh(session)
    return session


def list_sessions(
    db: DBSession, user_id: Optional[int] = None, limit: int = 100, offset: int = 0
) -> List[Session]:
    query = db.query(Session)
    if user_id is not None:
        query = query.filter(Session.user_id == user_id)
    return query.order_by(Session.started_at.desc()).offset(offset).limit(limit).all()


def sync_sessions(db: DBSession, user_id: int, payload: SyncPayload) -> SyncResponse:
    """Idempotently synchronize offline sessions and events for the authenticated user."""
    synced_items: List[SyncResultItem] = []
    errors = []

    for s_in in payload.sessions:
        try:
            # 1. Check for existing session by client_uuid
            existing = db.query(Session).filter(Session.client_uuid == s_in.client_uuid).first()

            if existing:
                # Security: Prevent overwriting another user's session
                if existing.user_id is not None and existing.user_id != user_id:
                    errors.append({
                        "client_uuid": s_in.client_uuid,
                        "error": "Session UUID belongs to a different user account",
                    })
                    continue

                # Update session stats idempotently
                existing.ended_at = s_in.ended_at
                existing.duration_seconds = s_in.duration_seconds
                existing.good_seconds = s_in.good_seconds
                existing.poor_seconds = s_in.poor_seconds
                existing.warning_count = s_in.warning_count
                existing.awareness_score = s_in.awareness_score
                session_obj = existing
            else:
                # Create new session
                session_obj = Session(
                    user_id=user_id,
                    client_uuid=s_in.client_uuid,
                    session_code=s_in.session_code,
                    started_at=s_in.started_at,
                    ended_at=s_in.ended_at,
                    duration_seconds=s_in.duration_seconds,
                    good_seconds=s_in.good_seconds,
                    poor_seconds=s_in.poor_seconds,
                    warning_count=s_in.warning_count,
                    awareness_score=s_in.awareness_score,
                )
                db.add(session_obj)
                db.flush()  # Generate session_obj.id

            # 2. Synchronize attached events idempotently
            for e_in in s_in.events:
                existing_event = (
                    db.query(PostureEvent)
                    .filter(PostureEvent.client_uuid == e_in.client_uuid)
                    .first()
                )
                if not existing_event:
                    event_obj = PostureEvent(
                        session_id=session_obj.id,
                        client_uuid=e_in.client_uuid,
                        occurred_at=e_in.occurred_at,
                        posture_class=e_in.posture_class,
                        confidence=e_in.confidence,
                        duration_seconds=e_in.duration_seconds,
                        is_warning=e_in.is_warning,
                    )
                    db.add(event_obj)

            synced_items.append(
                SyncResultItem(client_uuid=s_in.client_uuid, server_id=session_obj.id, status="ok")
            )
        except Exception as exc:
            errors.append({"client_uuid": s_in.client_uuid, "error": str(exc)})

    db.commit()
    return SyncResponse(synced=synced_items, errors=errors)
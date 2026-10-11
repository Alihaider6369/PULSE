from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database.session import get_db
from app.schemas.session import SessionEnd, SessionOut, SessionStart
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionOut, status_code=201)
def start(data: SessionStart, db: DBSession = Depends(get_db)):
    return session_service.start_session(db, data)


@router.post("/{session_id}/end", response_model=SessionOut)
def end(session_id: int, data: SessionEnd, db: DBSession = Depends(get_db)):
    session = session_service.end_session(db, session_id, data)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("", response_model=List[SessionOut])
def list_all(db: DBSession = Depends(get_db)):
    return session_service.list_sessions(db)
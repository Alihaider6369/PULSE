from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database.session import get_db
from app.schemas.posture_event import PostureEventIn, PostureEventOut
from app.services import posture_event_service

router = APIRouter(prefix="/api/posture", tags=["posture"])


@router.post("/events", response_model=PostureEventOut, status_code=201)
def create(data: PostureEventIn, db: DBSession = Depends(get_db)):
    event = posture_event_service.create_event(db, data)
    if event is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return event
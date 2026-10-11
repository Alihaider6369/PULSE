from fastapi import APIRouter

from app.schemas.live import LiveUpdate
from app.services import live_status

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/status")
def get_status():
    return live_status.get()


@router.post("/status")
def post_status(data: LiveUpdate):
    return live_status.update(data.model_dump())


@router.post("/stop")
def post_stop():
    return live_status.stop()
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_optional_current_user
from app.models.user import User
from app.schemas.live import LiveUpdate
from app.services import live_status
from app.services.live_status import LiveStorageConfigError, LiveStorageError

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/status")
def get_status(current_user: Optional[User] = Depends(get_optional_current_user)):
    """Retrieve the current live monitor status from shared storage."""
    user_id = current_user.id if current_user else None
    try:
        return live_status.get(user_id=user_id)
    except LiveStorageConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except LiveStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Live storage communication error: {exc}",
        )


@router.post("/status")
def post_status(
    data: LiveUpdate,
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Write/refresh live monitor telemetry in shared storage."""
    user_id = current_user.id if current_user else None
    try:
        return live_status.update(data.model_dump(), user_id=user_id)
    except LiveStorageConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except LiveStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Live storage communication error: {exc}",
        )


@router.post("/stop")
def post_stop(current_user: Optional[User] = Depends(get_optional_current_user)):
    """Mark the live monitor session as inactive in shared storage."""
    user_id = current_user.id if current_user else None
    try:
        return live_status.stop(user_id=user_id)
    except LiveStorageConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except LiveStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Live storage communication error: {exc}",
        )


@router.get("/diagnostics")
def get_diagnostics():
    """Diagnostic check for live monitor storage configuration and health."""
    return live_status.get_storage_diagnostic()
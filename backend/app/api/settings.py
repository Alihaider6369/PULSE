from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.auth import get_optional_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.setting import SettingIn, SettingOut
from app.services import setting_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingOut)
def read_settings(
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    return setting_service.get_settings(db, user_id=user_id)


@router.put("", response_model=SettingOut)
def update(
    data: SettingIn,
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    user_id = current_user.id if current_user else None
    return setting_service.update_settings(db, data, user_id=user_id)
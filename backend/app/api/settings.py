from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.database.session import get_db
from app.schemas.setting import SettingIn, SettingOut
from app.services import setting_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingOut)
def read_settings(db: DBSession = Depends(get_db)):
    return setting_service.get_settings(db)


@router.put("", response_model=SettingOut)
def update(data: SettingIn, db: DBSession = Depends(get_db)):
    return setting_service.update_settings(db, data)
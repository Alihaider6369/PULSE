from sqlalchemy.orm import Session as DBSession

from app.models.setting import Setting
from app.schemas.setting import SettingIn


def get_settings(db: DBSession) -> Setting:
    # Single-row table: create the default row the first time it is read
    row = db.get(Setting, 1)
    if row is None:
        row = Setting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_settings(db: DBSession, data: SettingIn) -> Setting:
    row = get_settings(db)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
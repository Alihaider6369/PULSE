"""Service layer for user settings management."""
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.models.setting import Setting
from app.schemas.setting import SettingIn


def get_settings(db: DBSession, user_id: Optional[int] = None) -> Setting:
    """Retrieve settings for the specific user (or global fallback if unauthenticated)."""
    if user_id is not None:
        row = db.query(Setting).filter(Setting.user_id == user_id).first()
        if row is None:
            row = Setting(user_id=user_id)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    # Global / legacy settings row (id=1)
    row = db.get(Setting, 1)
    if row is None:
        row = Setting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_settings(db: DBSession, data: SettingIn, user_id: Optional[int] = None) -> Setting:
    """Update settings for the specific user."""
    row = get_settings(db, user_id)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
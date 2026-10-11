from pydantic import BaseModel, ConfigDict, Field


class SettingIn(BaseModel):
    poor_posture_threshold_seconds: float = Field(ge=5, le=600)
    cooldown_seconds: float = Field(ge=10, le=3600)
    warning_duration_seconds: float = Field(ge=1, le=60)
    sound_enabled: bool
    min_confidence: float = Field(ge=0, le=1)


class SettingOut(SettingIn):
    model_config = ConfigDict(from_attributes=True)
"""Configuration manager and path definitions for PULSE Desktop."""
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

# Resolve application bundle / root directory
if getattr(sys, "frozen", False):
    # PyInstaller sets sys._MEIPASS to the bundle / extraction directory
    base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    if not (base_dir / "models" / "pulse_model.joblib").exists():
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "_internal" / "models" / "pulse_model.joblib").exists():
            base_dir = exe_dir / "_internal"
        elif (exe_dir / "models" / "pulse_model.joblib").exists():
            base_dir = exe_dir
        elif (base_dir / "ml" / "models" / "pulse_model.joblib").exists():
            pass
        elif (exe_dir / "_internal" / "ml" / "models" / "pulse_model.joblib").exists():
            base_dir = exe_dir / "_internal"
        elif (exe_dir / "ml" / "models" / "pulse_model.joblib").exists():
            base_dir = exe_dir
    ROOT_DIR = base_dir
    MODELS_DIR = (
        (ROOT_DIR / "models")
        if (ROOT_DIR / "models" / "pulse_model.joblib").exists()
        else (ROOT_DIR / "ml" / "models")
    )
    ML_DIR = ROOT_DIR / "ml"
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    ML_DIR = ROOT_DIR / "ml"
    MODELS_DIR = ML_DIR / "models"

MODEL_PATH = MODELS_DIR / "pose_landmarker_lite.task"
CLASSIFIER_PATH = MODELS_DIR / "pulse_model.joblib"
METADATA_PATH = MODELS_DIR / "model_metadata.json"


def _resolve_app_data_dir() -> Path:
    """Return a writable per-user application-data directory.

    Uses %LOCALAPPDATA%\\PULSE on Windows (or ~/.pulse fallback / non-Windows).
    Migrates legacy ~/.pulse files safely to %LOCALAPPDATA%\\PULSE if present.
    """
    override = os.environ.get("PULSE_DATA_DIR")
    if override:
        app_dir = Path(override)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        app_dir = Path(os.environ["LOCALAPPDATA"]) / "PULSE"
        legacy_dir = Path.home() / ".pulse"
        if legacy_dir.exists() and not (app_dir / "pulse_local.db").exists():
            try:
                app_dir.mkdir(parents=True, exist_ok=True)
                import shutil

                for item in legacy_dir.iterdir():
                    target = app_dir / item.name
                    if not target.exists():
                        if item.is_file():
                            shutil.copy2(item, target)
                        elif item.is_dir():
                            shutil.copytree(item, target)
            except Exception as exc:
                print(f"Notice: Failed to migrate legacy cache to {app_dir}: {exc}")
    else:
        app_dir = Path.home() / ".pulse"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


APP_DATA_DIR = _resolve_app_data_dir()
CONFIG_FILE = APP_DATA_DIR / "desktop_config.json"
OFFLINE_CACHE_FILE = APP_DATA_DIR / "offline_sessions.json"


@dataclass
class AppConfig:
    api_url: str = "http://127.0.0.1:8000/api"
    camera_index: int = 0
    poor_posture_threshold_seconds: float = 30.0
    cooldown_seconds: float = 300.0
    warning_duration_seconds: float = 5.0
    sound_enabled: bool = True
    min_confidence: float = 0.5
    smoothing_window: int = 10
    show_landmarks: bool = True
    camera_width: int = 640
    camera_height: int = 480
    target_preview_fps: int = 30
    target_inference_fps: int = 12

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as exc:
            print(f"Warning: Failed to save config to {CONFIG_FILE}: {exc}")

"""Entry point for the PULSE Desktop Application."""
import os
import sys
from pathlib import Path

# Add project root to sys.path
if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Guard against None sys.stdout / sys.stderr in PyInstaller windowed mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from desktop_app.config import APP_DATA_DIR, CLASSIFIER_PATH, METADATA_PATH, MODEL_PATH

try:
    with open(APP_DATA_DIR / "argv_diag.txt", "w", encoding="utf-8") as _df:
        _df.write(repr(sys.argv))
except Exception:
    pass


def run_integrity_check() -> int:
    """Headless self-test to verify bundled ML assets, dependencies, and writable per-user directory."""
    import json
    import joblib

    status = {
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "classifier_path": str(CLASSIFIER_PATH),
        "classifier_exists": CLASSIFIER_PATH.exists(),
        "metadata_path": str(METADATA_PATH),
        "metadata_exists": METADATA_PATH.exists(),
        "app_data_dir": str(APP_DATA_DIR),
        "app_data_writable": False,
        "classifier_loaded": False,
        "matplotlib_loaded": False,
        "mediapipe_loaded": False,
        "worker_loaded": False,
        "main_window_loaded": False,
    }

    try:
        test_file = APP_DATA_DIR / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        status["app_data_writable"] = True
    except Exception as exc:
        status["app_data_error"] = str(exc)

    try:
        if CLASSIFIER_PATH.exists():
            clf = joblib.load(CLASSIFIER_PATH)
            status["classifier_loaded"] = hasattr(clf, "predict")
    except Exception as exc:
        status["classifier_error"] = str(exc)

    try:
        import matplotlib

        status["matplotlib_loaded"] = True
        status["matplotlib_version"] = getattr(matplotlib, "__version__", "unknown")
    except Exception as exc:
        status["matplotlib_error"] = str(exc)

    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        status["mediapipe_loaded"] = True
    except Exception as exc:
        status["mediapipe_error"] = str(exc)

    try:
        from desktop_app.core.worker import PostureWorker

        status["worker_loaded"] = True
    except Exception as exc:
        status["worker_error"] = str(exc)

    try:
        from desktop_app.ui.main_window import MainWindow

        status["main_window_loaded"] = True
    except Exception as exc:
        status["main_window_error"] = str(exc)

    success = (
        status["model_exists"]
        and status["classifier_exists"]
        and status["metadata_exists"]
        and status["app_data_writable"]
        and status["classifier_loaded"]
        and status["matplotlib_loaded"]
        and status["mediapipe_loaded"]
        and status["worker_loaded"]
        and status["main_window_loaded"]
    )
    status["success"] = success

    try:
        report_file = APP_DATA_DIR / "integrity_check.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception:
        pass

    return 0 if success else 1


# Early exit for headless integrity check or version flags
if "--check-integrity" in sys.argv:
    os._exit(run_integrity_check())

if "--version" in sys.argv:
    os._exit(0)

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from desktop_app.ui.main_window import MainWindow


def main() -> None:

    # High DPI support
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("PULSE")
    app.setOrganizationName("PULSE Posture")

    # Set application icon if present
    icon_path = ROOT / "desktop_app" / "resources" / "pulse.ico"
    if not icon_path.exists():
        icon_path = ROOT / "resources" / "pulse.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Set default application font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

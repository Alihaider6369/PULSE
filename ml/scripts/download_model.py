"""Download the MediaPipe pose model (one time only).

The model file is saved in ml/models/. It is ignored by Git (see .gitignore).
"""
from pathlib import Path
import urllib.request

URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
DEST = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)

    if DEST.exists() and DEST.stat().st_size > 1_000_000:
        print(f"Model already exists: {DEST}")
        return

    print("Downloading pose model (about 5 MB)...")
    try:
        urllib.request.urlretrieve(URL, DEST)
    except Exception as exc:
        if DEST.exists():
            DEST.unlink()
        print(f"Download failed: {exc}")
        print("Check your internet connection and run this script again.")
        raise SystemExit(1)

    size_mb = DEST.stat().st_size / 1_000_000
    print(f"Saved: {DEST} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
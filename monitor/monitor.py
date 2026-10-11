"""Phase 13: live monitor connected to the FastAPI backend.

Each run creates a session in the database, saves posture warnings as events,
sends live status to the backend every second, and closes the session with the
final totals when you press Q. If the backend is not running, the monitor still
works, it just does not save.

Press Q or ESC to quit.
"""
import sys
import threading
import time
import uuid
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml" / "scripts"))

import cv2
import joblib
import mediapipe as mp
import requests
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from ml.pulse_features import extract_features, features_to_vector, is_person_visible
from webcam_pose_poc import MODEL_PATH, CAMERA_INDEX, draw_landmarks
from monitor import settings as cfg
from monitor.temporal import PostureTimer

CLASSIFIER_PATH = ROOT / "ml" / "models" / "pulse_model.joblib"
API = "http://127.0.0.1:8000/api"
LIVE_INTERVAL_S = 1.0   # send live status every second
NO_PERSON = "no_person"
UNCERTAIN = "uncertain"

try:
    import winsound

    def beep():
        if cfg.SOUND_ENABLED:
            winsound.Beep(800, 300)
except ImportError:
    def beep():
        pass


def put(frame, text, y, color=(255, 255, 255), scale=0.6):
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def api_post(path, payload):
    """POST to the backend. Returns the JSON, or None if the backend is down."""
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=3)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        print(f"Backend not reachable ({exc.__class__.__name__}). Continuing without saving.")
        return None


def send_live(payload):
    """Send live status in a background thread so the camera loop never waits."""
    threading.Thread(target=api_post, args=("/live/status", payload), daemon=True).start()


def main() -> None:
    if not MODEL_PATH.exists() or not CLASSIFIER_PATH.exists():
        print("Model or pose file missing. Run download_model.py and train_model_4class.py first.")
        sys.exit(1)

    clf = joblib.load(CLASSIFIER_PATH)
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open the camera. Close other apps using it.")
        sys.exit(1)

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )

    # Start a session in the backend (the code is just a readable unique ID)
    session_code = uuid.uuid4().hex[:8]
    created = api_post("/sessions/start", {"session_code": session_code})
    db_session_id = created["id"] if created else None
    if db_session_id:
        print(f"Session started in database: id={db_session_id}, code={session_code}")

    timer = PostureTimer(cfg.POOR_POSTURE_THRESHOLD_SECONDS, cfg.COOLDOWN_SECONDS)
    history = deque(maxlen=cfg.SMOOTHING_WINDOW)
    warning_until = 0.0
    good_seconds = 0.0
    poor_seconds = 0.0
    warnings_count = 0
    last_ts = 0
    last_tick = time.monotonic()
    last_live_sent = 0.0
    print("Monitor is ON. Press Q or ESC in the window to stop.")

    try:
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Could not read a frame from the camera.")
                    break

                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int(time.monotonic() * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts

                result = landmarker.detect_for_video(mp_image, ts)
                lm = result.pose_landmarks[0] if result.pose_landmarks else None
                if lm:
                    draw_landmarks(frame, lm)

                raw = NO_PERSON
                if lm and is_person_visible(lm):
                    feats = extract_features(lm, w, h)
                    raw = str(clf.predict([features_to_vector(feats)])[0]) if feats else UNCERTAIN
                history.append(raw)
                label = Counter(history).most_common(1)[0][0]

                now = time.monotonic()
                dt = now - last_tick
                last_tick = now
                if label == "poor_posture":
                    poor_seconds += dt
                elif label in ("good", "lean_left", "lean_right"):
                    good_seconds += dt

                if timer.update(label, now):
                    warnings_count += 1
                    warning_until = now + cfg.WARNING_DURATION_SECONDS
                    beep()
                    if db_session_id:
                        api_post("/posture/events", {
                            "session_id": db_session_id,
                            "posture_class": label,
                            "confidence": None,
                            "duration_seconds": cfg.POOR_POSTURE_THRESHOLD_SECONDS,
                            "is_warning": True,
                        })

                if now - last_live_sent >= LIVE_INTERVAL_S:
                    send_live({
                        "active": True,
                        "session_id": db_session_id,
                        "posture": label,
                        "warnings": warnings_count,
                        "good_seconds": good_seconds,
                        "poor_seconds": poor_seconds,
                    })
                    last_live_sent = now

                display = cv2.flip(frame, 1)
                color = (0, 200, 0) if label == "good" else (0, 165, 255)
                if label == "poor_posture":
                    color = (0, 0, 255)
                put(display, f"Posture: {label}", 35, color, 0.9)
                put(display, f"Warnings: {warnings_count}", 70, (255, 255, 255), 0.6)
                put(display, f"Good: {good_seconds:.0f}s   Poor: {poor_seconds:.0f}s", 100, (255, 255, 255), 0.6)
                if now < warning_until:
                    put(display, "Please sit up straight and relax your shoulders", 140, (0, 0, 255), 0.7)
                put(display, "Q = quit", h - 15, (255, 255, 255), 0.5)

                cv2.imshow("PULSE - Monitor", display)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if db_session_id:
            api_post("/live/stop", {})
            ended = api_post(f"/sessions/{db_session_id}/end", {
                "good_seconds": good_seconds,
                "poor_seconds": poor_seconds,
                "warning_count": warnings_count,
            })
            if ended:
                print(f"Session saved: score={ended['awareness_score']}")
        print(f"Monitor OFF. Good: {good_seconds:.0f}s, Poor: {poor_seconds:.0f}s, Warnings: {warnings_count}")


if __name__ == "__main__":
    main()
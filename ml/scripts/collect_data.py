"""Phase 5: collect labelled posture samples from the webcam.

Usage:
    python ml\\scripts\\collect_data.py

Keys in the video window:
    1 = Good posture
    2 = Slouching
    3 = Forward head
    4 = Leaning left
    5 = Leaning right
    S = start / stop recording the current label
    Q or ESC = quit and save

Only numbers are saved (features + landmark visibility). No video or images.
"""
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]      # D:\PULSE
sys.path.insert(0, str(ROOT))

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from ml.pulse_features import extract_features, features_to_vector, FEATURE_NAMES, is_person_visible
from webcam_pose_poc import MODEL_PATH, CAMERA_INDEX, draw_landmarks

OUT_DIR = ROOT / "ml" / "data" / "raw"
SAMPLE_INTERVAL_S = 0.4     # one sample every 0.4 s (avoids near-duplicate frames)
COUNTDOWN_S = 5             # countdown before recording starts

LABELS = {
    ord("1"): "good",
    ord("2"): "slouch",
    ord("3"): "forward_head",
    ord("4"): "lean_left",
    ord("5"): "lean_right",
}
INSTRUCTIONS = {
    "good": "Sit upright, shoulders level, head over shoulders",
    "slouch": "Drop your shoulders and head forward, like hunched over a laptop",
    "forward_head": "Push your head forward (chin toward screen), shoulders stay back",
    "lean_left": "Lean your upper body to your LEFT side",
    "lean_right": "Lean your upper body to your RIGHT side",
}

COLUMNS = ["session_id", "timestamp", "label"] + FEATURE_NAMES + ["min_visibility"]


def new_csv_path() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUT_DIR / f"posture_{stamp}.csv"


def put(frame, text, y, color=(255, 255, 255), scale=0.6):
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def main() -> None:
    if not MODEL_PATH.exists():
        print("Model file not found. Run: python ml\\scripts\\download_model.py")
        sys.exit(1)

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open the camera. Close other apps using it.")
        sys.exit(1)

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )

    csv_path = new_csv_path()
    session_id = uuid4().hex[:8]
    print(f"Saving to: {csv_path}")
    print(f"Session ID: {session_id}")

    f_out = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f_out, fieldnames=COLUMNS)
    writer.writeheader()

    current_label = None
    recording = False
    countdown_end = None
    last_sample_t = 0.0
    saved_counts = {}
    last_ts = 0

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
                visible = is_person_visible(lm) if lm else False
                features = extract_features(lm, w, h) if visible else None
                if lm:
                    draw_landmarks(frame, lm)

                now = time.monotonic()

                # Countdown -> start recording
                if countdown_end is not None and now >= countdown_end:
                    countdown_end = None
                    recording = True
                    last_sample_t = 0.0

                # Save one sample if recording, label set, person visible, interval passed
                if recording and features and (now - last_sample_t) >= SAMPLE_INTERVAL_S:
                    row = {
                        "session_id": session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "label": current_label,
                        "min_visibility": min(lm[0].visibility, lm[11].visibility, lm[12].visibility),
                    }
                    row.update(dict(zip(FEATURE_NAMES, features_to_vector(features))))
                    writer.writerow(row)
                    saved_counts[current_label] = saved_counts.get(current_label, 0) + 1
                    last_sample_t = now

                display = cv2.flip(frame, 1)
                overlay = display.copy()
                cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
                display = cv2.addWeighted(overlay, 0.5, display, 0.5, 0)

                if current_label is None:
                    put(display, "Press 1-5 to choose a posture label", 30)
                else:
                    put(display, f"Label: {current_label}", 30, (0, 255, 255))
                    put(display, INSTRUCTIONS[current_label][:70], 60, (255, 255, 255), 0.5)

                if countdown_end is not None:
                    left = max(0.0, countdown_end - now)
                    put(display, f"Starting in {left:0.1f}s", 90, (0, 165, 255))
                elif recording:
                    put(display, "RECORDING  (S = stop)", 90, (0, 0, 255))
                    if features is None:
                        put(display, "Adjust position: head/shoulders not clear", 110, (0, 165, 255), 0.5)
                else:
                    put(display, "Press S to start (5s countdown)", 90, (200, 200, 200), 0.6)

                counts = " | ".join(f"{k}:{v}" for k, v in saved_counts.items()) or "no samples yet"
                put(display, f"Saved -> {counts}"[:90], h - 15, (255, 255, 255), 0.5)

                cv2.imshow("PULSE - Phase 5 collector", display)
                key = cv2.waitKey(1) & 0xFF

                if key in (ord("q"), 27):
                    break
                if key in LABELS:
                    current_label = LABELS[key]
                    recording = False
                    countdown_end = None
                if key == ord("s") and current_label is not None:
                    if recording:
                        recording = False
                    else:
                        countdown_end = time.monotonic() + COUNTDOWN_S
    finally:
        f_out.close()
        cap.release()
        cv2.destroyAllWindows()
        total = sum(saved_counts.values())
        print(f"Camera is OFF. Saved {total} rows to {csv_path}")
        for k, v in saved_counts.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
"""Phase 8: live posture prediction with the saved model.

Press Q or ESC to quit. Nothing is saved (no video, no images, no CSV).
"""
import sys
import time
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2
import joblib
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from ml.pulse_features import extract_features, features_to_vector, is_person_visible
from webcam_pose_poc import MODEL_PATH, CAMERA_INDEX, draw_landmarks

CLASSIFIER_PATH = ROOT / "ml" / "models" / "pulse_model.joblib"
SMOOTHING_WINDOW = 10     # majority vote over the last N frames
MIN_CONFIDENCE = 0.5      # below this the frame counts as "uncertain"
NO_PERSON = "no_person"
UNCERTAIN = "uncertain"

COLORS = {
    "good": (0, 200, 0),
    "poor_posture": (0, 0, 255),
    "lean_left": (0, 165, 255),
    "lean_right": (0, 165, 255),
    NO_PERSON: (200, 200, 200),
    UNCERTAIN: (200, 200, 200),
}


def put(frame, text, y, color=(255, 255, 255), scale=0.6):
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def main() -> None:
    if not MODEL_PATH.exists():
        print("Pose model not found. Run: python ml\\scripts\\download_model.py")
        sys.exit(1)
    if not CLASSIFIER_PATH.exists():
        print("Posture model not found. Run: python ml\\scripts\\train_model_4class.py")
        sys.exit(1)

    clf = joblib.load(CLASSIFIER_PATH)
    print("Model loaded. Classes:", list(clf.classes_))

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open the camera. Close other apps using it.")
        sys.exit(1)

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )

    history = deque(maxlen=SMOOTHING_WINDOW)
    last_ts = 0
    prev_time = time.time()
    print("Camera is ON. Press Q or ESC in the video window to stop.")

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

                raw_label, conf, proba_text = NO_PERSON, 0.0, ""
                if lm:
                    draw_landmarks(frame, lm)
                if lm and is_person_visible(lm):
                    features = extract_features(lm, w, h)
                    if features:
                        vec = [features_to_vector(features)]   # same order as training
                        proba = clf.predict_proba(vec)[0]
                        idx = int(proba.argmax())
                        conf = float(proba[idx])
                        raw_label = str(clf.classes_[idx]) if conf >= MIN_CONFIDENCE else UNCERTAIN
                        proba_text = "  ".join(
                            f"{c}:{p:.2f}" for c, p in zip(clf.classes_, proba))

                history.append(raw_label)
                smoothed = Counter(history).most_common(1)[0][0]
                color = COLORS.get(smoothed, (255, 255, 255))

                display = cv2.flip(frame, 1)
                now = time.time()
                fps = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                put(display, f"Posture: {smoothed}", 35, color, 0.9)
                put(display, f"Confidence (this frame): {conf:.0%}", 70, (255, 255, 255), 0.6)
                if proba_text:
                    put(display, proba_text[:80], 100, (220, 220, 220), 0.45)
                put(display, f"FPS: {fps:.0f}   (Q = quit)", h - 15, (255, 255, 255), 0.5)

                cv2.imshow("PULSE - Phase 8 live prediction", display)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Camera is OFF.")


if __name__ == "__main__":
    main()
"""Phase 4: show live posture features on top of the webcam feed.

Press Q or ESC to quit. Nothing is saved.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # D:\PULSE
sys.path.insert(0, str(ROOT))                   # so "ml.pulse_features" can be imported

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from ml.pulse_features import extract_features, FEATURE_NAMES, is_person_visible
from ml.scripts.webcam_pose_poc import MODEL_PATH, CAMERA_INDEX, draw_landmarks


def main() -> None:
    if not MODEL_PATH.exists():
        print("Model file not found. Run: python ml\\scripts\\download_model.py")
        sys.exit(1)

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open the camera. Close other apps using it and check Windows camera privacy.")
        sys.exit(1)

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )

    print("Camera is ON. Press Q or ESC in the video window to stop.")
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

                features, status, color = None, "No person detected", (0, 0, 255)
                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    draw_landmarks(frame, lm)
                    if is_person_visible(lm):
                        features = extract_features(lm, w, h)
                        status, color = "Person detected", (0, 200, 0)
                    else:
                        status, color = "Poor visibility", (0, 165, 255)

                display = cv2.flip(frame, 1)

                # dark panel behind the numbers
                panel_h = 20 * len(FEATURE_NAMES) + 10
                overlay = display.copy()
                cv2.rectangle(overlay, (0, 45), (330, 45 + panel_h), (0, 0, 0), -1)
                display = cv2.addWeighted(overlay, 0.55, display, 0.45, 0)

                cv2.putText(display, status, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                for i, name in enumerate(FEATURE_NAMES):
                    value = f"{features[name]:7.2f}" if features else "    ---"
                    cv2.putText(display, f"{name[:24]:24s}{value}", (8, 65 + i * 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

                cv2.imshow("PULSE - Phase 4 features", display)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Camera is OFF.")


if __name__ == "__main__":
    main()
"""Phase 3 proof of concept: webcam + MediaPipe pose landmarks.

Press Q or ESC to quit. Nothing is saved: no video, no images.
"""
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"
CAMERA_INDEX = 0          # 0 = built-in laptop webcam
MIN_VISIBILITY = 0.5      # below this a landmark is treated as not visible

# MediaPipe landmark indices we care about (upper body only)
NOSE, L_EAR, R_EAR = 0, 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
POINTS = [NOSE, L_EAR, R_EAR, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW]
LINES = [(L_EAR, NOSE), (NOSE, R_EAR), (L_SHOULDER, R_SHOULDER),
         (L_SHOULDER, L_ELBOW), (R_SHOULDER, R_ELBOW)]


def draw_landmarks(frame, landmarks) -> None:
    """Draw upper-body points and lines on the frame (in place)."""
    h, w = frame.shape[:2]

    def pos(i):
        return int(landmarks[i].x * w), int(landmarks[i].y * h)

    for a, b in LINES:
        if landmarks[a].visibility >= MIN_VISIBILITY and landmarks[b].visibility >= MIN_VISIBILITY:
            cv2.line(frame, pos(a), pos(b), (255, 200, 0), 2)
    for i in POINTS:
        if landmarks[i].visibility >= MIN_VISIBILITY:
            cv2.circle(frame, pos(i), 5, (0, 255, 0), -1)


def main() -> None:
    if not MODEL_PATH.exists():
        print("Model file not found. Run first:")
        print("    python ml\\scripts\\download_model.py")
        sys.exit(1)

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open the camera.")
        print("- Close other apps using the camera (Zoom, Teams, browser tabs).")
        print("- Windows Settings > Privacy & security > Camera: allow desktop apps.")
        sys.exit(1)

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )

    print("Camera is ON. Press Q or ESC in the video window to stop.")
    last_ts = 0
    prev_time = time.time()

    try:
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Could not read a frame from the camera.")
                    break

                # Process the RAW (un-mirrored) frame. Later phases do the same,
                # so training and live prediction see identical data.
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                ts = int(time.monotonic() * 1000)
                if ts <= last_ts:          # timestamps must increase
                    ts = last_ts + 1
                last_ts = ts

                result = landmarker.detect_for_video(mp_image, ts)

                status, color = "No person detected", (0, 0, 255)
                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    key_vis = min(lm[NOSE].visibility,
                                  lm[L_SHOULDER].visibility,
                                  lm[R_SHOULDER].visibility)
                    draw_landmarks(frame, lm)
                    if key_vis >= MIN_VISIBILITY:
                        status, color = "Head and shoulders visible", (0, 200, 0)
                    else:
                        status, color = "Poor visibility: adjust light/position", (0, 165, 255)

                display = cv2.flip(frame, 1)   # mirror only for display
                now = time.time()
                fps = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                cv2.putText(display, status, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.putText(display, f"FPS: {fps:.0f}   (Q = quit)", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                cv2.imshow("PULSE - Phase 3", display)

                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Camera is OFF.")


if __name__ == "__main__":
    main()
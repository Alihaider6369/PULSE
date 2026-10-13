"""Background worker thread for low-latency camera capture, pose estimation, and SVM prediction."""
import math
import sys
import threading
import time
import uuid
from collections import Counter, deque
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

import cv2
import joblib
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from desktop_app.config import AppConfig, CLASSIFIER_PATH, MODEL_PATH, ROOT_DIR
from desktop_app.core.audio import AudioManager
from desktop_app.core.client import PulseApiClient

# Import core PULSE modules
sys.path.insert(0, str(ROOT_DIR))
from ml.pulse_features import extract_features, features_to_vector, is_person_visible
from monitor.temporal import PostureTimer

# Upper-body landmarks and connections
NOSE, L_EAR, R_EAR = 0, 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
KEY_POINTS = [NOSE, L_EAR, R_EAR, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW]
KEY_LINES = [
    (L_EAR, NOSE),
    (NOSE, R_EAR),
    (L_SHOULDER, R_SHOULDER),
    (L_SHOULDER, L_ELBOW),
    (R_SHOULDER, R_ELBOW),
]
MIN_VISIBILITY = 0.5


class MirroredLM:
    """Lightweight mirrored landmark proxy for natural mirror preview overlay."""
    __slots__ = ("x", "y", "visibility")

    def __init__(self, original):
        self.x = 1.0 - original.x
        self.y = original.y
        self.visibility = getattr(original, "visibility", 1.0)


def draw_pose_landmarks(frame, landmarks) -> None:
    """Draw upper-body skeletal landmarks directly on the frame (in-place)."""
    h, w = frame.shape[:2]

    def pos(idx):
        return int(landmarks[idx].x * w), int(landmarks[idx].y * h)

    for a, b in KEY_LINES:
        if (landmarks[a].visibility >= MIN_VISIBILITY and
                landmarks[b].visibility >= MIN_VISIBILITY):
            cv2.line(frame, pos(a), pos(b), (245, 180, 0), 2, cv2.LINE_AA)

    for i in KEY_POINTS:
        if landmarks[i].visibility >= MIN_VISIBILITY:
            cv2.circle(frame, pos(i), 5, (0, 220, 100), -1, cv2.LINE_AA)
            cv2.circle(frame, pos(i), 6, (255, 255, 255), 1, cv2.LINE_AA)


class PostureWorker(QThread):
    """Decoupled worker running responsive camera capture and independent inference."""

    # Qt Signals
    frame_ready = Signal(QImage)
    posture_changed = Signal(str, str)  # label, display_name
    stats_updated = Signal(float, float, float, int, float)  # elapsed, good, poor, warnings, score
    warning_triggered = Signal(str)     # warning text
    warning_cleared = Signal()
    status_message = Signal(str, bool)  # message, is_error
    session_started = Signal(str, object)  # session_code, db_session_id
    session_finished = Signal(dict)
    diagnostics_updated = Signal(float, float, float)  # preview_fps, inference_fps, latency_ms

    def __init__(
        self,
        config: AppConfig,
        api_client: PulseApiClient,
        audio_manager: AudioManager,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.api_client = api_client
        self.audio = audio_manager
        self._running = False
        self._show_landmarks = config.show_landmarks

        # Concurrency & Decoupling primitives
        self._frame_lock = threading.Lock()
        self._latest_raw_frame = None  # Tuple: (numpy_frame, capture_monotonic_ts)
        self._latest_landmarks = None  # Cached landmarks for zero-latency preview overlay
        self._new_frame_event = threading.Event()

        # Telemetry metrics
        self._current_preview_fps = 0.0
        self._current_inference_fps = 0.0
        self._current_latency_ms = 0.0

    def set_show_landmarks(self, show: bool) -> None:
        self._show_landmarks = show

    def stop(self) -> None:
        """Signal all worker threads to terminate and release hardware."""
        self._running = False
        self._new_frame_event.set()

    def _capture_loop(self, cap: cv2.VideoCapture) -> None:
        """Dedicated high-speed camera capture loop. Always displays newest frame."""
        preview_counter = 0
        fps_start = time.monotonic()

        while self._running:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            capture_ts = time.monotonic()

            # Atomically update latest frame slot (dropping any unconsumed stale frames)
            with self._frame_lock:
                self._latest_raw_frame = (frame, capture_ts)
                landmarks = self._latest_landmarks

            # Notify inference worker that a new frame is available
            self._new_frame_event.set()

            # Generate immediate low-latency mirror preview
            display = cv2.flip(frame, 1)
            if self._show_landmarks and landmarks:
                mirrored_landmarks = [MirroredLM(p) for p in landmarks]
                draw_pose_landmarks(display, mirrored_landmarks)

            # Convert to QImage and emit immediately to UI thread
            display_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            dh, dw, channels = display_rgb.shape
            bytes_per_line = channels * dw
            q_img = QImage(
                display_rgb.data, dw, dh, bytes_per_line, QImage.Format.Format_RGB888
            ).copy()
            self.frame_ready.emit(q_img)

            # Measure actual preview FPS
            preview_counter += 1
            now = time.monotonic()
            dt = now - fps_start
            if dt >= 1.0:
                self._current_preview_fps = preview_counter / dt
                preview_counter = 0
                fps_start = now

    def run(self) -> None:
        self._running = True

        # 1. Validate files
        if not MODEL_PATH.exists():
            self.status_message.emit(f"MediaPipe pose task file not found at: {MODEL_PATH}", True)
            return

        if not CLASSIFIER_PATH.exists():
            self.status_message.emit(f"Classifier model file not found at: {CLASSIFIER_PATH}", True)
            return

        try:
            clf = joblib.load(CLASSIFIER_PATH)
        except Exception as exc:
            self.status_message.emit(f"Failed to load SVM model: {exc}", True)
            return

        # 2. Open Camera with optimized DirectShow buffer
        cap = cv2.VideoCapture(self.config.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            # Fallback without DSHOW if first attempt failed
            cap = cv2.VideoCapture(self.config.camera_index)
            if not cap.isOpened():
                self.status_message.emit(
                    f"Could not open camera {self.config.camera_index}. Please check privacy settings or close other apps.",
                    True,
                )
                return

        # Configure camera resolution and single-frame buffer
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.config.camera_width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.config.camera_height))
        cap.set(cv2.CAP_PROP_FPS, float(self.config.target_preview_fps))
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # 3. Initialize MediaPipe PoseLandmarker
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )

        # 4. Initialize Session
        session_code = uuid.uuid4().hex[:8]
        start_res = self.api_client.start_session(session_code)
        client_uuid = start_res.get("client_uuid")
        db_session_id = start_res.get("server_id")
        self.session_started.emit(session_code, db_session_id)

        timer = PostureTimer(
            threshold_s=self.config.poor_posture_threshold_seconds,
            cooldown_s=self.config.cooldown_seconds,
        )
        history = deque(maxlen=self.config.smoothing_window)

        good_seconds = 0.0
        poor_seconds = 0.0
        warnings_count = 0
        warning_until = 0.0
        last_warning_active = False

        start_time = time.monotonic()
        last_tick = start_time
        last_ts = 0
        last_live_sent = 0.0

        # Dedicated Capture Thread
        capture_thread = threading.Thread(
            target=self._capture_loop, args=(cap,), name="PulseCameraCapture", daemon=True
        )
        capture_thread.start()

        # Inference pacing (target rate around 10–15 FPS)
        target_fps = max(1.0, float(self.config.target_inference_fps))
        inference_interval = 1.0 / target_fps
        last_inference_time = 0.0
        inference_count = 0
        diag_timer = time.monotonic()

        self.status_message.emit("Monitoring active", False)

        try:
            with vision.PoseLandmarker.create_from_options(options) as landmarker:
                while self._running:
                    # Wait for fresh frame or brief timeout
                    self._new_frame_event.wait(timeout=0.04)
                    self._new_frame_event.clear()

                    if not self._running:
                        break

                    now = time.monotonic()
                    if now - last_inference_time < inference_interval:
                        # Regulate inference rate to avoid excessive CPU load
                        continue

                    # Fetch the newest frame from the atomic slot
                    with self._frame_lock:
                        raw_item = self._latest_raw_frame

                    if raw_item is None:
                        continue

                    frame, capture_ts = raw_item
                    last_inference_time = now

                    # Measure latency / frame age from hardware capture to inference start
                    latency_ms = (now - capture_ts) * 1000.0
                    self._current_latency_ms = latency_ms

                    h, w = frame.shape[:2]
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                    ts = int(now * 1000)
                    if ts <= last_ts:
                        ts = last_ts + 1
                    last_ts = ts

                    result = landmarker.detect_for_video(mp_image, ts)
                    lm = result.pose_landmarks[0] if result.pose_landmarks else None

                    # Cache latest landmarks for live preview overlay
                    with self._frame_lock:
                        self._latest_landmarks = lm

                    # Classification
                    raw_label = "no_person"
                    if lm and is_person_visible(lm, min_visibility=self.config.min_confidence):
                        feats = extract_features(lm, w, h)
                        if feats:
                            vec = features_to_vector(feats)
                            raw_label = str(clf.predict([vec])[0])
                        else:
                            raw_label = "uncertain"

                    history.append(raw_label)
                    label = Counter(history).most_common(1)[0][0]

                    # Exact monotonic time calculation
                    dt = now - last_tick
                    last_tick = now

                    if label == "poor_posture":
                        poor_seconds += dt
                    elif label in ("good", "lean_left", "lean_right"):
                        good_seconds += dt

                    elapsed = now - start_time
                    total_tracked = good_seconds + poor_seconds
                    score = (good_seconds / total_tracked * 100) if total_tracked > 0 else 0.0

                    # Check warning condition with strict threshold & cooldown
                    if timer.update(label, now):
                        warnings_count += 1
                        warning_until = now + self.config.warning_duration_seconds
                        self.audio.play_warning_alert()
                        self.warning_triggered.emit(
                            "Poor posture detected. Please sit up straight and relax your shoulders."
                        )
                        self.api_client.record_warning_event(
                            session_client_uuid=client_uuid,
                            posture_class=label,
                            duration_seconds=self.config.poor_posture_threshold_seconds,
                            server_session_id=db_session_id,
                        )

                    if now > warning_until and last_warning_active:
                        self.warning_cleared.emit()
                        last_warning_active = False
                    elif now <= warning_until:
                        last_warning_active = True

                    # Update UI telemetry
                    self.posture_changed.emit(label, label.replace("_", " ").title())
                    self.stats_updated.emit(elapsed, good_seconds, poor_seconds, warnings_count, score)

                    # Update diagnostic metrics periodically (~1 Hz)
                    inference_count += 1
                    diag_dt = now - diag_timer
                    if diag_dt >= 1.0:
                        self._current_inference_fps = inference_count / diag_dt
                        inference_count = 0
                        diag_timer = now
                        self.diagnostics_updated.emit(
                            self._current_preview_fps,
                            self._current_inference_fps,
                            self._current_latency_ms,
                        )

                    # Live Telemetry
                    if now - last_live_sent >= 1.0:
                        self.api_client.send_live_status({
                            "active": True,
                            "session_id": db_session_id,
                            "posture": label,
                            "warnings": warnings_count,
                            "good_seconds": good_seconds,
                            "poor_seconds": poor_seconds,
                        })
                        last_live_sent = now

        except Exception as exc:
            self.status_message.emit(f"Error during video processing: {exc}", True)
        finally:
            self._running = False
            self._new_frame_event.set()
            if capture_thread is not None and capture_thread.is_alive():
                capture_thread.join(timeout=1.0)
            cap.release()
            self.api_client.stop_live()

            # End session and emit summary
            summary = self.api_client.end_session(
                client_uuid=client_uuid,
                session_code=session_code,
                good_seconds=good_seconds,
                poor_seconds=poor_seconds,
                warning_count=warnings_count,
                server_id=db_session_id,
            )
            self.session_finished.emit(summary.get("data", {}))
            self.status_message.emit("Monitoring stopped", False)

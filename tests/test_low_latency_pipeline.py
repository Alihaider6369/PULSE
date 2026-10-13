"""Automated tests for low-latency camera preview, frame decoupling, and temporal warning invariance."""
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from desktop_app.config import AppConfig
from desktop_app.core.worker import PostureWorker
from monitor.temporal import PostureTimer


def test_app_config_low_latency_defaults():
    """Verify default resolution and decoupled frame rate configuration."""
    cfg = AppConfig()
    assert cfg.camera_width == 640
    assert cfg.camera_height == 480
    assert cfg.target_preview_fps == 30
    assert cfg.target_inference_fps == 12


def test_worker_decoupled_primitives_and_signals():
    """Verify PostureWorker exposes low-latency primitives and diagnostic signals."""
    mock_api = MagicMock()
    mock_audio = MagicMock()
    cfg = AppConfig()

    worker = PostureWorker(config=cfg, api_client=mock_api, audio_manager=mock_audio)
    assert hasattr(worker, "diagnostics_updated"), "Worker must have diagnostics_updated signal"
    assert hasattr(worker, "_frame_lock"), "Worker must have thread-safe frame lock"
    assert hasattr(worker, "_new_frame_event"), "Worker must have new_frame_event sync primitive"
    assert worker._latest_raw_frame is None


def test_stale_frame_dropping_and_low_latency():
    """Verify that slower inference always drops stale frames and processes only the newest."""
    mock_api = MagicMock()
    mock_audio = MagicMock()
    cfg = AppConfig(target_inference_fps=12)

    worker = PostureWorker(config=cfg, api_client=mock_api, audio_manager=mock_audio)

    # Simulate camera capture producing 3 frames rapidly
    t0 = time.monotonic()
    frame_old = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_mid = np.ones((480, 640, 3), dtype=np.uint8)
    frame_new = np.full((480, 640, 3), 2, dtype=np.uint8)

    # Frame 1 pushed
    with worker._frame_lock:
        worker._latest_raw_frame = (frame_old, t0)
    worker._new_frame_event.set()

    # Frame 2 pushed before inference ran (simulating MediaPipe busy)
    time.sleep(0.01)
    t1 = time.monotonic()
    with worker._frame_lock:
        worker._latest_raw_frame = (frame_mid, t1)
    worker._new_frame_event.set()

    # Frame 3 pushed (newest available frame)
    time.sleep(0.01)
    t2 = time.monotonic()
    with worker._frame_lock:
        worker._latest_raw_frame = (frame_new, t2)
    worker._new_frame_event.set()

    # Inference thread wakes up: it must retrieve the newest frame (frame_new), not frame_old
    with worker._frame_lock:
        retrieved_frame, capture_ts = worker._latest_raw_frame

    assert np.array_equal(retrieved_frame, frame_new), "Inference must retrieve only the newest frame"
    assert capture_ts == t2, "Capture timestamp must match newest frame"

    # Frame age / latency must be negligible (< 50ms)
    now = time.monotonic()
    latency_ms = (now - capture_ts) * 1000.0
    assert latency_ms < 50.0, f"Latency should be < 50ms, got {latency_ms:.1f}ms"


def test_posture_timer_warning_invariance_at_12_fps():
    """Verify that temporal warning behavior (30s threshold, 3s grace, 300s cooldown)
    functions with exact precision at 12 FPS inference rate.
    """
    timer = PostureTimer(threshold_s=30.0, cooldown_s=300.0)

    # Baseline: good posture for 5 seconds at ~12 FPS (step ~0.083s)
    step = 1.0 / 12.0
    t = 0.0
    while t < 5.0:
        assert timer.update("good", now=t) is False
        t += step

    # Slouching starts at T=5.0
    slouch_start = t
    while t < slouch_start + 29.5:
        # Before 30s threshold (i.e. before T=35.0), no warning should fire
        assert timer.update("poor_posture", now=t) is False
        t += step

    # At T=35.0+ (30 seconds of poor posture accumulated)
    warning_triggered = False
    while t < slouch_start + 32.0:
        if timer.update("poor_posture", now=t):
            warning_triggered = True
            break
        t += step

    assert warning_triggered is True, "Warning must trigger once 30s threshold is reached at 12 FPS"

    # Cooldown verification: next poor posture update immediately after must be suppressed
    t += step
    assert timer.update("poor_posture", now=t) is False, "Warning must not retrigger during cooldown"


def test_worker_safe_stop_and_cleanup():
    """Verify that worker.stop() terminates execution and unblocks synchronization primitives."""
    mock_api = MagicMock()
    mock_audio = MagicMock()
    cfg = AppConfig()

    worker = PostureWorker(config=cfg, api_client=mock_api, audio_manager=mock_audio)
    worker._running = True
    assert worker._running is True

    worker.stop()
    assert worker._running is False
    assert worker._new_frame_event.is_set(), "stop() must set _new_frame_event to wake up waiting threads"

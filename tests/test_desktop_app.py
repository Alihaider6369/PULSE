"""Automated verification suite for PULSE Desktop Application and ML components."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import joblib
import pytest

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop_app.config import AppConfig, CLASSIFIER_PATH, METADATA_PATH, MODEL_PATH
from desktop_app.core.client import PulseApiClient
from ml.pulse_features import FEATURE_NAMES, extract_features, features_to_vector, is_person_visible
from monitor.temporal import PostureTimer


# ---------------- ML Pipeline & Models ----------------

def test_model_and_metadata_exist():
    """Verify that model files and metadata exist on disk."""
    assert MODEL_PATH.exists(), f"MediaPipe model missing at {MODEL_PATH}"
    assert CLASSIFIER_PATH.exists(), f"Classifier joblib missing at {CLASSIFIER_PATH}"
    assert METADATA_PATH.exists(), f"Model metadata missing at {METADATA_PATH}"


def test_model_loading_and_classes():
    """Verify that the SVM model loads and classifies using the exact 4 posture classes."""
    clf = joblib.load(CLASSIFIER_PATH)
    assert hasattr(clf, "predict"), "Loaded classifier has no predict method"

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    expected_classes = ["good", "lean_left", "lean_right", "poor_posture"]
    assert meta["classes"] == expected_classes
    assert len(FEATURE_NAMES) == 13
    assert meta["feature_names"] == FEATURE_NAMES


def test_feature_extraction_and_inference():
    """Verify feature extraction and SVM inference on synthetic landmarks."""
    clf = joblib.load(CLASSIFIER_PATH)

    # Synthetic upright landmarks
    NOSE, L_EAR, R_EAR, L_SHOULDER, R_SHOULDER = 0, 7, 8, 11, 12
    lm = [SimpleNamespace(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    lm[NOSE] = SimpleNamespace(x=0.50, y=0.45, z=0.0, visibility=1.0)
    lm[L_EAR] = SimpleNamespace(x=0.55, y=0.43, z=0.0, visibility=1.0)
    lm[R_EAR] = SimpleNamespace(x=0.45, y=0.43, z=0.0, visibility=1.0)
    lm[L_SHOULDER] = SimpleNamespace(x=0.60, y=0.70, z=0.0, visibility=1.0)
    lm[R_SHOULDER] = SimpleNamespace(x=0.40, y=0.70, z=0.0, visibility=1.0)

    assert is_person_visible(lm, min_visibility=0.5) is True

    feats = extract_features(lm, 640, 480)
    assert feats is not None
    assert len(feats) == 13

    vec = features_to_vector(feats)
    assert len(vec) == 13

    pred = clf.predict([vec])[0]
    assert pred in ["good", "lean_left", "lean_right", "poor_posture"]


# ---------------- Temporal Logic & PostureTimer ----------------

def test_posture_timer_warning_and_cooldown():
    """Verify threshold, warning firing, and cooldown behavior."""
    timer = PostureTimer(threshold_s=30.0, cooldown_s=300.0)

    # T=0: Poor posture starts
    assert timer.update("poor_posture", now=100.0) is False

    # T=20: 20 seconds poor posture (under threshold of 30) -> no warning
    assert timer.update("poor_posture", now=120.0) is False

    # T=30: 30 seconds poor posture -> warning triggers!
    assert timer.update("poor_posture", now=130.0) is True

    # T=40: In cooldown period (10s since last warning, cooldown is 300s) -> no warning
    assert timer.update("poor_posture", now=140.0) is False

    # T=160: 30 seconds after previous reset, but still within 300s cooldown -> no warning
    assert timer.update("poor_posture", now=160.0) is False

    # T=431: 301 seconds after last warning (cooldown expired) -> warning triggers again
    assert timer.update("poor_posture", now=431.0) is True


def test_posture_timer_grace_period():
    """Verify that brief posture changes within grace period don't reset poor streak."""
    timer = PostureTimer(threshold_s=30.0, cooldown_s=300.0)

    timer.update("poor_posture", now=10.0)
    timer.update("poor_posture", now=20.0)

    # Brief good posture at T=22 (2s < 3s grace)
    timer.update("good", now=22.0)

    # Back to poor posture at T=23 -> poor_since is preserved
    timer.update("poor_posture", now=23.0)
    assert timer.poor_since == 10.0

    # At T=41 (31s elapsed from T=10) -> warning triggers
    assert timer.update("poor_posture", now=41.0) is True


# ---------------- Client & Offline Fallback ----------------

def test_api_client_offline_fallback(tmp_path):
    """Verify that when backend is offline, API client gracefully falls back to local storage."""
    client = PulseApiClient(base_url="http://127.0.0.1:9999/api")  # Non-existent port

    is_ok, msg, lat = client.check_health()
    assert is_ok is False
    assert "offline" in msg.lower() or "connection" in msg.lower()

    # Start session offline
    res_start = client.start_session(session_code="test1234")
    client_uuid = res_start["client_uuid"]
    assert client_uuid is not None
    assert res_start["data"]["session_code"] == "test1234"

    # End session offline
    res_end = client.end_session(
        client_uuid=client_uuid,
        session_code="test1234",
        good_seconds=80.0,
        poor_seconds=20.0,
        warning_count=1,
    )
    # Score calculation: 80 / (80 + 20) * 100 = 80.0%
    assert res_end["data"]["awareness_score"] == 80.0
    assert res_end["data"]["sync_status"] == "pending"


# ---------------- Headless Desktop UI Tests ----------------

def test_desktop_ui_initialization_and_views():
    """Verify that MainWindow and all 4 views instantiate without errors."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtWidgets import QApplication
    from desktop_app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    window = MainWindow()
    assert window is not None
    assert window.windowTitle().startswith("PULSE")

    # Check that all 4 stacked pages are present
    assert window.stack.count() == 4
    assert window.view_live is not None
    assert window.view_history is not None
    assert window.view_settings is not None
    assert window.view_connection is not None

    # Test initial LiveView state
    assert not window.view_live.btn_start.isHidden()
    assert window.view_live.btn_stop.isHidden()
    assert window.view_live.lbl_posture_value.text() == "Not Monitoring"

    # Test navigation switches
    window._on_nav_clicked(1)
    assert window.stack.currentIndex() == 1

    window._on_nav_clicked(2)
    assert window.stack.currentIndex() == 2

    window._on_nav_clicked(3)
    assert window.stack.currentIndex() == 3

    window._on_nav_clicked(0)
    assert window.stack.currentIndex() == 0

    # Test UI shutdown cleanup
    window.stop_monitoring()
    assert window.worker is None
    window.close()

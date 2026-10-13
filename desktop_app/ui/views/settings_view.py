"""Settings view for configuring posture thresholds, camera, and backend connection."""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop_app.config import AppConfig
from desktop_app.core.client import PulseApiClient
from desktop_app.ui.theme import COLORS


class SettingsView(QWidget):
    """Screen 3: Application & Monitoring Settings."""

    settings_saved = Signal(AppConfig)

    def __init__(
        self, config: AppConfig, api_client: PulseApiClient, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.config = config
        self.api_client = api_client
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(20)

        # Header
        header = QVBoxLayout()
        title = QLabel("Settings & Thresholds")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel("Tune detection sensitivity, alerts, and connection parameters")
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
        header.addWidget(title)
        header.addWidget(subtitle)
        main_layout.addLayout(header)

        # Settings Card
        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # 1. Poor posture threshold
        self.spn_threshold = QSpinBox()
        self.spn_threshold.setRange(5, 600)
        self.spn_threshold.setValue(int(self.config.poor_posture_threshold_seconds))
        self.spn_threshold.setSuffix(" seconds")
        form.addRow("Poor Posture Threshold:", self.spn_threshold)

        # 2. Cooldown
        self.spn_cooldown = QSpinBox()
        self.spn_cooldown.setRange(10, 3600)
        self.spn_cooldown.setValue(int(self.config.cooldown_seconds))
        self.spn_cooldown.setSuffix(" seconds")
        form.addRow("Cooldown Between Warnings:", self.spn_cooldown)

        # 3. Warning duration
        self.spn_warn_duration = QSpinBox()
        self.spn_warn_duration.setRange(1, 60)
        self.spn_warn_duration.setValue(int(self.config.warning_duration_seconds))
        self.spn_warn_duration.setSuffix(" seconds")
        form.addRow("Warning On-Screen Duration:", self.spn_warn_duration)

        # 4. Minimum confidence
        self.spn_confidence = QDoubleSpinBox()
        self.spn_confidence.setRange(0.1, 1.0)
        self.spn_confidence.setSingleStep(0.05)
        self.spn_confidence.setValue(self.config.min_confidence)
        form.addRow("Minimum Pose Landmark Confidence:", self.spn_confidence)

        # 5. Camera Index
        self.spn_camera = QSpinBox()
        self.spn_camera.setRange(0, 10)
        self.spn_camera.setValue(self.config.camera_index)
        form.addRow("Webcam Hardware Index:", self.spn_camera)

        # 6. Backend API URL
        self.txt_api_url = QLineEdit()
        self.txt_api_url.setText(self.config.api_url)
        form.addRow("Backend API Base URL:", self.txt_api_url)

        # 7. Sound enabled
        self.chk_sound = QCheckBox("Enable audible beep reminder when warning fires")
        self.chk_sound.setChecked(self.config.sound_enabled)
        form.addRow("Audio Notification:", self.chk_sound)

        card_layout.addLayout(form)

        # Feedback message
        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setStyleSheet("font-size: 13px; font-weight: 500;")
        card_layout.addWidget(self.lbl_feedback)

        # Button Row
        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("💾 Save Settings")
        self.btn_save.setProperty("class", "primary_button")
        self.btn_save.clicked.connect(self._save_settings)

        self.btn_reset = QPushButton("↺ Reset Defaults")
        self.btn_reset.setProperty("class", "secondary_button")
        self.btn_reset.clicked.connect(self._reset_defaults)

        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        main_layout.addWidget(card)

        # Note at bottom
        note = QLabel(
            "Note: Settings are saved locally and synced to your backend PostgreSQL database if online."
        )
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        main_layout.addWidget(note)
        main_layout.addStretch()

    def _save_settings(self) -> None:
        self.config.poor_posture_threshold_seconds = float(self.spn_threshold.value())
        self.config.cooldown_seconds = float(self.spn_cooldown.value())
        self.config.warning_duration_seconds = float(self.spn_warn_duration.value())
        self.config.min_confidence = float(self.spn_confidence.value())
        self.config.camera_index = int(self.spn_camera.value())
        self.config.api_url = self.txt_api_url.text().strip()
        self.config.sound_enabled = self.chk_sound.isChecked()

        # Persist locally
        self.config.save()
        self.api_client.set_base_url(self.config.api_url)

        # Attempt remote sync
        synced = self.api_client.update_backend_settings({
            "poor_posture_threshold_seconds": self.config.poor_posture_threshold_seconds,
            "cooldown_seconds": self.config.cooldown_seconds,
            "warning_duration_seconds": self.config.warning_duration_seconds,
            "sound_enabled": self.config.sound_enabled,
            "min_confidence": self.config.min_confidence,
        })

        if synced:
            self.lbl_feedback.setText("✓ Settings saved locally and synchronized with PostgreSQL backend.")
            self.lbl_feedback.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self.lbl_feedback.setText("✓ Settings saved locally (Backend offline: will apply locally).")
            self.lbl_feedback.setStyleSheet(f"color: {COLORS['warning']};")

        self.settings_saved.emit(self.config)

    def _reset_defaults(self) -> None:
        default = AppConfig()
        self.spn_threshold.setValue(int(default.poor_posture_threshold_seconds))
        self.spn_cooldown.setValue(int(default.cooldown_seconds))
        self.spn_warn_duration.setValue(int(default.warning_duration_seconds))
        self.spn_confidence.setValue(default.min_confidence)
        self.spn_camera.setValue(default.camera_index)
        self.txt_api_url.setText(default.api_url)
        self.chk_sound.setChecked(default.sound_enabled)
        self.lbl_feedback.setText("Defaults restored. Click 'Save Settings' to apply.")
        self.lbl_feedback.setStyleSheet(f"color: {COLORS['text_muted']};")

"""Live Monitoring view for webcam preview and posture awareness."""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.config import AppConfig
from desktop_app.ui.theme import COLORS


class LiveView(QWidget):
    """Screen 1: Live Monitoring interface."""

    start_requested = Signal()
    stop_requested = Signal()
    landmarks_toggled = Signal(bool)
    sound_toggled = Signal(bool)

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Header
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        title = QLabel("Live Posture Monitoring")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel("AI-assisted ergonomic feedback using your local webcam")
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_layout.addLayout(header_left)
        header_layout.addStretch()

        self.lbl_system_status = QLabel("● Ready")
        self.lbl_system_status.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #10b981; "
            "background-color: rgba(16, 185, 129, 0.15); "
            "padding: 6px 14px; border-radius: 12px;"
        )
        header_layout.addWidget(self.lbl_system_status)
        main_layout.addLayout(header_layout)

        # 2. Warning alert banner (hidden by default)
        self.banner_warning = QFrame()
        self.banner_warning.setStyleSheet(
            f"background-color: {COLORS['danger_bg']}; "
            f"border: 1px solid {COLORS['danger']}; "
            "border-radius: 8px; padding: 10px 16px;"
        )
        self.banner_warning.setVisible(False)
        banner_layout = QHBoxLayout(self.banner_warning)
        banner_layout.setContentsMargins(8, 6, 8, 6)
        self.lbl_warning_text = QLabel("⚠️ Please sit up straight and relax your shoulders")
        self.lbl_warning_text.setStyleSheet(
            f"color: {COLORS['danger']}; font-weight: 600; font-size: 14px;"
        )
        banner_layout.addWidget(self.lbl_warning_text)
        main_layout.addWidget(self.banner_warning)

        # 3. Content grid: Video on left, Controls & Stats on right
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # --- Left Column: Video Preview ---
        video_col = QVBoxLayout()
        video_col.setSpacing(10)

        self.video_frame = QFrame()
        self.video_frame.setProperty("class", "card")
        self.video_frame.setStyleSheet(
            f"background-color: #070a13; border: 1px solid {COLORS['border']}; border-radius: 12px;"
        )
        self.video_frame.setMinimumSize(560, 420)
        video_inner_layout = QVBoxLayout(self.video_frame)
        video_inner_layout.setContentsMargins(4, 4, 4, 4)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_placeholder_video()
        video_inner_layout.addWidget(self.video_label)
        video_col.addWidget(self.video_frame, stretch=1)

        # Video controls row
        video_ctrl_row = QHBoxLayout()
        self.chk_landmarks = QCheckBox("Show Pose Landmarks")
        self.chk_landmarks.setChecked(self.config.show_landmarks)
        self.chk_landmarks.toggled.connect(self.landmarks_toggled.emit)

        self.chk_sound = QCheckBox("Sound Alert on Warning")
        self.chk_sound.setChecked(self.config.sound_enabled)
        self.chk_sound.toggled.connect(self.sound_toggled.emit)

        video_ctrl_row.addWidget(self.chk_landmarks)
        video_ctrl_row.addSpacing(16)
        video_ctrl_row.addWidget(self.chk_sound)
        video_ctrl_row.addStretch()

        self.lbl_diagnostics = QLabel("Preview: -- FPS | Inference: -- FPS | Latency: -- ms")
        self.lbl_diagnostics.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; font-family: 'Segoe UI', monospace;"
        )
        video_ctrl_row.addWidget(self.lbl_diagnostics)

        video_col.addLayout(video_ctrl_row)

        content_layout.addLayout(video_col, stretch=3)

        # --- Right Column: Status & Real-time Metrics ---
        stats_col = QVBoxLayout()
        stats_col.setSpacing(14)

        # Card: Current Posture Status
        posture_card = QFrame()
        posture_card.setProperty("class", "card")
        posture_layout = QVBoxLayout(posture_card)
        posture_layout.setContentsMargins(18, 16, 18, 16)

        lbl_posture_header = QLabel("CURRENT POSTURE")
        lbl_posture_header.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {COLORS['text_muted']}; letter-spacing: 1px;"
        )
        posture_layout.addWidget(lbl_posture_header)

        self.lbl_posture_value = QLabel("Not Monitoring")
        self.lbl_posture_value.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #94a3b8; padding: 4px 0px;"
        )
        posture_layout.addWidget(self.lbl_posture_value)

        self.lbl_posture_desc = QLabel("Start monitoring to analyze posture")
        self.lbl_posture_desc.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        posture_layout.addWidget(self.lbl_posture_desc)
        stats_col.addWidget(posture_card)

        # Card: Primary Metrics
        metrics_card = QFrame()
        metrics_card.setProperty("class", "card")
        metrics_layout = QGridLayout(metrics_card)
        metrics_layout.setContentsMargins(16, 16, 16, 16)
        metrics_layout.setHorizontalSpacing(14)
        metrics_layout.setVerticalSpacing(14)

        # Awareness Score
        self.lbl_score_val = QLabel("--%")
        self.lbl_score_val.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #6366f1;"
        )
        lbl_score_title = QLabel("Awareness Score")
        lbl_score_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        metrics_layout.addWidget(self.lbl_score_val, 0, 0)
        metrics_layout.addWidget(lbl_score_title, 1, 0)

        # Warnings Count
        self.lbl_warnings_val = QLabel("0")
        self.lbl_warnings_val.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #f59e0b;"
        )
        lbl_warn_title = QLabel("Warnings")
        lbl_warn_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        metrics_layout.addWidget(self.lbl_warnings_val, 0, 1)
        metrics_layout.addWidget(lbl_warn_title, 1, 1)

        # Good Time
        self.lbl_good_val = QLabel("0m 0s")
        self.lbl_good_val.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #10b981;"
        )
        lbl_good_title = QLabel("Good Posture")
        lbl_good_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        metrics_layout.addWidget(self.lbl_good_val, 2, 0)
        metrics_layout.addWidget(lbl_good_title, 3, 0)

        # Poor Time
        self.lbl_poor_val = QLabel("0m 0s")
        self.lbl_poor_val.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #ef4444;"
        )
        lbl_poor_title = QLabel("Poor Posture")
        lbl_poor_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        metrics_layout.addWidget(self.lbl_poor_val, 2, 1)
        metrics_layout.addWidget(lbl_poor_title, 3, 1)

        stats_col.addWidget(metrics_card)

        # Session Time & Controls
        session_card = QFrame()
        session_card.setProperty("class", "card")
        session_layout = QVBoxLayout(session_card)
        session_layout.setContentsMargins(16, 16, 16, 16)
        session_layout.setSpacing(12)

        time_row = QHBoxLayout()
        lbl_elapsed_title = QLabel("Elapsed Time:")
        lbl_elapsed_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
        self.lbl_elapsed_val = QLabel("00:00:00")
        self.lbl_elapsed_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #f8fafc;")
        time_row.addWidget(lbl_elapsed_title)
        time_row.addStretch()
        time_row.addWidget(self.lbl_elapsed_val)
        session_layout.addLayout(time_row)

        self.btn_start = QPushButton("▶  Start Monitoring")
        self.btn_start.setProperty("class", "primary_button")
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self.start_requested.emit)
        session_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹  Stop Monitoring")
        self.btn_stop.setProperty("class", "danger_button")
        self.btn_stop.setMinimumHeight(44)
        self.btn_stop.setVisible(False)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        session_layout.addWidget(self.btn_stop)

        stats_col.addWidget(session_card)
        stats_col.addStretch()
        content_layout.addLayout(stats_col, stretch=2)

        main_layout.addLayout(content_layout)

    def _set_placeholder_video(self) -> None:
        """Render a placeholder image when camera is offline."""
        pixmap = QPixmap(560, 420)
        pixmap.fill(QColor("#070a13"))
        painter = QPainter(pixmap)
        painter.setPen(QColor(COLORS["text_muted"]))
        font = QFont("Segoe UI", 13)
        painter.setFont(font)
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "Camera is inactive.\nClick 'Start Monitoring' to begin posture tracking.",
        )
        painter.end()
        self.video_label.setPixmap(pixmap)

    # ---------------- Slot Updates ----------------

    def update_frame(self, image: QImage) -> None:
        """Display incoming video frame scaled to container with low rendering overhead."""
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.video_frame.width() - 10,
            self.video_frame.height() - 10,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.video_label.setPixmap(scaled)

    def update_diagnostics(self, preview_fps: float, inference_fps: float, latency_ms: float) -> None:
        """Display live frame rate and latency performance metrics."""
        self.lbl_diagnostics.setText(
            f"Preview: {preview_fps:.1f} FPS | Inference: {inference_fps:.1f} FPS | Latency: {latency_ms:.0f} ms"
        )

    def update_posture(self, label: str, display_name: str) -> None:
        self.lbl_posture_value.setText(display_name)
        color_map = {
            "good": (COLORS["success"], "Sitting with upright spine alignment"),
            "lean_left": (COLORS["warning"], "Leaning toward your left side"),
            "lean_right": (COLORS["warning"], "Leaning toward your right side"),
            "poor_posture": (COLORS["danger"], "Slouching or forward head tilt"),
            "no_person": (COLORS["text_muted"], "No person detected in frame"),
            "uncertain": (COLORS["text_muted"], "Key landmarks obstructed"),
        }
        color, desc = color_map.get(label, (COLORS["text_muted"], "Unknown state"))
        self.lbl_posture_value.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
        self.lbl_posture_desc.setText(desc)

    def update_stats(
        self, elapsed_s: float, good_s: float, poor_s: float, warnings: int, score: float
    ) -> None:
        # Format elapsed
        h = int(elapsed_s // 3600)
        m = int((elapsed_s % 3600) // 60)
        s = int(elapsed_s % 60)
        self.lbl_elapsed_val.setText(f"{h:02d}:{m:02d}:{s:02d}")

        # Good / Poor format
        gm, gs = int(good_s // 60), int(good_s % 60)
        pm, ps = int(poor_s // 60), int(poor_s % 60)
        self.lbl_good_val.setText(f"{gm}m {gs}s")
        self.lbl_poor_val.setText(f"{pm}m {ps}s")

        self.lbl_warnings_val.setText(str(warnings))

        # Score format
        if good_s + poor_s > 0:
            self.lbl_score_val.setText(f"{score:.0f}%")
            if score >= 80:
                self.lbl_score_val.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['success']};")
            elif score >= 60:
                self.lbl_score_val.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['warning']};")
            else:
                self.lbl_score_val.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['danger']};")
        else:
            self.lbl_score_val.setText("--%")

    def show_warning_alert(self, message: str) -> None:
        self.lbl_warning_text.setText(f"⚠️ {message}")
        self.banner_warning.setVisible(True)

    def clear_warning_alert(self) -> None:
        self.banner_warning.setVisible(False)

    def set_monitoring_state(self, is_monitoring: bool) -> None:
        self.btn_start.setVisible(not is_monitoring)
        self.btn_stop.setVisible(is_monitoring)
        if is_monitoring:
            self.lbl_system_status.setText("● Active")
            self.lbl_system_status.setStyleSheet(
                "font-size: 13px; font-weight: 600; color: #10b981; "
                "background-color: rgba(16, 185, 129, 0.15); "
                "padding: 6px 14px; border-radius: 12px;"
            )
        else:
            self.lbl_system_status.setText("● Stopped")
            self.lbl_system_status.setStyleSheet(
                "font-size: 13px; font-weight: 600; color: #94a3b8; "
                "background-color: rgba(148, 163, 184, 0.15); "
                "padding: 6px 14px; border-radius: 12px;"
            )
            self._set_placeholder_video()
            self.clear_warning_alert()
            self.lbl_posture_value.setText("Not Monitoring")
            self.lbl_posture_value.setStyleSheet("font-size: 22px; font-weight: bold; color: #94a3b8;")
            self.lbl_posture_desc.setText("Start monitoring to analyze posture")
            self.lbl_diagnostics.setText("Preview: -- FPS | Inference: -- FPS | Latency: -- ms")

"""Main application window for PULSE Desktop."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.config import AppConfig
from desktop_app.core.audio import AudioManager
from desktop_app.core.client import PulseApiClient
from desktop_app.core.sync_service import SyncService
from desktop_app.core.worker import PostureWorker
from desktop_app.ui.theme import COLORS, STYLESHEET
from desktop_app.ui.views.connection_view import ConnectionView
from desktop_app.ui.views.history_view import HistoryView
from desktop_app.ui.views.live_view import LiveView
from desktop_app.ui.views.settings_view import SettingsView


class MainWindow(QMainWindow):
    """Main window with sidebar navigation and stacked screens."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("PULSE — AI Desk Posture Awareness")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(STYLESHEET)

        # Core components
        self.config = AppConfig.load()
        self.api_client = PulseApiClient(base_url=self.config.api_url)
        self.audio_manager = AudioManager(enabled=self.config.sound_enabled)
        self.worker: Optional[PostureWorker] = None

        # Background synchronization service
        self.sync_service = SyncService(
            api_client=self.api_client,
            storage=self.api_client.storage,
            interval_ms=15000,
            parent=self,
        )

        self._init_ui()
        self._check_initial_connection()
        self.sync_service.start()

    def _init_ui(self) -> None:
        root_widget = QWidget()
        self.setCentralWidget(root_widget)

        main_layout = QHBoxLayout(root_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(6)

        # Brand
        lbl_title = QLabel("PULSE")
        lbl_title.setObjectName("brand_title")
        lbl_sub = QLabel("Posture Awareness")
        lbl_sub.setObjectName("brand_subtitle")
        sidebar_layout.addWidget(lbl_title)
        sidebar_layout.addWidget(lbl_sub)
        sidebar_layout.addSpacing(10)

        # Navigation Buttons
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_nav_live = QPushButton("📷  Live Monitoring")
        self.btn_nav_live.setProperty("class", "nav_button")
        self.btn_nav_live.setCheckable(True)
        self.btn_nav_live.setChecked(True)
        self.nav_group.addButton(self.btn_nav_live, 0)
        sidebar_layout.addWidget(self.btn_nav_live)

        self.btn_nav_history = QPushButton("📋  Session History")
        self.btn_nav_history.setProperty("class", "nav_button")
        self.btn_nav_history.setCheckable(True)
        self.nav_group.addButton(self.btn_nav_history, 1)
        sidebar_layout.addWidget(self.btn_nav_history)

        self.btn_nav_settings = QPushButton("⚙️  Settings")
        self.btn_nav_settings.setProperty("class", "nav_button")
        self.btn_nav_settings.setCheckable(True)
        self.nav_group.addButton(self.btn_nav_settings, 2)
        sidebar_layout.addWidget(self.btn_nav_settings)

        self.btn_nav_connection = QPushButton("🌐  Cloud & Sync")
        self.btn_nav_connection.setProperty("class", "nav_button")
        self.btn_nav_connection.setCheckable(True)
        self.nav_group.addButton(self.btn_nav_connection, 3)
        sidebar_layout.addWidget(self.btn_nav_connection)

        self.nav_group.idClicked.connect(self._on_nav_clicked)

        sidebar_layout.addStretch()

        # User profile indicator in sidebar
        self.lbl_sidebar_user = QLabel("")
        self.lbl_sidebar_user.setStyleSheet(
            f"font-size: 11px; font-weight: 500; color: {COLORS['text_main']}; padding: 2px 12px;"
        )
        sidebar_layout.addWidget(self.lbl_sidebar_user)

        # Connection status indicator in sidebar
        self.lbl_sidebar_status = QLabel("● Offline Mode")
        self.lbl_sidebar_status.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; padding: 2px 12px 6px 12px;"
        )
        sidebar_layout.addWidget(self.lbl_sidebar_status)

        lbl_version = QLabel("v1.1.0 • Python 3.13")
        lbl_version.setStyleSheet(f"font-size: 10px; color: {COLORS['border_light']}; padding: 0 12px;")
        sidebar_layout.addWidget(lbl_version)

        main_layout.addWidget(sidebar)

        # 2. Right Stacked Pages
        self.stack = QStackedWidget()

        self.view_live = LiveView(config=self.config)
        self.view_history = HistoryView(api_client=self.api_client)
        self.view_settings = SettingsView(config=self.config, api_client=self.api_client)
        self.view_connection = ConnectionView(config=self.config, api_client=self.api_client)

        self.stack.addWidget(self.view_live)        # Index 0
        self.stack.addWidget(self.view_history)     # Index 1
        self.stack.addWidget(self.view_settings)    # Index 2
        self.stack.addWidget(self.view_connection)  # Index 3

        main_layout.addWidget(self.stack, stretch=1)

        # Connect Live View events
        self.view_live.start_requested.connect(self.start_monitoring)
        self.view_live.stop_requested.connect(self.stop_monitoring)
        self.view_live.landmarks_toggled.connect(self._on_landmarks_toggled)
        self.view_live.sound_toggled.connect(self._on_sound_toggled)

        # Connect Settings View events
        self.view_settings.settings_saved.connect(self._on_settings_saved)

        # Connect Connection View events
        self.view_connection.account_changed.connect(self._on_account_changed)
        self.view_connection.sync_now_requested.connect(self.sync_service.trigger_sync)

        # Connect Sync Service signals
        self.sync_service.sync_finished.connect(self._on_sync_finished)

        self._update_user_label()

    def _on_nav_clicked(self, page_index: int) -> None:
        self.stack.setCurrentIndex(page_index)
        if page_index == 1:
            self.view_history.refresh_sessions()
        elif page_index == 3:
            self.view_connection.check_connection()

    def _update_user_label(self) -> None:
        if self.api_client.is_authenticated():
            email = self.api_client.get_user_email() or ""
            short = email if len(email) < 22 else email[:19] + "..."
            self.lbl_sidebar_user.setText(f"👤 {short}")
            self.lbl_sidebar_user.setVisible(True)
        else:
            self.lbl_sidebar_user.setText("👤 Guest Profile")
            self.lbl_sidebar_user.setVisible(True)

    def _on_account_changed(self) -> None:
        self._update_user_label()
        self.view_history.refresh_sessions()

    def _on_sync_finished(self, synced: int, failed: int, error_msg: Optional[str]) -> None:
        self.view_connection.refresh_account_view()
        if synced > 0:
            self.view_history.refresh_sessions()

    def _check_initial_connection(self) -> None:
        is_ok, msg, _ = self.api_client.check_health()
        if is_ok:
            self.lbl_sidebar_status.setText("● Cloud Online")
            self.lbl_sidebar_status.setStyleSheet(
                f"font-size: 11px; color: {COLORS['success']}; padding: 2px 12px 6px 12px;"
            )
        else:
            self.lbl_sidebar_status.setText("● Local Offline")
            self.lbl_sidebar_status.setStyleSheet(
                f"font-size: 11px; color: {COLORS['warning']}; padding: 2px 12px 6px 12px;"
            )

    # ---------------- Monitoring Lifecycle ----------------

    def start_monitoring(self) -> None:
        """Start the background camera and inference pipeline."""
        if self.worker is not None and self.worker.isRunning():
            return

        self.worker = PostureWorker(
            config=self.config,
            api_client=self.api_client,
            audio_manager=self.audio_manager,
            parent=self,
        )

        # Wire worker signals
        self.worker.frame_ready.connect(self.view_live.update_frame)
        self.worker.posture_changed.connect(self.view_live.update_posture)
        self.worker.stats_updated.connect(self.view_live.update_stats)
        self.worker.warning_triggered.connect(self.view_live.show_warning_alert)
        self.worker.warning_cleared.connect(self.view_live.clear_warning_alert)
        self.worker.diagnostics_updated.connect(self.view_live.update_diagnostics)
        self.worker.status_message.connect(self._on_worker_status)
        self.worker.session_finished.connect(self._on_session_finished)

        self.worker.start()
        self.view_live.set_monitoring_state(True)

    def stop_monitoring(self) -> None:
        """Safely stop the worker and release camera hardware."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None

        self.view_live.set_monitoring_state(False)

    def _on_landmarks_toggled(self, show: bool) -> None:
        self.config.show_landmarks = show
        self.config.save()
        if self.worker is not None:
            self.worker.set_show_landmarks(show)

    def _on_sound_toggled(self, enabled: bool) -> None:
        self.config.sound_enabled = enabled
        self.config.save()
        self.audio_manager.set_enabled(enabled)

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        self.config = new_config
        self.audio_manager.set_enabled(new_config.sound_enabled)
        self.api_client.set_base_url(new_config.api_url)
        self._check_initial_connection()

    def _on_worker_status(self, message: str, is_error: bool) -> None:
        if is_error:
            self.stop_monitoring()
            QMessageBox.warning(self, "Camera / Model Notice", message)

    def _on_session_finished(self, summary: dict) -> None:
        self.view_history.refresh_sessions()
        # Trigger background sync when session completes
        self.sync_service.trigger_sync()

    # ---------------- Application Shutdown ----------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure all camera resources and sync workers are cleanly released on close."""
        self.sync_service.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None
        event.accept()

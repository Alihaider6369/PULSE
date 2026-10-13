"""Enhanced Connection & Cloud Sync Status view with account controls and queue inspection."""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.config import AppConfig
from desktop_app.core.client import PulseApiClient
from desktop_app.core.storage import LocalStorage
from desktop_app.ui.dialogs.auth_dialog import AuthDialog
from desktop_app.ui.theme import COLORS


class ConnectionView(QWidget):
    """Screen 4: Backend Connectivity, Health, Account, and Sync Queue."""

    account_changed = Signal()
    sync_now_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        api_client: PulseApiClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.api_client = api_client
        self.storage = api_client.storage
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(18)

        # Header
        header = QVBoxLayout()
        title = QLabel("Cloud Synchronization & Accounts")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel("Manage your secure user session, backend connection, and SQLite sync queue")
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
        header.addWidget(title)
        header.addWidget(subtitle)
        main_layout.addLayout(header)

        # --- Card 1: User Account & Authentication ---
        user_card = QFrame()
        user_card.setProperty("class", "card")
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(20, 16, 20, 16)

        user_info = QVBoxLayout()
        lbl_acc_title = QLabel("CURRENT ACCOUNT")
        lbl_acc_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLORS['text_muted']};")
        self.lbl_user_email = QLabel("Guest / Local Offline Profile")
        self.lbl_user_email.setStyleSheet("font-size: 16px; font-weight: bold; color: #f8fafc;")
        user_info.addWidget(lbl_acc_title)
        user_info.addWidget(self.lbl_user_email)
        user_layout.addLayout(user_info)
        user_layout.addStretch()

        self.btn_auth_action = QPushButton("🔑 Sign In / Register")
        self.btn_auth_action.setProperty("class", "primary_button")
        self.btn_auth_action.clicked.connect(self._handle_auth_action)
        user_layout.addWidget(self.btn_auth_action)

        main_layout.addWidget(user_card)

        # --- Card 2: Server Connectivity ---
        server_card = QFrame()
        server_card.setProperty("class", "card")
        server_layout = QVBoxLayout(server_card)
        server_layout.setContentsMargins(20, 18, 20, 18)
        server_layout.setSpacing(14)

        endpoint_row = QHBoxLayout()
        lbl_ep_title = QLabel("Backend REST Endpoint:")
        lbl_ep_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: 500;")
        self.lbl_endpoint_val = QLabel(self.config.api_url)
        self.lbl_endpoint_val.setStyleSheet("font-weight: bold; color: #f8fafc;")
        endpoint_row.addWidget(lbl_ep_title)
        endpoint_row.addWidget(self.lbl_endpoint_val)
        endpoint_row.addStretch()
        server_layout.addLayout(endpoint_row)

        status_row = QHBoxLayout()
        lbl_st_title = QLabel("Service Health:")
        lbl_st_title.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: 500;")
        self.lbl_status_badge = QLabel("Not Checked")
        self.lbl_status_badge.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #94a3b8; "
            "background-color: rgba(148, 163, 184, 0.15); "
            "padding: 5px 12px; border-radius: 12px;"
        )
        self.lbl_latency = QLabel("")
        self.lbl_latency.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")

        status_row.addWidget(lbl_st_title)
        status_row.addWidget(self.lbl_status_badge)
        status_row.addWidget(self.lbl_latency)
        status_row.addStretch()

        self.btn_test_conn = QPushButton("⚡ Test Connection")
        self.btn_test_conn.setProperty("class", "secondary_button")
        self.btn_test_conn.clicked.connect(self.check_connection)
        status_row.addWidget(self.btn_test_conn)

        server_layout.addLayout(status_row)
        main_layout.addWidget(server_card)

        # --- Card 3: SQLite Sync Queue Metrics ---
        queue_card = QFrame()
        queue_card.setProperty("class", "card")
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(20, 18, 20, 18)
        queue_layout.setSpacing(14)

        queue_header = QHBoxLayout()
        lbl_q_title = QLabel("Durable SQLite Sync Queue")
        lbl_q_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        queue_header.addWidget(lbl_q_title)
        queue_header.addStretch()

        self.btn_sync_now = QPushButton("🔄 Sync Now")
        self.btn_sync_now.setProperty("class", "primary_button")
        self.btn_sync_now.clicked.connect(self.sync_now_requested.emit)
        queue_header.addWidget(self.btn_sync_now)
        queue_layout.addLayout(queue_header)

        # Stats Grid
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(16)
        stats_grid.setVerticalSpacing(10)

        self.lbl_cnt_total = self._create_stat_badge("Total Local Records", "0", COLORS["primary"], stats_grid, 0)
        self.lbl_cnt_synced = self._create_stat_badge("Confirmed Synced", "0", COLORS["success"], stats_grid, 1)
        self.lbl_cnt_pending = self._create_stat_badge("Pending Sync", "0", COLORS["warning"], stats_grid, 2)
        self.lbl_cnt_failed = self._create_stat_badge("Failed (Retrying)", "0", COLORS["danger"], stats_grid, 3)

        queue_layout.addLayout(stats_grid)
        main_layout.addWidget(queue_card)
        main_layout.addStretch()

        self.refresh_account_view()

    def _create_stat_badge(
        self, label: str, value: str, color: str, grid: QGridLayout, col: int
    ) -> QLabel:
        box = QFrame()
        box.setStyleSheet(f"background-color: {COLORS['surface_light']}; border-radius: 8px; padding: 10px;")
        l = QVBoxLayout(box)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        title_lbl = QLabel(label)
        title_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        l.addWidget(val_lbl)
        l.addWidget(title_lbl)
        grid.addWidget(box, 0, col)
        return val_lbl

    def refresh_account_view(self) -> None:
        """Update account labels and sync queue badges."""
        if self.api_client.is_authenticated():
            email = self.api_client.get_user_email()
            self.lbl_user_email.setText(f"Signed in as: {email}")
            self.btn_auth_action.setText("🚪 Log Out")
            self.btn_auth_action.setStyleSheet(f"background-color: {COLORS['danger']}; color: white; border-radius: 8px; font-weight: 600; padding: 8px 16px;")
        else:
            self.lbl_user_email.setText("Guest / Local Offline Profile")
            self.btn_auth_action.setText("🔑 Sign In / Register")
            self.btn_auth_action.setStyleSheet(f"background-color: {COLORS['primary']}; color: white; border-radius: 8px; font-weight: 600; padding: 8px 16px;")

        # Update sync stats
        stats = self.storage.get_sync_stats(user_email=self.api_client.get_user_email())
        self.lbl_cnt_total.setText(str(stats["total"]))
        self.lbl_cnt_synced.setText(str(stats["synced"]))
        self.lbl_cnt_pending.setText(str(stats["pending"]))
        self.lbl_cnt_failed.setText(str(stats["failed"]))

    def _handle_auth_action(self) -> None:
        if self.api_client.is_authenticated():
            # Check for unsynced records before logging out
            stats = self.storage.get_sync_stats(user_email=self.api_client.get_user_email())
            pending_count = stats["pending"] + stats["failed"]
            if pending_count > 0:
                reply = QMessageBox.question(
                    self,
                    "Unsynchronized Records",
                    f"You have {pending_count} unsynced session(s) stored safely in local SQLite.\n\n"
                    "If you log out now, they will remain in local storage and synchronize "
                    "the next time you sign in to this account.\n\n"
                    "Do you wish to log out now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            self.api_client.logout()
            self.refresh_account_view()
            self.account_changed.emit()
        else:
            dlg = AuthDialog(api_client=self.api_client, parent=self)
            if dlg.exec():
                self.refresh_account_view()
                self.account_changed.emit()
                self.sync_now_requested.emit()

    def check_connection(self) -> None:
        self.lbl_endpoint_val.setText(self.api_client.base_url)
        is_ok, msg, latency = self.api_client.check_health()
        self.refresh_account_view()

        if is_ok:
            self.lbl_status_badge.setText("● Online")
            self.lbl_status_badge.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #10b981; "
                "background-color: rgba(16, 185, 129, 0.15); "
                "padding: 5px 12px; border-radius: 12px;"
            )
            lat_str = f"({latency:.0f} ms)" if latency is not None else ""
            self.lbl_latency.setText(lat_str)
        else:
            self.lbl_status_badge.setText(f"● {msg}")
            self.lbl_status_badge.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #ef4444; "
                "background-color: rgba(239, 68, 68, 0.15); "
                "padding: 5px 12px; border-radius: 12px;"
            )
            self.lbl_latency.setText("")

"""Session History view displaying past posture tracking sessions."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.core.client import PulseApiClient
from desktop_app.ui.theme import COLORS


def format_duration(seconds: float) -> str:
    s = int(round(seconds or 0))
    h = s // 3600
    m = (s % 3600) // 60
    rem_s = s % 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {rem_s}s"


def format_iso_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "-"
    try:
        # Handles ISO strings with or without timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(iso_str)[:19].replace("T", " ")


class HistoryView(QWidget):
    """Screen 2: Session History & Metrics."""

    refresh_requested = Signal()

    def __init__(self, api_client: PulseApiClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.api_client = api_client
        self._raw_sessions: List[Dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Header Row
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        title = QLabel("Session History")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel("Comprehensive record of your posture awareness sessions")
        subtitle.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_row.addLayout(header_text)
        header_row.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setProperty("class", "secondary_button")
        self.btn_refresh.clicked.connect(self.refresh_sessions)
        header_row.addWidget(self.btn_refresh)
        main_layout.addLayout(header_row)

        # 2. KPI Summary Cards
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(14)

        self.card_total_sessions = self._create_kpi_card("Total Sessions", "0", COLORS["primary"])
        self.card_total_time = self._create_kpi_card("Total Time", "0m 0s", COLORS["cyan"])
        self.card_avg_score = self._create_kpi_card("Avg Awareness Score", "--%", COLORS["success"])
        self.card_total_warnings = self._create_kpi_card("Total Warnings", "0", COLORS["warning"])

        summary_layout.addWidget(self.card_total_sessions)
        summary_layout.addWidget(self.card_total_time)
        summary_layout.addWidget(self.card_avg_score)
        summary_layout.addWidget(self.card_total_warnings)
        main_layout.addLayout(summary_layout)

        # 3. Filter Bar & Table Panel
        panel = QFrame()
        panel.setProperty("class", "card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(12)

        filter_row = QHBoxLayout()
        lbl_filter = QLabel("Filter by Score:")
        lbl_filter.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: 500;")
        filter_row.addWidget(lbl_filter)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems([
            "All Sessions",
            "Score ≥ 80% (Good)",
            "Score 60% – 79% (Fair)",
            "Score < 60% (Poor)",
        ])
        self.cmb_filter.currentIndexChanged.connect(self._apply_filter)
        self.cmb_filter.setMinimumWidth(180)
        filter_row.addWidget(self.cmb_filter)
        filter_row.addStretch()

        panel_layout.addLayout(filter_row)

        # History Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Started At",
            "Duration",
            "Good Posture",
            "Poor Posture",
            "Warnings",
            "Awareness Score",
            "Source",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        panel_layout.addWidget(self.table)

        main_layout.addWidget(panel)

    def _create_kpi_card(self, title: str, initial_value: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        lbl_val = QLabel(initial_value)
        lbl_val.setObjectName("val")
        lbl_val.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {accent_color};")
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")

        layout.addWidget(lbl_val)
        layout.addWidget(lbl_title)
        return card

    def refresh_sessions(self) -> None:
        """Fetch updated session list and repopulate UI."""
        self._raw_sessions = self.api_client.fetch_sessions()
        self._update_kpis(self._raw_sessions)
        self._apply_filter()

    def _update_kpis(self, sessions: List[Dict[str, Any]]) -> None:
        total_count = len(sessions)
        total_seconds = sum(s.get("duration_seconds") or 0.0 for s in sessions)
        total_warnings = sum(s.get("warning_count") or 0 for s in sessions)

        scored = [s["awareness_score"] for s in sessions if s.get("awareness_score") is not None]
        avg_score = (sum(scored) / len(scored)) if scored else None

        self.card_total_sessions.findChild(QLabel, "val").setText(str(total_count))
        self.card_total_time.findChild(QLabel, "val").setText(format_duration(total_seconds))
        self.card_total_warnings.findChild(QLabel, "val").setText(str(total_warnings))

        score_label = self.card_avg_score.findChild(QLabel, "val")
        if avg_score is not None:
            score_label.setText(f"{avg_score:.0f}%")
        else:
            score_label.setText("--%")

    def _apply_filter(self) -> None:
        idx = self.cmb_filter.currentIndex()
        filtered = []

        for s in self._raw_sessions:
            score = s.get("awareness_score")
            if idx == 0:
                filtered.append(s)
            elif idx == 1 and score is not None and score >= 80:
                filtered.append(s)
            elif idx == 2 and score is not None and 60 <= score < 80:
                filtered.append(s)
            elif idx == 3 and score is not None and score < 60:
                filtered.append(s)

        self._populate_table(filtered)

    def _populate_table(self, sessions: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            # 1. Started At
            start_str = format_iso_date(s.get("started_at"))
            item_start = QTableWidgetItem(start_str)
            item_start.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_start)

            # 2. Duration
            item_dur = QTableWidgetItem(format_duration(s.get("duration_seconds") or 0.0))
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item_dur)

            # 3. Good
            item_good = QTableWidgetItem(format_duration(s.get("good_seconds") or 0.0))
            item_good.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_good)

            # 4. Poor
            item_poor = QTableWidgetItem(format_duration(s.get("poor_seconds") or 0.0))
            item_poor.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item_poor)

            # 5. Warnings
            item_warn = QTableWidgetItem(str(s.get("warning_count") or 0))
            item_warn.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_warn)

            # 6. Awareness Score
            score = s.get("awareness_score")
            score_text = f"{score:.1f}%" if score is not None else "--"
            item_score = QTableWidgetItem(score_text)
            item_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if score is not None:
                if score >= 80:
                    item_score.setForeground(Qt.GlobalColor.green)
                elif score >= 60:
                    item_score.setForeground(Qt.GlobalColor.yellow)
                else:
                    item_score.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 5, item_score)

            # 7. Sync / Source Status
            st = s.get("sync_status")
            is_offline = s.get("is_offline", False)
            if st == "synced" or not is_offline:
                source_text = "Cloud Synced"
                item_src = QTableWidgetItem(source_text)
                item_src.setForeground(Qt.GlobalColor.green)
            elif st == "pending":
                source_text = "Pending Sync"
                item_src = QTableWidgetItem(source_text)
                item_src.setForeground(Qt.GlobalColor.yellow)
            elif st == "failed":
                source_text = "Sync Failed (Retrying)"
                item_src = QTableWidgetItem(source_text)
                item_src.setForeground(Qt.GlobalColor.red)
            elif st == "syncing":
                source_text = "Syncing..."
                item_src = QTableWidgetItem(source_text)
                item_src.setForeground(Qt.GlobalColor.cyan)
            else:
                source_text = "Local Storage"
                item_src = QTableWidgetItem(source_text)
                item_src.setForeground(Qt.GlobalColor.darkYellow)

            item_src.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, item_src)


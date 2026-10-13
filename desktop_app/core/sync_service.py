"""Background synchronization service for PULSE Desktop."""
import threading
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from desktop_app.core.client import PulseApiClient
from desktop_app.core.storage import LocalStorage


class SyncService(QObject):
    """Background service to periodically push pending SQLite records to the cloud backend."""

    sync_started = Signal()
    sync_finished = Signal(int, int, object)  # synced_count, failed_count, error_msg
    stats_updated = Signal(dict)

    def __init__(
        self,
        api_client: PulseApiClient,
        storage: LocalStorage,
        interval_ms: int = 15000,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.api_client = api_client
        self.storage = storage
        self._is_syncing = False
        self._lock = threading.Lock()

        # Periodic timer
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.trigger_sync)

    def start(self) -> None:
        self.timer.start()
        self.trigger_sync()

    def stop(self) -> None:
        self.timer.stop()

    def trigger_sync(self) -> None:
        """Trigger synchronization in a non-blocking background thread."""
        if self._is_syncing:
            return

        def _run():
            with self._lock:
                self._is_syncing = True

            try:
                self.sync_started.emit()
                # 1. Ping health
                is_ok, _, _ = self.api_client.check_health()
                if not is_ok:
                    stats = self.storage.get_sync_stats(user_email=self.api_client.get_user_email())
                    self.stats_updated.emit(stats)
                    self.sync_finished.emit(0, 0, "Backend unreachable")
                    return

                # 2. Sync pending records
                synced, failed, err = self.api_client.sync_pending_records()
                stats = self.storage.get_sync_stats(user_email=self.api_client.get_user_email())
                self.stats_updated.emit(stats)
                self.sync_finished.emit(synced, failed, err)
            finally:
                with self._lock:
                    self._is_syncing = False

        threading.Thread(target=_run, daemon=True).start()

"""Audio feedback manager for posture warnings."""
import threading

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class AudioManager:
    """Non-blocking audio alert player."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def play_warning_alert(self) -> None:
        if not self.enabled or not HAS_WINSOUND:
            return

        def _play():
            try:
                # 800 Hz beep for 300 ms as configured in PULSE core
                winsound.Beep(800, 300)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

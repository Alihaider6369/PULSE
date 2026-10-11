"""Phase 9: temporal logic. No camera, no model here, so it is easy to test.

Rules:
  - A warning needs poor posture to last POOR_POSTURE_THRESHOLD_SECONDS
    continuously. One bad frame, or a short movement, resets nothing big:
    a short break of GRACE_SECONDS does not reset the timer.
  - After a warning, no new warning until COOLDOWN_SECONDS have passed.
"""
from dataclasses import dataclass
from typing import Optional

GRACE_SECONDS = 3.0   # brief good posture (e.g. a stretch) does not reset the timer


@dataclass
class PostureTimer:
    threshold_s: float
    cooldown_s: float
    poor_since: Optional[float] = None     # when the current poor streak started
    last_good_at: Optional[float] = None   # last time posture was good
    last_warning_at: Optional[float] = None

    def update(self, label: str, now: float) -> bool:
        """Feed one smoothed label with its timestamp (seconds).

        Returns True exactly when a warning should be shown.
        """
        if label == "poor_posture":
            self.last_good_at = None
            if self.poor_since is None:
                self.poor_since = now
            poor_for = now - self.poor_since
            in_cooldown = (self.last_warning_at is not None
                           and now - self.last_warning_at < self.cooldown_s)
            if poor_for >= self.threshold_s and not in_cooldown:
                self.last_warning_at = now
                self.poor_since = now   # restart the streak after warning
                return True
            return False

        # Not poor (good, uncertain, no person): allow a short grace period
        if label in ("good", "lean_left", "lean_right"):
            if self.last_good_at is None:
                self.last_good_at = now
            if now - self.last_good_at >= GRACE_SECONDS:
                self.poor_since = None
                self.last_good_at = None
        return False
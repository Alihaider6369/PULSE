"""Phase 9: all feedback settings in one place.

Change these numbers to tune the behaviour. No code changes needed.
"""

POOR_POSTURE_THRESHOLD_SECONDS = 30   # poor posture must last this long before a warning
COOLDOWN_SECONDS = 300                # after a warning, wait this long before the next one
SOUND_ENABLED = True                  # short beep when a warning is shown
WARNING_DURATION_SECONDS = 5          # how long the on-screen warning stays visible
SMOOTHING_WINDOW = 10                 # frames used for majority vote
MIN_CONFIDENCE = 0.5                  # below this, a frame counts as "uncertain"
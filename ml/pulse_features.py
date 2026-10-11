"""PULSE shared feature engineering.

This ONE module is used for dataset collection, model training and live
prediction, so features are always computed the same way.

Input : MediaPipe pose landmarks of the RAW (un-mirrored) camera frame.
Output: a dict of posture features (see FEATURE_NAMES).

All distances are divided by the shoulder width, so the numbers do not change
much when you sit closer to or farther from the camera.

Sign conventions (raw camera image, y points DOWN):
  shoulder_tilt_deg > 0  -> person's LEFT shoulder is lower
  head_offset_x     > 0  -> head is shifted toward person's LEFT side
  head_tilt_deg     > 0  -> person's LEFT ear is lower
  neck_angle_deg    > 0  -> head leans toward person's LEFT side
"""
import math
from typing import Dict, Optional, Sequence

# MediaPipe landmark indices used here
NOSE, L_EAR, R_EAR, L_SHOULDER, R_SHOULDER = 0, 7, 8, 11, 12

MIN_VISIBILITY = 0.5   # landmark confidence needed to trust a point

FEATURE_NAMES = [
    "shoulder_width_ratio",   # shoulder width / image width (closeness to camera)
    "shoulder_tilt_deg",      # slope of the shoulder line
    "head_offset_x",          # nose left/right of shoulder centre
    "nose_height",            # nose height above shoulder centre
    "ear_mid_height",         # mid-ear height above shoulder centre
    "ear_height_l",           # left ear height above left shoulder
    "ear_height_r",           # right ear height above right shoulder
    "ear_shoulder_dx_l",      # left ear sideways offset from left shoulder
    "ear_shoulder_dx_r",      # right ear sideways offset from right shoulder
    "head_tilt_deg",          # slope of the ear-to-ear line
    "neck_angle_deg",         # angle of shoulder-centre -> nose line vs vertical
    "head_shoulder_dist",     # distance shoulder centre -> nose
    "nose_z_rel",             # nose depth relative to shoulders (noisy estimate)
]


def is_person_visible(landmarks: Optional[Sequence],
                      min_visibility: float = MIN_VISIBILITY) -> bool:
    """Rule-based 'No Person' check using nose + both shoulders."""
    if not landmarks or len(landmarks) <= R_SHOULDER:
        return False
    key_vis = min(landmarks[NOSE].visibility,
                  landmarks[L_SHOULDER].visibility,
                  landmarks[R_SHOULDER].visibility)
    return key_vis >= min_visibility


def _deg(dy: float, dx: float) -> float:
    return math.degrees(math.atan2(dy, dx))


def extract_features(landmarks: Optional[Sequence],
                     image_width: int,
                     image_height: int) -> Optional[Dict[str, float]]:
    """Convert pose landmarks into posture features.

    Returns None if landmarks are missing or unusable.
    """
    if not landmarks or len(landmarks) <= R_SHOULDER:
        return None

    w, h = float(image_width), float(image_height)

    # Pixel coordinates (so x and y have the same scale)
    nose = (landmarks[NOSE].x * w, landmarks[NOSE].y * h)
    l_ear = (landmarks[L_EAR].x * w, landmarks[L_EAR].y * h)
    r_ear = (landmarks[R_EAR].x * w, landmarks[R_EAR].y * h)
    l_sh = (landmarks[L_SHOULDER].x * w, landmarks[L_SHOULDER].y * h)
    r_sh = (landmarks[R_SHOULDER].x * w, landmarks[R_SHOULDER].y * h)

    sw = math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1])   # shoulder width in px
    if sw < 5.0:                                            # shoulders not usable
        return None

    mid_sh = ((l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2)
    mid_ear = ((l_ear[0] + r_ear[0]) / 2, (l_ear[1] + r_ear[1]) / 2)

    up = mid_sh[1] - nose[1]              # positive when nose is above shoulders
    side = nose[0] - mid_sh[0]

    mid_sh_z = (landmarks[L_SHOULDER].z + landmarks[R_SHOULDER].z) / 2
    nose_z_rel = (landmarks[NOSE].z - mid_sh_z) * w / sw

    return {
        "shoulder_width_ratio": sw / w,
        "shoulder_tilt_deg": _deg(l_sh[1] - r_sh[1], l_sh[0] - r_sh[0]),
        "head_offset_x": side / sw,
        "nose_height": up / sw,
        "ear_mid_height": (mid_sh[1] - mid_ear[1]) / sw,
        "ear_height_l": (l_sh[1] - l_ear[1]) / sw,
        "ear_height_r": (r_sh[1] - r_ear[1]) / sw,
        "ear_shoulder_dx_l": (l_ear[0] - l_sh[0]) / sw,
        "ear_shoulder_dx_r": (r_ear[0] - r_sh[0]) / sw,
        "head_tilt_deg": _deg(l_ear[1] - r_ear[1], l_ear[0] - r_ear[0]),
        "neck_angle_deg": _deg(side, up),
        "head_shoulder_dist": math.hypot(side, up) / sw,
        "nose_z_rel": nose_z_rel,
    }


def features_to_vector(features: Dict[str, float]) -> list:
    """Dict -> list in the fixed FEATURE_NAMES order (what the ML model expects)."""
    return [features[name] for name in FEATURE_NAMES]


if __name__ == "__main__":
    # Self-test with a perfectly symmetric, upright "person"
    from types import SimpleNamespace as P

    lm = [P(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    lm[NOSE] = P(x=0.50, y=0.45, z=0.0, visibility=1.0)
    lm[L_EAR] = P(x=0.55, y=0.43, z=0.0, visibility=1.0)
    lm[R_EAR] = P(x=0.45, y=0.43, z=0.0, visibility=1.0)
    lm[L_SHOULDER] = P(x=0.60, y=0.70, z=0.0, visibility=1.0)
    lm[R_SHOULDER] = P(x=0.40, y=0.70, z=0.0, visibility=1.0)

    feats = extract_features(lm, 640, 480)
    for name in FEATURE_NAMES:
        print(f"{name:22s} {feats[name]:8.3f}")
    print("person visible:", is_person_visible(lm))
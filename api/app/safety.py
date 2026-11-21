"""Hard limits for follow sessions.

These are enforced twice: once in the cloud API (here) and again on the edge
laptop before any velocity command is sent. Values follow the feasibility study.
"""

from dataclasses import dataclass

ALLOWED_MODES = {"third_person"}  # "reverse_third_person" is a stretch goal
MIN_DISTANCE_M = 1.5
MAX_DISTANCE_M = 3.0
DEFAULT_DISTANCE_M = 2.0
MIN_HEIGHT_M = 0.5
MAX_HEIGHT_M = 2.5
DEFAULT_HEIGHT_M = 1.6
MAX_SPEED_MPS = 1.0  # low cap for indoor, walking-pace following
TOF_STOP_MM = 500  # back off if anything is closer than this straight ahead
LOST_HOVER_S = 2.0  # hover once the subject has been out of view this long
LOST_LAND_S = 10.0  # land if the subject is not re-acquired within this time


class SafetyError(ValueError):
    """Raised when a requested setting breaks a hard limit."""


@dataclass(frozen=True)
class FollowSettings:
    mode: str
    distance_m: float
    height_m: float


def validate_settings(mode: str, distance_m: float, height_m: float) -> FollowSettings:
    if mode not in ALLOWED_MODES:
        raise SafetyError(f"mode must be one of {sorted(ALLOWED_MODES)}")
    if not MIN_DISTANCE_M <= distance_m <= MAX_DISTANCE_M:
        raise SafetyError(f"distance_m must be between {MIN_DISTANCE_M} and {MAX_DISTANCE_M}")
    if not MIN_HEIGHT_M <= height_m <= MAX_HEIGHT_M:
        raise SafetyError(f"height_m must be between {MIN_HEIGHT_M} and {MAX_HEIGHT_M}")
    return FollowSettings(mode=mode, distance_m=distance_m, height_m=height_m)


def clamp_speed(speed_mps: float) -> float:
    return max(-MAX_SPEED_MPS, min(MAX_SPEED_MPS, speed_mps))

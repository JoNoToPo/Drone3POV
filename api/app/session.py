"""Follow-session state machine.

States: searching -> locked -> following <-> lost, and any state -> landing -> finished.
The vision pipeline feeds one Observation per frame; tick() returns the next state.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum

from . import safety
from .safety import FollowSettings


class State(str, Enum):
    SEARCHING = "searching"
    LOCKED = "locked"
    FOLLOWING = "following"
    LOST = "lost"
    LANDING = "landing"
    FINISHED = "finished"


@dataclass
class Observation:
    subject_visible: bool
    distance_m: float | None = None
    tof_mm: int | None = None
    link_ok: bool = True
    battery_pct: int = 100
    lost_for_s: float = 0.0  # seconds since the subject was last seen


@dataclass
class FollowSession:
    settings: FollowSettings
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: State = State.SEARCHING
    end_reason: str | None = None
    owner_id: int | None = None

    def stop(self, reason: str) -> None:
        if self.state not in (State.LANDING, State.FINISHED):
            self.state = State.LANDING
            self.end_reason = reason

    def tick(self, obs: Observation) -> State:
        """Advance the state machine by one observation. Safety triggers come first."""
        if self.state in (State.LANDING, State.FINISHED):
            return self.state

        if not obs.link_ok:
            return self._end("link_lost")
        if obs.battery_pct <= 15:
            return self._end("low_battery")
        if obs.tof_mm is not None and obs.tof_mm < safety.TOF_STOP_MM:
            return self._end("obstacle_too_close")
        if obs.distance_m is not None and obs.distance_m < safety.MIN_DISTANCE_M:
            return self._end("subject_too_close")

        if not obs.subject_visible:
            if self.state in (State.FOLLOWING, State.LOCKED):
                self.state = State.LOST
            if self.state == State.LOST and obs.lost_for_s >= safety.LOST_LAND_S:
                return self._end("subject_lost")
            return self.state

        # Subject visible again.
        if self.state == State.SEARCHING:
            self.state = State.LOCKED
        elif self.state in (State.LOST, State.LOCKED):
            self.state = State.FOLLOWING
        return self.state

    def _end(self, reason: str) -> State:
        self.state = State.LANDING
        self.end_reason = reason
        return self.state

    def confirm_landed(self) -> None:
        self.state = State.FINISHED

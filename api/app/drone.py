"""Drone adapter interface.

The follow controller talks only to DroneAdapter, so each physical drone gets its
own backend (RoboMaster TT via DJITelloPy, DJI Mini 2 via the mobile SDK, ...).
SimulatedDrone lets the API and state machine run with no hardware attached.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Telemetry:
    battery_pct: int
    height_m: float
    tof_mm: int | None  # None when nothing is in range (or the drone has no ToF)
    link_ok: bool


class DroneAdapter(Protocol):
    def connect(self) -> None: ...
    def takeoff(self) -> None: ...
    def land(self) -> None: ...
    def emergency_stop(self) -> None: ...
    def send_velocity(self, forward_mps: float, right_mps: float, up_mps: float, yaw_dps: float) -> None: ...
    def telemetry(self) -> Telemetry: ...


class SimulatedDrone:
    """In-memory drone for development and tests. Records what it was asked to do."""

    def __init__(self, battery_pct: int = 90) -> None:
        self.connected = False
        self.airborne = False
        self.emergency_stopped = False
        self.battery_pct = battery_pct
        self.height_m = 0.0
        self.tof_mm: int | None = None
        self.link_ok = True
        self.commands: list[tuple[str, tuple]] = []

    def connect(self) -> None:
        self.connected = True
        self.commands.append(("connect", ()))

    def takeoff(self) -> None:
        self.airborne = True
        self.height_m = 1.0
        self.commands.append(("takeoff", ()))

    def land(self) -> None:
        self.airborne = False
        self.height_m = 0.0
        self.commands.append(("land", ()))

    def emergency_stop(self) -> None:
        self.emergency_stopped = True
        self.airborne = False
        self.height_m = 0.0
        self.commands.append(("emergency_stop", ()))

    def send_velocity(self, forward_mps: float, right_mps: float, up_mps: float, yaw_dps: float) -> None:
        self.commands.append(("velocity", (forward_mps, right_mps, up_mps, yaw_dps)))

    def telemetry(self) -> Telemetry:
        return Telemetry(
            battery_pct=self.battery_pct,
            height_m=self.height_m,
            tof_mm=self.tof_mm,
            link_ok=self.link_ok,
        )

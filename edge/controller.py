"""Conservative, tunable follow-position controller and bridge HTTP client."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import httpx

from api.app import safety


@dataclass(frozen=True)
class ControllerConfig:
    follow_distance_m: float = safety.DEFAULT_DISTANCE_M
    forward_kp: float = 0.25
    right_kp: float = 0.25
    yaw_kp: float = 0.7
    max_speed_mps: float = 0.3
    max_yaw_dps: float = 12.0
    distance_deadband_m: float = 0.2
    lateral_deadband_m: float = 0.15
    bearing_deadband_deg: float = 4.0
    max_heading_error_deg: float = 55.0
    filter_alpha: float = 0.25
    camera_yaw_offset_deg: float = 0.0
    forward_sign: int = 1
    right_sign: int = 1
    yaw_sign: int = 1
    stable_observations: int = 5

    def validate(self) -> None:
        safety.validate_settings("third_person", self.follow_distance_m, safety.DEFAULT_HEIGHT_M)
        if not 0 < self.max_speed_mps <= safety.MAX_SPEED_MPS:
            raise ValueError(f"max_speed_mps must be in (0, {safety.MAX_SPEED_MPS}]")
        if not 0 < self.max_yaw_dps <= 90:
            raise ValueError("max_yaw_dps must be in (0, 90]")
        if min(self.forward_kp, self.right_kp, self.yaw_kp) < 0:
            raise ValueError("controller gains must be non-negative")
        if min(self.distance_deadband_m, self.lateral_deadband_m, self.bearing_deadband_deg) < 0:
            raise ValueError("deadbands must be non-negative")
        if not 0 < self.max_heading_error_deg <= 90:
            raise ValueError("max_heading_error_deg must be in (0, 90]")
        if not 0 < self.filter_alpha <= 1:
            raise ValueError("filter_alpha must be in (0, 1]")
        if any(sign not in (-1, 1) for sign in (self.forward_sign, self.right_sign, self.yaw_sign)):
            raise ValueError("axis signs must be -1 or 1")
        if self.stable_observations < 1:
            raise ValueError("stable_observations must be at least 1")


@dataclass(frozen=True)
class VelocityCommand:
    forward_mps: float = 0.0
    right_mps: float = 0.0
    up_mps: float = 0.0
    yaw_dps: float = 0.0
    reason: str = "waiting_for_target"
    land: bool = False

    def body(self) -> dict[str, float]:
        return {
            "forward_mps": self.forward_mps,
            "right_mps": self.right_mps,
            "up_mps": self.up_mps,
            "yaw_dps": self.yaw_dps,
        }


@dataclass(frozen=True)
class TargetObservation:
    received_at: float
    track_id: int | None
    visible: bool
    distance_m: float | None
    bearing_right_deg: float | None
    facing_yaw_deg: float | None


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


class FollowController:
    """Computes a body-frame velocity setpoint from the latest vision result."""

    def __init__(self, config: ControllerConfig) -> None:
        config.validate()
        self.config = config
        self._lock = threading.Lock()
        self._latest = TargetObservation(time.monotonic(), None, False, None, None, None)
        self._filtered: tuple[float, float, float] | None = None
        self._stable_count = 0

    def update(self, values: dict) -> None:
        now = time.monotonic()
        track_id = values.get("track_id")
        visible = bool(values.get("target_visible", False))
        distance = values.get("distance_m")
        bearing = values.get("bearing_right_deg")
        heading = values.get("facing_yaw_deg")
        valid = all(isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (distance, bearing, heading))

        with self._lock:
            if visible and valid:
                self._stable_count += 1
                sample = (float(distance), float(bearing), float(heading))
                alpha = self.config.filter_alpha
                if self._filtered is None or now - self._latest.received_at > 1.0:
                    self._filtered = sample
                else:
                    old_d, old_b, old_h = self._filtered
                    self._filtered = (
                        alpha * sample[0] + (1 - alpha) * old_d,
                        alpha * sample[1] + (1 - alpha) * old_b,
                        old_h + alpha * _wrap_degrees(sample[2] - old_h),
                    )
                distance, bearing, heading = self._filtered
            else:
                self._stable_count = 0
                distance = bearing = heading = None

            self._latest = TargetObservation(
                received_at=now,
                track_id=int(track_id) if track_id is not None else None,
                visible=visible,
                distance_m=float(distance) if distance is not None else None,
                bearing_right_deg=float(bearing) if bearing is not None else None,
                facing_yaw_deg=float(heading) if heading is not None else None,
            )

    def snapshot(self) -> TargetObservation:
        with self._lock:
            return self._latest

    def compute(self, now: float | None = None, max_observation_age_s: float = 0.5) -> VelocityCommand:
        observation = self.snapshot()
        current = time.monotonic() if now is None else now
        if observation.track_id is None:
            return VelocityCommand(reason="waiting_for_target")
        if current - observation.received_at > max_observation_age_s:
            return VelocityCommand(reason="stale_observation")
        if not observation.visible:
            return VelocityCommand(reason="target_lost")
        if None in (observation.distance_m, observation.bearing_right_deg, observation.facing_yaw_deg):
            return VelocityCommand(reason="measurement_unavailable")
        with self._lock:
            if self._stable_count < self.config.stable_observations:
                return VelocityCommand(reason="stabilizing_measurements")

        distance = observation.distance_m
        bearing_camera = observation.bearing_right_deg
        facing_camera = observation.facing_yaw_deg
        assert distance is not None and bearing_camera is not None and facing_camera is not None
        bearing = bearing_camera + self.config.camera_yaw_offset_deg
        facing = facing_camera + self.config.camera_yaw_offset_deg

        # The hard minimum is enforced as a land request, not a push-away command.
        if distance < safety.MIN_DISTANCE_M:
            return VelocityCommand(reason="subject_too_close", land=True)

        # This heading convention follows estimate_facing_yaw_deg(): 0° faces the
        # camera, 180° faces away. Hold if heading is not suitable for trailing.
        heading_error = abs(_wrap_degrees(facing - 180.0))
        if heading_error > self.config.max_heading_error_deg:
            return VelocityCommand(reason="subject_not_facing_away")

        r = math.radians(bearing)
        psi = math.radians(facing)
        person_x = distance * math.sin(r)
        person_z = distance * math.cos(r)
        heading_x = math.sin(psi)
        heading_z = -math.cos(psi)

        # Desired follower position is follow_distance behind the person's heading.
        right_error = person_x - self.config.follow_distance_m * heading_x
        forward_error = person_z - self.config.follow_distance_m * heading_z
        if abs(right_error) < self.config.lateral_deadband_m:
            right_error = 0.0
        if abs(forward_error) < self.config.distance_deadband_m:
            forward_error = 0.0

        yaw_error = 0.0 if abs(bearing) < self.config.bearing_deadband_deg else bearing
        return VelocityCommand(
            forward_mps=self.config.forward_sign * _clamp(
                self.config.forward_kp * forward_error, self.config.max_speed_mps
            ),
            right_mps=self.config.right_sign * _clamp(
                self.config.right_kp * right_error, self.config.max_speed_mps
            ),
            up_mps=0.0,
            yaw_dps=self.config.yaw_sign * _clamp(
                self.config.yaw_kp * yaw_error, self.config.max_yaw_dps
            ),
            reason="following",
        )


class BridgeClient:
    """Small HTTP client for the Android bridge on the local network."""

    def __init__(self, base_url: str, timeout_s: float = 0.5) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)

    def telemetry(self) -> dict:
        response = self._client.get("/v1/telemetry")
        response.raise_for_status()
        return response.json()

    def send_velocity(self, command: VelocityCommand) -> None:
        response = self._client.post("/v1/velocity", json=command.body())
        response.raise_for_status()

    def land(self) -> None:
        response = self._client.post("/v1/land", json={})
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()


class ControlWorker:
    """Sends setpoints at a fixed rate and lands after prolonged target loss."""

    def __init__(self, client: BridgeClient, controller: FollowController,
                 watchdog, rate_hz: float = 10.0, observation_timeout_s: float = 0.5) -> None:
        self.client = client
        self.controller = controller
        self.watchdog = watchdog
        self.period = 1.0 / rate_hz
        self.observation_timeout_s = observation_timeout_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="edge-follow-control", daemon=True)
        self._status_thread = threading.Thread(target=self._poll_telemetry, name="edge-bridge-telemetry", daemon=True)
        self._last_status_at = 0.0
        self._telemetry: dict = {}
        self._telemetry_lock = threading.Lock()
        self._last_reason: str | None = None
        self._land_requested = False

    def start(self) -> None:
        status = self.client.telemetry()
        if not status.get("link_ok"):
            raise RuntimeError("bridge reports link_ok=false")
        if not status.get("flying") or not status.get("virtual_stick"):
            raise RuntimeError("aircraft must already be flying with virtual sticks enabled; edge will not take off")
        decision = self.watchdog.evaluate(
            self.controller.snapshot(), status, time.monotonic(),
            telemetry_age_s=0.0, observation_timeout_s=self.observation_timeout_s,
        )
        if decision.action != "allow":
            raise RuntimeError(f"safety preflight blocked controller: {decision.reason}")
        with self._telemetry_lock:
            self._telemetry = status
            self._last_status_at = time.monotonic()
        self._status_thread.start()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._status_thread.is_alive():
            self._status_thread.join(timeout=1.0)
        if not self._land_requested:
            try:
                self.client.send_velocity(VelocityCommand(reason="controller_stopped"))
            except Exception as exc:
                print(f"Could not send final hover command: {exc}")

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            observation = self.controller.snapshot()
            with self._telemetry_lock:
                telemetry = dict(self._telemetry)
                status_age = started - self._last_status_at

            safety_decision = self.watchdog.evaluate(
                observation, telemetry, started,
                telemetry_age_s=status_age,
                observation_timeout_s=self.observation_timeout_s,
            )
            if safety_decision.reason == "flight_control_unavailable":
                print("Aircraft is no longer flying under virtual-stick control; stopping controller")
                self._stop.set()
                break
            elif safety_decision.action == "land":
                command = VelocityCommand(reason=safety_decision.reason, land=True)
            elif safety_decision.action == "hover":
                command = VelocityCommand(reason=safety_decision.reason)
            else:
                command = self.controller.compute(
                    now=started,
                    max_observation_age_s=self.observation_timeout_s,
                )

            if command.land:
                self._send_hover()
                try:
                    self.client.land()
                    self._land_requested = True
                    print(f"Landing requested: {command.reason}")
                except Exception as exc:
                    print(f"Could not request landing ({command.reason}): {exc}")
                self._stop.set()
                break

            try:
                self.client.send_velocity(command)
            except Exception as exc:
                print(f"Velocity request failed; bridge stale-command timeout should hover: {exc}")
            if command.reason != self._last_reason:
                print(f"Controller: {command.reason}; {command.body()}")
                self._last_reason = command.reason
            self._sleep(started)

    def _poll_telemetry(self) -> None:
        while not self._stop.wait(1.0):
            try:
                status = self.client.telemetry()
            except Exception as exc:
                print(f"Bridge telemetry unavailable; commands will hover if it stays stale: {exc}")
                continue
            with self._telemetry_lock:
                self._telemetry = status
                self._last_status_at = time.monotonic()

    def _send_hover(self) -> None:
        try:
            self.client.send_velocity(VelocityCommand(reason="hover"))
        except Exception:
            pass

    def _sleep(self, started: float) -> None:
        self._stop.wait(max(0.0, self.period - (time.monotonic() - started)))

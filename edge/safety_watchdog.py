"""Independent safety overrides for the edge follow controller."""

from __future__ import annotations

import math
from dataclasses import dataclass

from api.app import safety
from edge.controller import TargetObservation


EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class WatchdogConfig:
    boundary_center_lat: float
    boundary_center_lon: float
    boundary_radius_m: float
    boundary_margin_m: float = 2.0
    gps_lost_land_s: float = 2.0

    def validate(self) -> None:
        values = (
            self.boundary_center_lat, self.boundary_center_lon, self.boundary_radius_m,
            self.boundary_margin_m, self.gps_lost_land_s,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("watchdog settings must be finite numbers")
        if not -90 <= self.boundary_center_lat <= 90:
            raise ValueError("boundary center latitude must be between -90 and 90")
        if not -180 <= self.boundary_center_lon <= 180:
            raise ValueError("boundary center longitude must be between -180 and 180")
        if self.boundary_radius_m <= 0:
            raise ValueError("boundary radius must be positive")
        if not 0 < self.boundary_margin_m < self.boundary_radius_m:
            raise ValueError("boundary margin must be positive and smaller than boundary radius")
        if self.gps_lost_land_s <= 0:
            raise ValueError("gps lost land timeout must be positive")


@dataclass(frozen=True)
class WatchdogDecision:
    action: str  # "allow", "hover", or "land"
    reason: str
    boundary_distance_m: float | None = None


def distance_from_boundary_center_m(lat: float, lon: float, center_lat: float, center_lon: float) -> float:
    """Local tangent-plane distance, accurate enough for small flight areas."""
    lat_r = math.radians(lat)
    center_lat_r = math.radians(center_lat)
    north_m = math.radians(lat - center_lat) * EARTH_RADIUS_M
    east_m = math.radians(lon - center_lon) * EARTH_RADIUS_M * math.cos((lat_r + center_lat_r) / 2)
    return math.hypot(north_m, east_m)


class SafetyWatchdog:
    """Checks link, battery, target freshness/range, and a circular GPS geofence."""

    def __init__(self, config: WatchdogConfig) -> None:
        config.validate()
        self.config = config
        self._last_seen_at: float | None = None
        self._gps_lost_since: float | None = None

    def evaluate(
        self,
        observation: TargetObservation,
        telemetry: dict,
        now: float,
        *,
        telemetry_age_s: float,
        observation_timeout_s: float,
    ) -> WatchdogDecision:
        if telemetry_age_s > 2.0 or not telemetry.get("link_ok"):
            return WatchdogDecision("hover", "bridge_or_aircraft_link_lost")
        if not telemetry.get("flying") or not telemetry.get("virtual_stick"):
            return WatchdogDecision("hover", "flight_control_unavailable")
        if int(telemetry.get("battery_pct", 100)) <= 15:
            return WatchdogDecision("land", "low_battery")

        if observation.visible and observation.track_id is not None:
            self._last_seen_at = observation.received_at
        elif observation.track_id is not None and self._last_seen_at is not None:
            if now - self._last_seen_at >= safety.LOST_LAND_S:
                return WatchdogDecision("land", "subject_lost_too_long")
            return WatchdogDecision("hover", "target_lost")

        if now - observation.received_at > observation_timeout_s:
            if observation.track_id is not None and self._last_seen_at is not None:
                if now - self._last_seen_at >= safety.LOST_LAND_S:
                    return WatchdogDecision("land", "subject_lost_too_long")
            return WatchdogDecision("hover", "stale_observation")
        if observation.visible and observation.distance_m is None:
            return WatchdogDecision("hover", "distance_unavailable")
        if observation.distance_m is not None and observation.distance_m < safety.MIN_DISTANCE_M:
            return WatchdogDecision("land", "subject_too_close")

        position = self._gps_position(telemetry)
        if position is None:
            if self._gps_lost_since is None:
                self._gps_lost_since = now
            if now - self._gps_lost_since >= self.config.gps_lost_land_s:
                return WatchdogDecision("land", "gps_position_unavailable")
            return WatchdogDecision("hover", "gps_position_unavailable")
        self._gps_lost_since = None
        return self._boundary_decision(*position)

    def preflight(self, telemetry: dict) -> WatchdogDecision:
        """Start-up check: only what can be known before the first video frame.

        Vision isn't checked here, because no frame has been processed when the controller
        starts. That's safe: once running, evaluate() hovers until the locked subject has a
        fresh, valid observation.
        """
        if not telemetry.get("link_ok"):
            return WatchdogDecision("hover", "bridge_or_aircraft_link_lost")
        if not telemetry.get("flying") or not telemetry.get("virtual_stick"):
            return WatchdogDecision("hover", "flight_control_unavailable")
        if int(telemetry.get("battery_pct", 100)) <= 15:
            return WatchdogDecision("land", "low_battery")
        position = self._gps_position(telemetry)
        if position is None:
            return WatchdogDecision("hover", "gps_position_unavailable")
        return self._boundary_decision(*position)

    @staticmethod
    def _gps_position(telemetry: dict) -> tuple[float, float] | None:
        """(lat, lon) when the bridge reports a valid, finite GPS fix; otherwise None."""
        lat = telemetry.get("latitude")
        lon = telemetry.get("longitude")
        if (
            not bool(telemetry.get("gps_valid"))
            or not isinstance(lat, (int, float))
            or not isinstance(lon, (int, float))
            or not math.isfinite(lat)
            or not math.isfinite(lon)
        ):
            return None
        return float(lat), float(lon)

    def _boundary_decision(self, lat: float, lon: float) -> WatchdogDecision:
        boundary_distance = distance_from_boundary_center_m(
            lat, lon, self.config.boundary_center_lat, self.config.boundary_center_lon
        )
        if boundary_distance >= self.config.boundary_radius_m:
            return WatchdogDecision("land", "flight_boundary_exceeded", boundary_distance)
        if boundary_distance >= self.config.boundary_radius_m - self.config.boundary_margin_m:
            return WatchdogDecision("land", "flight_boundary_margin", boundary_distance)
        return WatchdogDecision("allow", "within_flight_boundary", boundary_distance)

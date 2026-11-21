"""DJI Mini 2 backend.

The Mini 2 has no Wi-Fi SDK. Control goes through DJI's Mobile SDK running on an
Android phone that is paired with the drone's RC (virtual-stick control). That
phone app is the "bridge": it exposes a small HTTP API, and this adapter calls it.

Facts this backend relies on (from DJI product pages and third-party spec sheets):
- Downward sensing only; NO forward obstacle sensor, so telemetry.tof_mm is always None.
  Obstacle safety for the Mini 2 therefore rests on the cleared area, the virtual
  boundary and trail following, not on a ToF stop.
- Under 250 g with the standard battery and propellers, so no registration is required.

Unverified until flown: whether the current MSDK velocity virtual sticks work on the Mini 2.
"""

from typing import Protocol

from . import safety
from .drone import Telemetry


class Transport(Protocol):
    def post(self, path: str, body: dict | None = None) -> dict: ...
    def get(self, path: str) -> dict: ...


class HttpBridgeTransport:
    """Talks to the Android bridge app over HTTP on the local network."""

    def __init__(self, base_url: str, timeout_s: float = 0.5) -> None:
        import httpx

        self._client = httpx.Client(base_url=base_url, timeout=timeout_s)

    def post(self, path: str, body: dict | None = None) -> dict:
        r = self._client.post(path, json=body or {})
        r.raise_for_status()
        return r.json()

    def get(self, path: str) -> dict:
        r = self._client.get(path)
        r.raise_for_status()
        return r.json()


class Mini2Adapter:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def connect(self) -> None:
        self._t.post("/v1/connect")

    def takeoff(self) -> None:
        self._t.post("/v1/takeoff")

    def land(self) -> None:
        self._t.post("/v1/land")

    def emergency_stop(self) -> None:
        # Bridge must stop the motors immediately; it does not wait for the phone's queue.
        self._t.post("/v1/emergency-stop")

    def send_velocity(self, forward_mps: float, right_mps: float, up_mps: float, yaw_dps: float) -> None:
        # Clamp on the laptop side as well as in the bridge app.
        self._t.post(
            "/v1/velocity",
            {
                "forward_mps": safety.clamp_speed(forward_mps),
                "right_mps": safety.clamp_speed(right_mps),
                "up_mps": safety.clamp_speed(up_mps),
                "yaw_dps": max(-90.0, min(90.0, yaw_dps)),
            },
        )

    def telemetry(self) -> Telemetry:
        d = self._t.get("/v1/telemetry")
        return Telemetry(
            battery_pct=int(d["battery_pct"]),
            height_m=float(d["height_m"]),
            tof_mm=None,  # no forward sensor on the Mini 2
            link_ok=bool(d["link_ok"]),
        )

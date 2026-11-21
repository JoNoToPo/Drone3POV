from app import safety
from app.mini2 import Mini2Adapter


class FakeBridge:
    def __init__(self, telemetry=None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self._telemetry = telemetry or {"battery_pct": 80, "height_m": 1.2, "link_ok": True}

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {}

    def get(self, path):
        self.calls.append(("GET", path, None))
        return self._telemetry


def test_velocity_is_clamped_before_sending():
    bridge = FakeBridge()
    Mini2Adapter(bridge).send_velocity(5.0, -5.0, 0.2, 500.0)
    _, path, body = bridge.calls[-1]
    assert path == "/v1/velocity"
    assert body["forward_mps"] == safety.MAX_SPEED_MPS
    assert body["right_mps"] == -safety.MAX_SPEED_MPS
    assert body["up_mps"] == 0.2
    assert body["yaw_dps"] == 90.0


def test_telemetry_has_no_tof_reading():
    t = Mini2Adapter(FakeBridge()).telemetry()
    assert t.tof_mm is None  # the Mini 2 has no forward sensor
    assert t.battery_pct == 80
    assert t.link_ok is True


def test_emergency_stop_goes_straight_to_bridge():
    bridge = FakeBridge()
    Mini2Adapter(bridge).emergency_stop()
    assert bridge.calls == [("POST", "/v1/emergency-stop", None)]


def test_app_uses_mini2_when_configured(monkeypatch):
    from app import main

    monkeypatch.setenv("DRONE", "mini2")
    monkeypatch.setenv("BRIDGE_URL", "http://127.0.0.1:1")  # not contacted for this check
    assert isinstance(main._default_drone(), Mini2Adapter)

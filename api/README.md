# Follow-me drone API (MVP scaffold)

Implements the cloud API and safety layer from the feasibility study (prjM4).
The control loop (vision, PID, drone link) runs on an edge laptop and is not in this scaffold yet.

## What is here

- `app/safety.py`: hard limits (distance 1.5–3 m, height band, speed cap, low-battery and ToF stop thresholds).
- `app/session.py`: follow-session state machine (searching → locked → following ⇄ lost → landing → finished).
- `app/drone.py`: `DroneAdapter` interface and a `SimulatedDrone` for development. Add one adapter per drone.
- `app/main.py`: REST API v1 (start, read, stop follow sessions; drone status; emergency stop).
- `tests/test_follow.py`: safety limits, state transitions, API behaviour.

## Run

From this `api/` folder, with the venv at the repo root:

```bash
py -3.13 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Set `FOLLOW_API_KEY` in the environment for anything beyond local development (default `dev-key`).

Python 3.14 alpha does not work with the current FastAPI/pydantic pins, so use 3.13.

## DJI Mini 2 (target drone)

- `app/mini2.py` calls an Android **bridge app** over HTTP. The bridge runs DJI's Mobile SDK on a phone paired with the Mini 2's RC and issues virtual-stick commands.
- Select it with `DRONE=mini2` and `BRIDGE_URL=http://<phone-ip>:<port>`. Without these, the simulator is used.
- The Mini 2 has **no forward obstacle sensor**. The TT's ToF stop does not apply, so telemetry reports `tof_mm = None`. Keep flights in the cleared, bounded area.
- Weight is under 250 g, so no registration is required for indoor flight. The camera records 4K, which is better than the 720p the study assumed.

Bridge endpoints the adapter expects: `POST /v1/connect`, `/v1/takeoff`, `/v1/land`, `/v1/emergency-stop`, `/v1/velocity` (`forward_mps`, `right_mps`, `up_mps`, `yaw_dps`), and `GET /v1/telemetry` (`battery_pct`, `height_m`, `link_ok`).

## Not yet built

- The Android bridge app. Its endpoints are defined above, but the app is not written.
- Whether MSDK velocity virtual sticks work on the Mini 2 is **unverified**. The search results were inconclusive, so test it on hardware with propellers off first.
- Vision pipeline, PID follow controller, recording, and the edge WebSocket hub.
- The feasibility study (Claude Docs) still describes the TT and the Wi-Fi UDP setup. Update it when the Mini 2 path is confirmed.
- Vision pipeline (YOLO, tracking, pose) and the PID follow controller on the edge laptop.
- Recording, database, auth beyond a single shared key, and the edge WebSocket hub.

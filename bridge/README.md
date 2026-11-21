# bridge

Android app that flies the DJI Mini 2 through DJI's Mobile SDK (virtual-stick control). The phone is paired with the Mini 2's RC and exposes a small API on the local network for the edge laptop. Not started yet.

## API it must expose

The Python adapter in `api/app/mini2.py` already calls these:

| Method | Path | Body or response |
| --- | --- | --- |
| POST | `/v1/connect` | |
| POST | `/v1/takeoff` | |
| POST | `/v1/land` | |
| POST | `/v1/emergency-stop` | Stops the motors at once, skipping any queue |
| POST | `/v1/velocity` | `forward_mps`, `right_mps`, `up_mps`, `yaw_dps` |
| GET | `/v1/telemetry` | `battery_pct`, `height_m`, `link_ok` |

Velocity commands need a steady rate, so a WebSocket will likely replace per-command HTTP once the control loop runs.

## Open questions

- Does the current MSDK support velocity virtual sticks on the Mini 2? Test with the propellers off first.
- The SDK needs the app registered online on first run, so the phone needs internet at least once.

## Secrets

Never commit the DJI app key. Load it from `local.properties` or an environment variable.

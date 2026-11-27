# bridge

Android app that flies the DJI Mini 2 through DJI's Mobile SDK v4 (virtual-stick control). The phone is plugged into the Mini 2's RC and serves a small HTTP API on the local network for the edge laptop. `api/app/mini2.py` is the client.

Kotlin, MSDK 4.18, NanoHTTPD. The Mini 2 isn't supported by MSDK v5, so this has to stay on v4.

## Setup

1. Register an app at developer.dji.com with package name `ca.bcit.drone3pov.bridge` and copy the key.
2. Copy `local.properties.example` to `local.properties` and fill in both lines. That file is git-ignored. Never commit the key.
   - `sdk.dir`: your Android SDK folder, usually `C:/Users/<your-windows-user>/AppData/Local/Android/Sdk` (forward slashes work; backslashes must be doubled). Android Studio shows it under **Settings → Languages & Frameworks → Android SDK**. Android Studio won't overwrite the example's placeholder path, so if you leave it, the build fails with "SDK location not found".
   - `DJI_API_KEY`: the key from step 1.

   The DJI Mobile SDK itself (`com.dji:dji-sdk:4.18`) isn't downloaded by hand: Gradle fetches it from Maven Central on the first build. You need the **Android 13 (API 33)** platform installed in the SDK Manager, because the app compiles against it.
3. Open this `bridge/` folder in Android Studio (not the repo root) and let it sync.
4. Run on an Android phone (7.0 or newer). The first run needs internet so the SDK can register.
5. Plug the phone into the RC, power on the drone, and accept the USB prompt.

The screen shows the URL to use, for example `http://192.168.1.42:8765`. On the edge laptop:

```powershell
$env:DRONE="mini2"; $env:BRIDGE_URL="http://192.168.1.42:8765"
```

The laptop and phone need to be on the same Wi-Fi. The app keeps running in a foreground service with Wi-Fi and CPU locks, so the screen can turn off.

## API

| Method | Path | Body or response |
| --- | --- | --- |
| POST | `/v1/connect` | Checks the SDK and drone are ready and clears the emergency-stop latch |
| POST | `/v1/takeoff` | Auto takeoff; virtual sticks turn on once it finishes |
| POST | `/v1/land` | Gives control back from virtual sticks and auto-lands, confirming the landing at 0.3 m |
| POST | `/v1/emergency-stop` | See below. Response has `action` |
| POST | `/v1/velocity` | `forward_mps`, `right_mps`, `up_mps`, `yaw_dps` (all required) |
| GET | `/v1/telemetry` | `battery_pct`, `height_m`, `link_ok`, plus debug fields (`flying`, `virtual_stick`, `estopped`, `simulator_active`, `simulator`, ...) |
| POST | `/v1/simulator/start` | Starts DJI's simulator on the drone. Optional `latitude`, `longitude` (default: BCIT Burnaby). Ground only, motors off |
| POST | `/v1/simulator/stop` | Stops the simulator. Refused while the simulated aircraft is flying |

Successful calls return `{"ok": true, ...}`. Errors return `{"ok": false, "error": "..."}` with a status code: 400 bad body, 409 wrong state (not flying, landing, emergency stop latched), 503 SDK or drone not ready.

Every call returns right away, since `mini2.py` uses a 0.5 s timeout. Takeoff and land run in the background; poll `/v1/telemetry` for `flying` and `virtual_stick`.

## Safety behaviour

- **Stale commands hover.** The bridge sends stick data to the drone at 20 Hz using the latest setpoint. If no `/v1/velocity` has arrived in the last 300 ms, it sends zeros. The edge controller should post at 10 Hz or faster.
- **Limits are enforced again here.** Speed is clamped to 1 m/s and yaw to 90 °/s, the same values as `api/app/safety.py`. No climbing above 2.5 m, no velocity descent below 0.5 m, and no climbing when the height is unknown. Limits live in `core/Limits.kt`; change them together with `safety.py`.
- **Emergency stop latches.** After `/v1/emergency-stop`, velocity and takeoff are refused until `/v1/connect` is called. Each request has its own thread, so the stop never waits behind other calls. The phone screen has a big stop button too.
- **What emergency stop actually does depends on the drone's state.** On the ground with motors running it turns the motors off (`motors_off`). In the air, MSDK v4 has no way to cut the Mini 2's motors, so it brakes to a hover and lands in place (`hover_then_land`). The README in `api/` says "stops the motors at once"; that's only true on the ground.

## Code layout

- `core/` is plain Kotlin with no Android or DJI imports: limits, the velocity gate (timeout, latch, height guard) and the HTTP router. Unit tests cover it (`./gradlew test`, 27 tests).
- `DjiDrone.kt` is everything that touches the SDK: registration, state callbacks, the 20 Hz stick loop, takeoff, landing and the stop.
- `HttpBridgeServer.kt` adapts NanoHTTPD to the router. `BridgeService.kt` keeps it alive. `MainActivity.kt` is the status screen.

## Testing with DJI's simulator (propellers off)

DJI's simulator runs on the Mini 2's own flight controller. You still need the phone, the RC and the
drone, but the drone stays on the ground while takeoff and velocity commands move a virtual aircraft.
**The motors may spin, so take the propellers off first.** The phone screen shows a `SIMULATOR ON`
banner while it runs.

In Git Bash, with the URL from the phone screen:

```bash
B=http://<phone-ip>:8765
curl -X POST $B/v1/connect
curl -X POST $B/v1/simulator/start
curl $B/v1/telemetry        # repeat until "simulator_active": true
curl -X POST $B/v1/takeoff
curl $B/v1/telemetry        # repeat until "flying": true and "virtual_stick": true
```

**Axis check.** Send forward-only commands for about 2 seconds. The bridge needs one at least every
300 ms, so loop them:

```bash
for i in $(seq 1 10); do curl -s -X POST -H "Content-Type: application/json" -d '{"forward_mps":0.5,"right_mps":0,"up_mps":0,"yaw_dps":0}' $B/v1/velocity; sleep 0.2; done
curl $B/v1/telemetry
```

In the `simulator` object, `forward_m` should have grown by roughly 1 m and `right_m` should stay
near 0. Then repeat with `"right_mps":0.5` and check that `right_m` grows. If forward and right come
out swapped, swap `roll` and `pitch` in `toStickData()` in `DjiDrone.kt`.

`forward_m` and `right_m` are worked out from the simulator's `north_m`, `east_m` and `yaw_deg`,
assuming DJI's X axis is north and Y is east. If they look wrong but the raw `north_m`/`east_m`
values clearly moved in the drone's direction, that assumption is the thing to check.

Also check, still in the simulator:
1. Stop sending commands mid-way: the aircraft should hover within half a second (no further position change).
2. `POST /v1/emergency-stop` while simulated-flying: the response is `hover_then_land` and it lands.

Finish with:

```bash
curl -X POST $B/v1/land
curl -X POST $B/v1/simulator/stop      # refused until the simulated aircraft has landed
```

Unverified: whether the Mini 2 accepts the v4 simulator at all. If `start simulator failed` shows in
the phone's event log, the remaining option is a short real hover in the taped area with a safety
pilot on the RC.

## Before the first real flight

Do these with the **propellers off** and the simulator **stopped**:

1. Call `/v1/connect`, then `/v1/telemetry`, and check `link_ok`, battery and height look right.
2. Confirm the axis check above passed in the simulator.
3. Hit emergency stop on the ground with the motors spinning and confirm they stop.

## Open questions

- Does velocity virtual-stick control work on the Mini 2 with the current SDK? DJI forum posts disagree. The simulator test above answers this, if the Mini 2 accepts the simulator.
- Indoors without GPS the Mini 2 holds position on its downward vision sensors only, so expect drift over plain floors.
- The API has no authentication. Anyone on the same Wi-Fi can send commands, so use a private network or the laptop's hotspot.
- A WebSocket for velocity would cut per-command overhead once the control loop runs. The router is transport-agnostic, so it can be added next to the HTTP server.

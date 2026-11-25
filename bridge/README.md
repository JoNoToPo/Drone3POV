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
| GET | `/v1/telemetry` | `battery_pct`, `height_m`, `link_ok`, plus debug fields (`flying`, `virtual_stick`, `estopped`, ...) |

Successful calls return `{"ok": true, ...}`. Errors return `{"ok": false, "error": "..."}` with a status code: 400 bad body, 409 wrong state (not flying, landing, emergency stop latched), 503 SDK or drone not ready.

Every call returns right away, since `mini2.py` uses a 0.5 s timeout. Takeoff and land run in the background; poll `/v1/telemetry` for `flying` and `virtual_stick`.

## Safety behaviour

- **Stale commands hover.** The bridge sends stick data to the drone at 20 Hz using the latest setpoint. If no `/v1/velocity` has arrived in the last 300 ms, it sends zeros. The edge controller should post at 10 Hz or faster.
- **Limits are enforced again here.** Speed is clamped to 1 m/s and yaw to 90 °/s, the same values as `api/app/safety.py`. No climbing above 2.5 m, no velocity descent below 0.5 m, and no climbing when the height is unknown. Limits live in `core/Limits.kt`; change them together with `safety.py`.
- **Emergency stop latches.** After `/v1/emergency-stop`, velocity and takeoff are refused until `/v1/connect` is called. Each request has its own thread, so the stop never waits behind other calls. The phone screen has a big stop button too.
- **What emergency stop actually does depends on the drone's state.** On the ground with motors running it turns the motors off (`motors_off`). In the air, MSDK v4 has no way to cut the Mini 2's motors, so it brakes to a hover and lands in place (`hover_then_land`). The README in `api/` says "stops the motors at once"; that's only true on the ground.

## Code layout

- `core/` is plain Kotlin with no Android or DJI imports: limits, the velocity gate (timeout, latch, height guard) and the HTTP router. Unit tests cover it (`./gradlew test`, 16 tests).
- `DjiDrone.kt` is everything that touches the SDK: registration, state callbacks, the 20 Hz stick loop, takeoff, landing and the stop.
- `HttpBridgeServer.kt` adapts NanoHTTPD to the router. `BridgeService.kt` keeps it alive. `MainActivity.kt` is the status screen.

## Before the first flight

Do these with the **propellers off**:

1. Call `/v1/connect`, then `/v1/telemetry`, and check `link_ok`, battery and height look right.
2. Check the axis mapping. In MSDK v4 velocity mode, `roll` is forward and `pitch` is right, which looks backwards. `toStickData()` in `DjiDrone.kt` follows DJI's own sample, but confirm it in the SDK simulator before flying: a positive `forward_mps` should move the simulated aircraft forward.
3. Stop the edge script mid-command and check the drone goes back to hovering within half a second.
4. Hit emergency stop on the ground with the motors spinning and confirm they stop.

## Open questions

- Does velocity virtual-stick control work on the Mini 2 with the current SDK? DJI forum posts disagree. The simulator test above answers this.
- Indoors without GPS the Mini 2 holds position on its downward vision sensors only, so expect drift over plain floors.
- The API has no authentication. Anyone on the same Wi-Fi can send commands, so use a private network or the laptop's hotspot.
- A WebSocket for velocity would cut per-command overhead once the control loop runs. The router is transport-agnostic, so it can be added next to the HTTP server.

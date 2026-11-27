# edge

Runs on a laptop next to the flight area. The perception prototype can read from
the laptop webcam for development or an RTSP stream relayed from the Android bridge.

Implemented pieces include the video reader, vision pipeline, proportional follow
controller, and a safety watchdog. Recording and the cloud API link remain planned.

The hard limits live in `api/app/safety.py`; import them here rather than copying them.

## Webcam perception prototype

The starter pipeline in `run_vision_pipeline.py` reads webcam frames, runs the project's
Hugging Face YOLOv10n ONNX person detector, tracks detections with ByteTrack by
default, then runs MediaPipe Pose Landmarker (Tasks API) on the selected track's
crop. It is observation-only:
it displays and periodically prints measurements and does not send drone commands.
The first person with a valid, non-negative ByteTrack ID becomes the locked subject;
unassigned detections (`tracker_id == -1`) are ignored while waiting for a track.
The script ignores other
people and reports the target as lost if ByteTrack no longer matches that ID;
restart the script to clear the lock. If multiple people first appear in the
same frame, it locks onto the highest-confidence detection.
The default ByteTrack tracker uses motion and box overlap. It can preserve a
track through brief missed detections, but it cannot recognize a person after a
full exit and re-entry if the original track is lost. In that case the script
reports the locked subject as lost rather than switching to somebody else.

For experiments with appearance-based reacquisition, install the optional ReID
dependencies and select BoT-SORT. This uses more processing and can still confuse
similar-looking people:

```powershell
.edge-venv\Scripts\python.exe -m pip install -r edge\requirements-reid.txt
.edge-venv\Scripts\python.exe edge\run_vision_pipeline.py --tracker botsort --lost-track-seconds 5
```

From the repository root, create a separate edge environment with Python 3.12
(the API's root environment can stay on Python 3.13):

```powershell
py -3.12 -m venv .edge-venv
.edge-venv\Scripts\python.exe -m pip install -r api\requirements.txt
.edge-venv\Scripts\python.exe -m pip install -r edge\requirements.txt
.edge-venv\Scripts\python.exe api\scripts\download_model.py
New-Item -ItemType Directory -Force edge\models | Out-Null
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task" -OutFile "edge\models\pose_landmarker_lite.task"
.edge-venv\Scripts\python.exe edge\run_vision_pipeline.py
```

Use `--source 0` for the default webcam or `--camera 1` for another webcam.
When MediaMTX is receiving the bridge's RTMP stream, use
`--source rtsp://127.0.0.1:8554/drone`. The webcam remains the default for
testing. Press `q` in the preview window to stop. Horizontal bearing is estimated
from the subject's image-center offset. By default, the script assumes a 70-degree
horizontal camera field of view; adjust it with `--horizontal-fov-deg`. For a
calibrated value, pass `--focal-length-px`, which overrides the FOV estimate.
Bearing uses the pinhole-camera model: `atan((subject_center_x - image_center_x) /
focal_length_px)`. It describes the subject's direction relative to the camera,
not the direction the subject faces. The default bearing is approximate until
the camera is calibrated.

Distance stays unavailable unless a calibrated focal length in pixels is supplied
with `--focal-length-px`.

Distance is estimated from shoulder width: `distance_m = focal_length_px *
shoulder_width_m / shoulder_width_px`. For a rough calibration, measure shoulder
width in pixels while a person with known shoulder width stands at a measured
distance, then compute `focal_length_px = shoulder_width_px * known_distance_m /
shoulder_width_m`. The default shoulder width is an assumption and should be
adjusted per subject. For better accuracy, calibrate camera intrinsics (including
lens distortion) with a checkerboard using OpenCV. Body rotation, loose clothing,
and different shoulder widths can all distort this monocular distance estimate.

`facing_yaw_deg` is a rough camera-relative heading estimated from MediaPipe's
3D nose and shoulder landmarks: near 0 degrees means facing toward the camera;
near 180 degrees means facing away. `bearing_right_deg` is a different value: it
is the subject's left/right direction from the camera and is printed in each
logged observation. The controller combines heading, distance, and camera-relative
bearing to calculate a point behind the person.
Validate orientation signs and stability with a person turning in place before
using it for control; the webcam preview is not a flight validation.

## Follow controller

The pipeline now computes proposed body-frame velocity commands with a tunable
proportional controller on every frame.
By default these are **dry-run only**: the preview and console show the proposed
forward, right, and yaw commands, but send nothing to the bridge. To enable HTTP
commands, pass `--control` and `--bridge-url` (or set `BRIDGE_URL`). The aircraft
must already be flying with virtual sticks enabled; the edge program never
connects, takes off, or starts the simulator by itself.

Example with the bridge RTMP/RTSP feed running:

```powershell
.edge-venv\Scripts\python.exe edge\run_vision_pipeline.py `
  --source rtsp://127.0.0.1:8554/drone `
  --control `
  --bridge-url "http://192.168.1.42:8765" `
  --focal-length-px 1905 `
  --shoulder-width-m 0.42 `
  --follow-distance-m 2.0 `
  --boundary-center-lat 49.2504 `
  --boundary-center-lon -123.0016 `
  --boundary-radius-m 15 `
  --boundary-margin-m 3 `
  --max-speed-mps 0.2 `
  --max-yaw-dps 8
```

The boundary arguments are required in control mode. The example coordinates
are BCIT Burnaby's DJI simulator default and are only appropriate when testing
there; for another site, use the center of the permitted flight area. The
watchdog uses a circular GPS boundary: it requests a landing once the aircraft
enters the configured margin (radius minus margin), providing a buffer before the
configured radius. It requests landing at or beyond the radius as well. If GPS becomes
invalid, it hovers immediately and requests landing if GPS stays unavailable for
`--gps-lost-land-s` seconds (default 2). It also requests landing for low battery,
a subject inside the hard minimum distance, or prolonged loss of the locked
subject. Bridge/link loss causes hover commands; the bridge's stale-command
watchdog also zeros velocity if HTTP commands stop arriving.

This is a software failsafe, not a substitute for DJI's own flight limits or a
physical observer with access to the controller. GPS error and momentum can carry
the aircraft beyond a software boundary, so choose a generous margin and keep the
configured radius well inside the actual safe area. Validate in the DJI simulator
before any real flight.

The controller requires an RTSP source and a calibrated `--focal-length-px` so
commands cannot accidentally be driven by an unrelated laptop webcam. Use the
webcam in dry-run to tune the estimator and inspect proposed commands. A webcam
does not move with the simulated aircraft, so it cannot provide closed-loop
simulator validation; use DJI's simulator separately for small manual axis checks.
The main tunable settings are:

- `--follow-distance-m`: desired trailing distance; constrained to the shared 1.5–3.0 m safety range.
- `--forward-kp`, `--right-kp`: velocity per metre of position error.
- `--yaw-kp`: yaw rate per degree of camera bearing.
- `--max-speed-mps`, `--max-yaw-dps`: controller caps; cannot exceed bridge/API hard limits.
- `--distance-deadband-m`, `--lateral-deadband-m`, `--bearing-deadband-deg`: ignore small estimate noise.
- `--max-heading-error-deg`: hover unless the person faces sufficiently away from the camera.
- `--filter-alpha`, `--stable-observations`: smooth measurements and require consecutive valid frames before movement.
- `--camera-yaw-offset-deg`, `--forward-sign`, `--right-sign`, `--yaw-sign`: align camera and command axes after simulator checks.
- `--control-hz`, `--observation-timeout-s`: command cadence and how long a vision estimate may be reused.

The controller sends commands at 10 Hz by default and sends zero velocity when
the vision data is stale or the person is not safely facing away. Start with
dry-run output and the DJI simulator; do not use webcam-derived commands to fly
the real drone.

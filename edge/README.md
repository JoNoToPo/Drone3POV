# edge

Runs on a laptop next to the flight area. The first perception prototype reads
from the laptop webcam; later, replace that capture source with the video stream
forwarded by the Android bridge.

Planned pieces:
- **Video reader:** receives the Mini 2's video from the bridge app.
- **Vision pipeline:** YOLO person detection, ByteTrack to keep one subject ID, MediaPipe pose for distance and facing.
- **Follow controller:** PID loops that turn the subject's position into velocity commands, sent to the bridge.
- **Safety watchdog:** boundary, minimum distance, lost subject, battery and link checks. It overrides the controller.
- **Recorder:** saves each session as MP4 and uploads it when the session ends.
- **API link:** outbound WebSocket to the cloud API for settings, events and heartbeats.

The hard limits live in `api/app/safety.py`; import them here rather than copying them.

## Webcam perception prototype

The starter pipeline in `run_webcam.py` reads webcam frames, runs the project's
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
.edge-venv\Scripts\python.exe edge\run_webcam.py --tracker botsort --lost-track-seconds 5
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
.edge-venv\Scripts\python.exe edge\run_webcam.py
```

Use `--camera 1` if the default camera index is not the built-in webcam. Press
`q` in the preview window to stop. Horizontal bearing is estimated from the
subject's image-center offset. By default, the script assumes a 70-degree
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
logged observation. To choose a position behind the person, the future controller
will need the facing heading as well as distance and camera-relative bearing.
Validate orientation signs and stability with a person turning in place before
using it for control; the webcam preview is not a flight validation.

# edge

Runs on a laptop next to the flight area. Not started yet.

Planned pieces:
- **Video reader:** receives the Mini 2's video from the bridge app.
- **Vision pipeline:** YOLO person detection, ByteTrack to keep one subject ID, MediaPipe pose for distance and facing.
- **Follow controller:** PID loops that turn the subject's position into velocity commands, sent to the bridge.
- **Safety watchdog:** boundary, minimum distance, lost subject, battery and link checks. It overrides the controller.
- **Recorder:** saves each session as MP4 and uploads it when the session ends.
- **API link:** outbound WebSocket to the cloud API for settings, events and heartbeats.

The hard limits live in `api/app/safety.py`; import them here rather than copying them.

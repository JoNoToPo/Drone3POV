"""Webcam -> Hugging Face YOLOv10n -> BoT-SORT/ByteTrack -> MediaPipe Pose.

This starter is observation-only: it displays and logs vision estimates but
does not connect to or command the drone. Run from the repository root after
installing both api/requirements.txt and edge/requirements.txt.
"""
# .edge-venv\Scripts\python.exe edge\run_webcam.py --focal-length-px 509 --shoulder-width-m 0.33
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np
import supervision as sv
from trackers import BoTSORTTracker, ByteTrackTracker

# Allow `python edge/run_webcam.py` from the repository root to import `api`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app.vision import PersonDetector


DEFAULT_MODEL = ROOT / "api" / "models" / "yolov10n" / "onnx" / "model.onnx"
DEFAULT_POSE_MODEL = ROOT / "edge" / "models" / "pose_landmarker_lite.task"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Hugging Face YOLOv10n ONNX file")
    parser.add_argument("--pose-model", type=Path, default=DEFAULT_POSE_MODEL,
                        help="MediaPipe Pose Landmarker .task model")
    parser.add_argument("--min-score", type=float, default=0.4)
    parser.add_argument("--shoulder-width-m", type=float, default=0.42,
                        help="Assumed physical shoulder width; adjust for your subject")
    parser.add_argument("--focal-length-px", type=float, default=None,
                        help="Calibrated camera focal length in pixels; overrides the FOV estimate")
    parser.add_argument("--horizontal-fov-deg", type=float, default=70.0,
                        help="Approximate camera horizontal field of view, used until calibrated")
    parser.add_argument("--lost-track-seconds", type=float, default=5.0,
                        help="How long the tracker retains a lost subject at 30 FPS")
    parser.add_argument("--tracker", choices=("botsort", "bytetrack"), default="bytetrack",
                        help="ByteTrack (default, motion-only) or BoT-SORT with appearance re-identification")
    parser.add_argument("--reid-model", default="fastreid_mot17_sbs50",
                        help="Appearance model used by BoT-SORT (may download on first run)")
    parser.add_argument("--log-every", type=int, default=15, help="Print one observation every N frames")
    return parser.parse_args()


def estimate_shoulder_distance(shoulder_width_px: float, focal_length_px: float | None,
                               shoulder_width_m: float) -> float | None:
    """Pinhole-camera estimate; only meaningful after calibrating focal length."""
    if focal_length_px is None or shoulder_width_px <= 1:
        return None
    return focal_length_px * shoulder_width_m / shoulder_width_px


def estimate_bearing_deg(center_x_px: float, image_center_x_px: float,
                         focal_length_px: float) -> float:
    """Horizontal camera-to-subject bearing; right of image center is positive."""
    if focal_length_px <= 0:
        raise ValueError("focal_length_px must be positive")
    return math.degrees(math.atan2(center_x_px - image_center_x_px, focal_length_px))


def estimate_facing_yaw_deg(world_landmarks: list) -> float | None:
    """Estimate facing heading from the nose relative to the shoulder midpoint.

    The result is camera-relative: approximately 0 degrees means facing toward
    the camera, 180 means facing away. MediaPipe's inferred 3D pose is only a
    rough orientation cue; validate its sign and stability for the camera setup.
    """
    if len(world_landmarks) <= 12:
        return None
    nose, left_shoulder, right_shoulder = world_landmarks[0], world_landmarks[11], world_landmarks[12]
    shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
    shoulder_mid_z = (left_shoulder.z + right_shoulder.z) / 2
    forward_x = nose.x - shoulder_mid_x
    # MediaPipe's pose depth convention has negative z toward the camera.
    forward_toward_camera = shoulder_mid_z - nose.z
    if math.hypot(forward_x, forward_toward_camera) < 1e-4:
        return None
    return math.degrees(math.atan2(forward_x, forward_toward_camera))


def main() -> None:
    args = parse_args()
    if not 0 < args.horizontal_fov_deg < 180:
        raise SystemExit("--horizontal-fov-deg must be between 0 and 180")
    if args.focal_length_px is not None and args.focal_length_px <= 0:
        raise SystemExit("--focal-length-px must be positive")
    if args.lost_track_seconds <= 0:
        raise SystemExit("--lost-track-seconds must be positive")
    if not args.model.is_file():
        raise SystemExit(
            f"Model not found: {args.model}\n"
            "From api/, run: ..\\.venv\\Scripts\\python.exe scripts\\download_model.py"
        )
    if not args.pose_model.is_file():
        raise SystemExit(
            f"Pose model not found: {args.pose_model}\n"
            "Download pose_landmarker_lite.task as described in edge/README.md"
        )

    detector = PersonDetector(args.model, min_score=args.min_score)
    tracker_options = {
        "frame_rate": 30.0,
        "lost_track_buffer": round(args.lost_track_seconds * 30),
    }
    if args.tracker == "botsort":
        tracker = BoTSORTTracker(reid_model=args.reid_model, **tracker_options)
    else:
        tracker = ByteTrackTracker(**tracker_options)
    base_options = mp_python.BaseOptions(model_asset_path=str(args.pose_model))
    pose_options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    pose = mp_vision.PoseLandmarker.create_from_options(pose_options)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        pose.close()
        raise SystemExit(f"Could not open camera index {args.camera}; try --camera 1")

    locked_subject_id: int | None = None
    frame_number = 0
    started = time.monotonic()
    print("Observation-only webcam pipeline running. Press q in the video window to quit.")
    try:
        while True:
            ok, frame = camera.read()
            captured_at = time.monotonic()
            if not ok:
                print("Camera frame unavailable; stopping.")
                break
            frame_number += 1
            height, width = frame.shape[:2]

            encoded_ok, encoded = cv2.imencode(".jpg", frame)
            if not encoded_ok:
                continue
            result = detector.detect(encoded.tobytes())
            people = result["people"]
            boxes = np.asarray([p["box"] for p in people], dtype=np.float32).reshape(-1, 4)
            scores = np.asarray([p["confidence"] for p in people], dtype=np.float32)
            detections = sv.Detections(
                xyxy=boxes,
                confidence=scores,
                class_id=np.zeros(len(people), dtype=int),
            )
            # BoT-SORT needs the frame pixels to compute appearance embeddings;
            # ByteTrack accepts the same argument but does not use it.
            tracked = tracker.update(detections, frame=frame)

            # Lock onto the first available track once. ReID can help BoT-SORT
            # reconnect the same person after their box/position changes. Never
            # switch to another person if the original ID is lost.
            ids = tracked.tracker_id
            if ids is None or len(ids) == 0:
                selected_index = None
            else:
                # ByteTrack uses -1 for detections that have not been assigned
                # an active track yet. Never lock onto that sentinel value.
                valid_indices = np.flatnonzero(ids >= 0)
                if locked_subject_id is None and len(valid_indices):
                    best_position = int(np.argmax(tracked.confidence[valid_indices]))
                    selected_index = int(valid_indices[best_position])
                    locked_subject_id = int(ids[selected_index])
                else:
                    matches = np.flatnonzero(ids == locked_subject_id)
                    selected_index = int(matches[0]) if len(matches) else None

            annotated = frame.copy()
            observation: dict[str, object] = {
                "frame": frame_number,
                "track_id": locked_subject_id,
                "target_visible": False,
                "center_offset_x": None,
                "bearing_right_deg": None,
                "distance_m": None,
                "facing_yaw_deg": None,
                "age_s": round(captured_at - started, 2),
            }

            if selected_index is not None:
                x1, y1, x2, y2 = tracked.xyxy[selected_index].astype(int)
                x1, x2 = max(0, x1), min(width, x2)
                y1, y2 = max(0, y1), min(height, y2)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
                cv2.putText(annotated, f"subject ID {locked_subject_id}", (x1, max(24, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 0), 2)

                # Pose is evaluated only on the selected person's crop.
                crop = frame[y1:y2, x1:x2]
                if crop.size:
                    rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
                    timestamp_ms = int((captured_at - started) * 1000)
                    pose_result = pose.detect_for_video(mp_image, timestamp_ms)
                    if pose_result.pose_landmarks:
                        landmarks = pose_result.pose_landmarks[0]
                        world_landmarks = pose_result.pose_world_landmarks[0]
                        # MediaPipe's 33-point pose landmark ordering.
                        nose, left, right = landmarks[0], landmarks[11], landmarks[12]
                        shoulder_px = float(np.hypot((left.x - right.x) * (x2 - x1),
                                                     (left.y - right.y) * (y2 - y1)))
                        distance = estimate_shoulder_distance(
                            shoulder_px, args.focal_length_px, args.shoulder_width_m
                        )
                        facing_yaw = estimate_facing_yaw_deg(world_landmarks)
                        for landmark in (left, right, nose):
                            px = x1 + int(landmark.x * (x2 - x1))
                            py = y1 + int(landmark.y * (y2 - y1))
                            cv2.circle(annotated, (px, py), 5, (0, 80, 255), -1)
                        observation.update({
                            "distance_m": round(distance, 2) if distance is not None else None,
                            "facing_yaw_deg": round(facing_yaw, 1) if facing_yaw is not None else None,
                            "shoulder_width_px": round(shoulder_px, 1),
                        })

                center_x = float((x1 + x2) / 2)
                focal_px_for_bearing = args.focal_length_px
                if focal_px_for_bearing is None:
                    focal_px_for_bearing = width / (2 * math.tan(math.radians(args.horizontal_fov_deg) / 2))
                bearing = estimate_bearing_deg(center_x, width / 2, focal_px_for_bearing)
                observation.update({
                    "track_id": locked_subject_id,
                    "target_visible": True,
                    "center_offset_x": round((center_x - width / 2) / (width / 2), 3),
                    "bearing_right_deg": round(bearing, 2) if bearing is not None else None,
                })
                facing_yaw = observation["facing_yaw_deg"]
                facing_text = f"facing {facing_yaw:+.1f} deg" if facing_yaw is not None else "facing unavailable"
                bearing_text = f"bearing {bearing:+.1f} deg"
                distance_text = (
                    f"distance {observation['distance_m']:.2f} m"
                    if observation["distance_m"] is not None else "distance uncalibrated"
                )
                cv2.putText(annotated, f"{facing_text} | {bearing_text} | {distance_text}", (12, height - 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            elif locked_subject_id is not None:
                cv2.putText(annotated, f"locked subject {locked_subject_id} lost",
                            (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                cv2.putText(annotated, "waiting for a valid subject track",
                            (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)

            if frame_number % max(args.log_every, 1) == 0:
                print({**observation, "capture_monotonic_s": round(captured_at, 3)})
            cv2.imshow("Drone3POV edge perception (observation only)", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        pose.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

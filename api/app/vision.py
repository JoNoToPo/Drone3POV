"""Person detection with a self-hosted Hugging Face model.

Model: onnx-community/yolov10n (https://huggingface.co/onnx-community/yolov10n), COCO classes, ONNX.
The file is downloaded into api/models/ by scripts/download_model.py and run locally with
ONNX Runtime; no third-party AI API is involved. If the file is missing, detection fails with
ModelUnavailable, which is how the self-hosting can be demonstrated.
"""

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MODEL_ID = "onnx-community/yolov10n"
INPUT_SIZE = 640
PERSON_CLASS = 0
PAD_COLOUR = (114, 114, 114)
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


class ModelUnavailable(Exception):
    pass


class ImageUnreadable(Exception):
    pass


class PersonDetector:
    def __init__(self, model_path: Path, min_score: float = 0.4) -> None:
        self.model_path = Path(model_path)
        self.min_score = min_score
        self._session = None
        self._loaded_mtime: float | None = None

    def _session_now(self):
        # Checked on every request, so removing the file makes detection fail at once.
        if not self.model_path.is_file():
            self._session = None
            raise ModelUnavailable(str(self.model_path))
        mtime = self.model_path.stat().st_mtime
        if self._session is None or mtime != self._loaded_mtime:
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
            self._loaded_mtime = mtime
        return self._session

    @staticmethod
    def _prepare(data: bytes) -> tuple[np.ndarray, float, int, int]:
        try:
            image = Image.open(io.BytesIO(data))
            image = ImageOps.exif_transpose(image).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ImageUnreadable from exc

        width, height = image.size
        scale = INPUT_SIZE / max(width, height)
        resized = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.BILINEAR)
        canvas = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), PAD_COLOUR)
        canvas.paste(resized, (0, 0))
        tensor = (np.asarray(canvas, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
        return tensor, scale, width, height

    def detect(self, data: bytes) -> dict:
        session = self._session_now()
        tensor, scale, width, height = self._prepare(data)

        started = time.perf_counter()
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]  # (300, 6)
        inference_ms = (time.perf_counter() - started) * 1000

        people = []
        for x1, y1, x2, y2, score, cls in output:
            if int(cls) != PERSON_CLASS or score < self.min_score:
                continue
            box = [
                float(np.clip(x1 / scale, 0, width)),
                float(np.clip(y1 / scale, 0, height)),
                float(np.clip(x2 / scale, 0, width)),
                float(np.clip(y2 / scale, 0, height)),
            ]
            people.append({
                "box": [round(v, 1) for v in box],
                "confidence": round(float(score), 3),
                # Horizontal offset of the person from the image centre, -1 (left) to 1 (right).
                # The follow controller turns this into a yaw command.
                "center_offset_x": round(((box[0] + box[2]) / 2 - width / 2) / (width / 2), 3),
                "height_fraction": round((box[3] - box[1]) / height, 3),
            })
        people.sort(key=lambda p: p["confidence"], reverse=True)

        return {
            "model": MODEL_ID,
            "image_width": width,
            "image_height": height,
            "people_count": len(people),
            "people": people,
            "inference_ms": round(inference_ms, 1),
        }

"""Download the self-hosted person-detection model from Hugging Face into api/models/.

Run from the api/ folder:  python scripts/download_model.py
"""

from pathlib import Path

from huggingface_hub import hf_hub_download

MODEL_ID = "onnx-community/yolov10n"
FILES = ("onnx/model.onnx", "config.json", "preprocessor_config.json")
TARGET = Path(__file__).resolve().parent.parent / "models" / "yolov10n"

if __name__ == "__main__":
    for name in FILES:
        path = hf_hub_download(MODEL_ID, name, local_dir=TARGET)
        print(f"{path}  ({Path(path).stat().st_size:,} bytes)")

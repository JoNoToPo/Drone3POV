from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from .. import messages
from ..config import Settings
from ..db import User
from ..security import get_current_user, get_settings
from ..vision import ImageUnreadable, ModelUnavailable
from ..schemas import error

router = APIRouter(prefix="/api/v1/vision", tags=["vision (AI)"])


class PersonOut(BaseModel):
    box: list[float]
    confidence: float
    center_offset_x: float
    height_fraction: float


class DetectOut(BaseModel):
    model: str
    image_width: int
    image_height: int
    people_count: int
    people: list[PersonOut]
    inference_ms: float


@router.post(
    "/detect",
    response_model=DetectOut,
    responses={
        401: error("Not logged in"),
        413: error("Image too large"),
        415: error("Not an image"),
        422: error("Image could not be decoded"),
        503: error("Model file not available on the server"),
    },
)
async def detect_people(
    request: Request,
    image: UploadFile = File(..., description="A JPEG or PNG photo"),
    _user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DetectOut:
    """Find the people in a photo with the self-hosted YOLOv10n model.

    Each person comes with a bounding box, a confidence score, and how far they are from the
    image centre: the same numbers the drone's follow controller steers by.
    """
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, messages.IMAGE_REQUIRED)
    data = await image.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            messages.IMAGE_TOO_LARGE.format(limit_mb=settings.max_upload_bytes // (1024 * 1024)),
        )
    try:
        return DetectOut(**request.app.state.detector.detect(data))
    except ImageUnreadable:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, messages.IMAGE_UNREADABLE) from None
    except ModelUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, messages.MODEL_UNAVAILABLE) from None

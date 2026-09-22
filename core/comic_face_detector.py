import os
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Union, Any
from core.crop_validator import ProtectedRegion

@dataclass
class FaceDetectorResult:
    completed: bool
    regions: List[ProtectedRegion]
    confidence: float
    error: Optional[str] = None


_ANIME_FACE_CASCADE: Optional[Any] = None


def _get_cascade_path() -> Optional[str]:
    # Check relative assets/models directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_path = os.path.join(project_root, "assets", "models", "lbpcascade_animeface.xml")
    if os.path.exists(local_path):
        return local_path
    return None


def get_face_cascade() -> Optional[Any]:
    global _ANIME_FACE_CASCADE
    if _ANIME_FACE_CASCADE is not None:
        return _ANIME_FACE_CASCADE

    cascade_cls = getattr(cv2, "CascadeClassifier", None)
    if cascade_cls is None:
        return None

    cascade_path = _get_cascade_path()
    if cascade_path and os.path.exists(cascade_path):
        try:
            _ANIME_FACE_CASCADE = cascade_cls(cascade_path)
            if hasattr(_ANIME_FACE_CASCADE, "empty") and not _ANIME_FACE_CASCADE.empty():
                return _ANIME_FACE_CASCADE
        except Exception:
            _ANIME_FACE_CASCADE = None

    # Fallback to OpenCV standard Haar cascade if available
    try:
        if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            haar_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if os.path.exists(haar_path):
                _ANIME_FACE_CASCADE = cascade_cls(haar_path)
                return _ANIME_FACE_CASCADE
    except Exception:
        pass

    return None


def detect_faces(
    image_input: Union[str, np.ndarray],
    min_size: int = 40,
    scale_factor: float = 1.1,
    min_neighbors: int = 5,
) -> FaceDetectorResult:
    """
    Detects faces in a comic panel image using anime face cascade / Haar cascade.
    Returns FaceDetectorResult with list of ProtectedRegion(region_type="face").
    """
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            return FaceDetectorResult(
                completed=False,
                regions=[],
                confidence=0.0,
                error=f"Image file not found: {image_input}",
            )
        img = cv2.imread(image_input)
        if img is None:
            return FaceDetectorResult(
                completed=False,
                regions=[],
                confidence=0.0,
                error=f"Could not decode image: {image_input}",
            )
    else:
        img = image_input

    cascade = get_face_cascade()
    if cascade is None or (hasattr(cascade, "empty") and cascade.empty()):
        # Cascade not available in this OpenCV build; return completed=False with informative note
        return FaceDetectorResult(
            completed=False,
            regions=[],
            confidence=0.0,
            error="CascadeClassifier unavailable in current OpenCV build",
        )

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        gray = cv2.equalizeHist(gray)

        flags = getattr(cv2, "CASCADE_SCALE_IMAGE", 0)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=(min_size, min_size),
            flags=flags,
        )

        regions: List[ProtectedRegion] = []
        for (x, y, w, h) in faces:
            regions.append(
                ProtectedRegion(
                    x1=int(x),
                    y1=int(y),
                    x2=int(x + w),
                    y2=int(y + h),
                    region_type="face",
                    confidence=0.92,
                    label="anime_face",
                )
            )

        return FaceDetectorResult(
            completed=True,
            regions=regions,
            confidence=0.95,
            error=None,
        )
    except Exception as e:
        return FaceDetectorResult(
            completed=False,
            regions=[],
            confidence=0.0,
            error=str(e),
        )

import os
import threading
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image
from core.crop_validator import ProtectedRegion

_EASYOCR_READER = None
_EASYOCR_LOCK = threading.Lock()
_SECONDARY_OCR = threading.local()


def crosscheck_ocr(image_path: str, first_text: str) -> tuple[str, bool]:
    """Compare EasyOCR with independent RapidOCR; leave the choice to review."""
    from rapidocr_onnxruntime import RapidOCR

    if not hasattr(_SECONDARY_OCR, "reader"):
        _SECONDARY_OCR.reader = RapidOCR()
    result, _ = _SECONDARY_OCR.reader(image_path)
    second_text = " ".join(item[1] for item in result or [])
    normalize = lambda value: " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
    first, second = normalize(first_text), normalize(second_text)
    return second_text, bool(first or second) and SequenceMatcher(None, first, second).ratio() < 0.82

@dataclass
class OCRResult:
    completed: bool
    text: str
    regions: List[ProtectedRegion]
    confidence: float
    error: Optional[str] = None


def extract_ocr_with_regions(image_path: str) -> OCRResult:
    """
    Performs OCR and returns both full text and ProtectedRegion bounding boxes for all dialogue bubbles.
    """
    if not os.path.exists(image_path):
        return OCRResult(completed=False, text="", regions=[], confidence=0.0, error="File not found")

    # Try EasyOCR first for accurate bounding box detection
    global _EASYOCR_READER
    try:
        import easyocr
        if _EASYOCR_READER is None:
            with _EASYOCR_LOCK:
                if _EASYOCR_READER is None:
                    _EASYOCR_READER = easyocr.Reader(['en'], gpu=False)
        results = _EASYOCR_READER.readtext(image_path)
        # results format: [([[x1,y1], [x2,y1], [x2,y2], [x1,y2]], text, prob), ...]
        text_lines = []
        regions: List[ProtectedRegion] = []
        confidences = []

        for bbox, text, prob in results:
            clean_t = text.strip()
            if len(clean_t) > 1 and prob > 0.2:
                text_lines.append(clean_t)
                confidences.append(prob)
                # Compute bounding box
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                x1, x2 = int(min(xs)), int(max(xs))
                y1, y2 = int(min(ys)), int(max(ys))
                regions.append(
                    ProtectedRegion(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        region_type="text",
                        confidence=float(prob),
                        label=clean_t[:30],
                    )
                )

        full_text = " ".join(text_lines)
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.85
        return OCRResult(
            completed=True,
            text=full_text,
            regions=regions,
            confidence=avg_conf,
            error=None,
        )
    except Exception as e:
        easy_error = str(e)

    # Fallback to PyTesseract with bounding box data
    try:
        import pytesseract
        img = Image.open(image_path)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, timeout=8)
        text_lines = []
        regions = []
        confidences = []

        n_boxes = len(data['text'])
        for i in range(n_boxes):
            word = data['text'][i].strip()
            conf = float(data['conf'][i])
            if word and conf > 30:
                text_lines.append(word)
                confidences.append(conf / 100.0)
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                regions.append(
                    ProtectedRegion(
                        x1=x,
                        y1=y,
                        x2=x + w,
                        y2=y + h,
                        region_type="text",
                        confidence=conf / 100.0,
                        label=word,
                    )
                )

        full_text = " ".join(text_lines)
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.80
        return OCRResult(
            completed=True,
            text=full_text,
            regions=regions,
            confidence=avg_conf,
            error=None,
        )
    except Exception as e:
        # If neither OCR engine succeeds
        return OCRResult(
            completed=False,
            text="",
            regions=[],
            confidence=0.0,
            error=f"EasyOCR: {easy_error}; Tesseract: {e}",
        )


def extract_ocr_text_from_panel(image_path: str) -> str:
    """
    Backward-compatibility wrapper returning extracted string.
    """
    res = extract_ocr_with_regions(image_path)
    if not res.completed:
        raise RuntimeError(f"OCR failed for {image_path}: {res.error}")
    return res.text

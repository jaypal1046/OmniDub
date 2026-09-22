import os
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image
from core.crop_validator import ProtectedRegion

_EASYOCR_READER = None

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
    except Exception:
        pass

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
            error=str(e),
        )


def extract_ocr_text_from_panel(image_path: str) -> str:
    """
    Backward-compatibility wrapper returning extracted string.
    """
    res = extract_ocr_with_regions(image_path)
    return res.text

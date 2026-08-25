import os
from PIL import Image

_EASYOCR_READER = None

def extract_ocr_text_from_panel(image_path):
    """
    Performs OCR on a comic/manhwa panel image to extract speech bubble dialogue,
    sound effects, and text cues.
    """
    if not os.path.exists(image_path):
        return ""

    # Try PyTesseract first
    try:
        import pytesseract
        img = Image.open(image_path)
        raw_text = pytesseract.image_to_string(img, timeout=5)
        lines = [line.strip() for line in raw_text.splitlines() if len(line.strip()) > 1]
        if lines:
            ocr_text = " ".join(lines)
            print(f"🔤 Tesseract OCR Extracted [{os.path.basename(image_path)}]: \"{ocr_text[:80]}...\"", flush=True)
            return ocr_text
    except Exception:
        pass

    # Try EasyOCR with cached reader
    try:
        global _EASYOCR_READER
        import easyocr
        if _EASYOCR_READER is None:
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False)
        results = _EASYOCR_READER.readtext(image_path, detail=0)
        clean_results = [r.strip() for r in results if len(r.strip()) > 1]
        if clean_results:
            ocr_text = " ".join(clean_results)
            print(f"🔤 EasyOCR Extracted [{os.path.basename(image_path)}]: \"{ocr_text[:80]}...\"", flush=True)
            return ocr_text
    except Exception:
        pass

    return ""

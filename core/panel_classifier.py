import os
import re
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

AD_KEYWORDS = [
    "discord", "support", "patreon", "scanlation", "unsupported reader",
    "watermark", "translated by", "translation", "donat", "kofi",
    "paypal", "read first on", "uploaded on", "t.me/", "join our",
    "credits", "recruitment", "raw provider", "cleaner", "typesetter"
]

@dataclass
class PanelClassification:
    action: str  # "INCLUDE", "STORY_ONLY", "EXCLUDE"
    reason: str
    confidence: float
    is_blank: bool
    is_ad: bool
    is_text_heavy: bool


def classify_panel_content(
    image_path_or_np: Any,
    ocr_text: str = "",
    height_px: int = 0,
    width_px: int = 0
) -> PanelClassification:
    """
    Automated Computer Vision & OCR Classifier for Manhwa panels:
    1. EXCLUDE: Blank gutters, pure backgrounds, scanlation watermark/ad banners, tiny slivers.
    2. STORY_ONLY: Status windows, lore info boxes, text-heavy monologue cards.
    3. INCLUDE: Action scenes, characters, and standard visual comic panels.
    """
    if isinstance(image_path_or_np, str):
        if not os.path.exists(image_path_or_np):
            return PanelClassification(action="EXCLUDE", reason="Missing file", confidence=1.0, is_blank=True, is_ad=False, is_text_heavy=False)
        img_np = cv2.imread(image_path_or_np)
        if img_np is None:
            return PanelClassification(action="EXCLUDE", reason="Unreadable image", confidence=1.0, is_blank=True, is_ad=False, is_text_heavy=False)
    else:
        img_np = image_path_or_np

    h, w = img_np.shape[:2]
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if len(img_np.shape) == 3 else img_np

    # 1. Check if image is extremely small sliver (< 220px)
    if h < 220:
        return PanelClassification(
            action="EXCLUDE",
            reason="Tiny slice height (< 220px)",
            confidence=0.95,
            is_blank=False,
            is_ad=False,
            is_text_heavy=False
        )

    # 2. Check for Blank / Solid Gutters (white/black/gradient)
    white_ratio = float(np.mean(gray >= 242))
    black_ratio = float(np.mean(gray <= 18))
    blank_ratio = white_ratio + black_ratio
    row_std = float(np.mean(np.std(gray, axis=1)))

    is_blank = (blank_ratio >= 0.90) or (row_std < 7.0 and blank_ratio >= 0.70)
    if is_blank:
        return PanelClassification(
            action="EXCLUDE",
            reason=f"Blank / Empty gutter ({blank_ratio*100:.0f}% uniform)",
            confidence=0.98,
            is_blank=True,
            is_ad=False,
            is_text_heavy=False
        )

    # 3. Check for Scanlation Ad / Watermark text in OCR
    clean_ocr = ocr_text.lower()
    is_ad = any(kw in clean_ocr for kw in AD_KEYWORDS)
    if is_ad:
        matched_kw = [kw for kw in AD_KEYWORDS if kw in clean_ocr]
        return PanelClassification(
            action="EXCLUDE",
            reason=f"Detected scanlation banner / credits ('{matched_kw[0]}')",
            confidence=0.92,
            is_blank=False,
            is_ad=True,
            is_text_heavy=True
        )

    # 4. Check for Text-Heavy / Status Window / Pure Monologue Card
    # If text has high word count and image has relatively low color variance / high text area
    word_count = len(clean_ocr.split())
    is_text_heavy = False

    if word_count >= 25:
        # Check color saturation
        if len(img_np.shape) == 3:
            hsv = cv2.cvtColor(img_np, cv2.COLOR_BGR2HSV)
            mean_sat = float(np.mean(hsv[:, :, 1]))
            if mean_sat < 35:  # Low color, monochrome status window or text card
                is_text_heavy = True
        else:
            is_text_heavy = True

    if is_text_heavy:
        return PanelClassification(
            action="STORY_ONLY",
            reason=f"Text-heavy lore/status card ({word_count} words)",
            confidence=0.85,
            is_blank=False,
            is_ad=False,
            is_text_heavy=True
        )

    # 5. Default Standard Comic Panel
    return PanelClassification(
        action="INCLUDE",
        reason="Visual story artwork panel",
        confidence=0.95,
        is_blank=False,
        is_ad=False,
        is_text_heavy=False
    )

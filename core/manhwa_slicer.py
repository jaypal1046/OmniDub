import os
import sys
import json
import cv2
import numpy as np
from PIL import Image
from typing import List, Tuple, Dict, Any, Optional

from core.crop_validator import (
    ProtectedRegion,
    DetectionCoverage,
    validate_crop_candidate,
    expand_box_safely,
    box_area,
    Box,
)
from core.comic_face_detector import detect_faces
from core.comic_ocr import extract_ocr_with_regions


def open_image_safely(image_path: str) -> Optional[np.ndarray]:
    """Opens image using PIL, falling back to FFmpeg decode for AVIF/unsupported formats."""
    if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        return None
    try:
        with Image.open(image_path) as pil_img:
            return np.array(pil_img.convert("RGB"))
    except Exception:
        # Fallback to FFmpeg decoding to RGB pipe
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-v", "error", "-i", image_path,
                "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"
            ]
            pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            raw_data, _ = pipe.communicate()
            if raw_data:
                probe_cmd = [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", image_path
                ]
                dims = subprocess.check_output(probe_cmd, text=True).strip().split("x")
                w, h = int(dims[0]), int(dims[1])
                img_np = np.frombuffer(raw_data, dtype=np.uint8).reshape((h, w, 3))
                return img_np
        except Exception as e:
            print(f"⚠️ Could not decode image '{image_path}': {e}")
    return None


def detect_true_gutters(gray_img: np.ndarray, min_gap_height: int = 35) -> List[Tuple[int, int]]:
    """
    Detects true comic gutters: wide horizontal gaps that are predominantly blank (white/black/solid background).
    Avoids splitting on subtle gradients or thin lines within a single panel.
    """
    h, w = gray_img.shape
    white_ratio = np.mean(gray_img >= 242, axis=1)
    black_ratio = np.mean(gray_img <= 18, axis=1)
    blank_ratio = white_ratio + black_ratio

    # Also calculate row variance
    row_std = np.std(gray_img, axis=1)
    is_solid_row = (blank_ratio >= 0.88) | (row_std < 8.0)

    gutters = []
    in_gap = False
    g_start = 0

    for y, is_blank in enumerate(is_solid_row):
        if is_blank:
            if not in_gap:
                in_gap = True
                g_start = y
        else:
            if in_gap:
                in_gap = False
                if (y - g_start) >= min_gap_height:
                    gutters.append((g_start, y))

    if in_gap and (h - g_start) >= min_gap_height:
        gutters.append((g_start, h))

    return gutters


def draw_debug_preview(
    image_np: np.ndarray,
    candidate_boxes: List[Box],
    protected_regions: List[ProtectedRegion],
    validations: List[Dict[str, Any]],
    output_path: str,
):
    """
    Draws an annotated debug image showing candidate crops, protected faces/text, and decisions.
    """
    debug_img = cv2.cvtColor(image_np.copy(), cv2.COLOR_RGB2BGR)

    for reg in protected_regions:
        color = (255, 255, 0) if reg.region_type == "text" else (255, 200, 0)
        cv2.rectangle(debug_img, (reg.x1, reg.y1), (reg.x2, reg.y2), color, 2)
        cv2.putText(
            debug_img,
            f"{reg.region_type}",
            (reg.x1, max(15, reg.y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    for idx, (box, val) in enumerate(zip(candidate_boxes, validations)):
        x1, y1, x2, y2 = box
        decision = val.get("decision", "contain_safe")
        is_approved = (decision == "approved_crop")
        box_color = (0, 255, 0) if is_approved else (0, 140, 255)

        cv2.rectangle(debug_img, (x1, y1), (x2, y2), box_color, 3)
        tag = f"#{idx+1} {decision} ({val.get('score', 0):.2f})"
        cv2.putText(
            debug_img,
            tag,
            (x1 + 10, y1 + 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            box_color,
            2,
            cv2.LINE_AA,
        )

    cv2.imwrite(output_path, debug_img)


def slice_strip(
    image_path: str,
    output_dir: Optional[str] = None,
    max_aspect_ratio: float = 1.6,
    save_debug_previews: bool = True,
) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    Smart Safe Webtoon Slicer & Scene Framing Classifier:
    - Splits only at genuine white/black comic gutters (min height >= 35px, min panel height >= 450px).
    - Preserves continuous tall action scenes as single units with Mode C (Vertical Pan).
    - Uses Anime Face & OCR dialogue guard rails to never cut through characters or text.
    """
    img_np = open_image_safely(image_path)
    if img_np is None:
        print(f"⚠️ Image file missing or empty: '{image_path}'. Skipping.")
        return [], []

    height, width, _ = img_np.shape
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    base_name = os.path.splitext(os.path.basename(image_path))[0]

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Detect Protected Regions
    face_res = detect_faces(img_np)
    ocr_res = extract_ocr_with_regions(image_path)

    protected_regions: List[ProtectedRegion] = []
    if face_res.completed:
        protected_regions.extend(face_res.regions)
    if ocr_res.completed:
        protected_regions.extend(ocr_res.regions)

    coverage = DetectionCoverage(
        ocr_attempted=True,
        ocr_completed=ocr_res.completed,
        face_detection_attempted=True,
        face_detection_completed=face_res.completed,
        ocr_confidence=ocr_res.confidence if ocr_res.completed else 0.0,
        face_confidence=face_res.confidence if face_res.completed else 0.0,
    )

    # Standard aspect ratio page -> Return as single panel
    if height <= width * max_aspect_ratio:
        fname = f"{base_name}_p01.png"
        meta = {
            "index": 1,
            "filename": fname,
            "y_start": 0,
            "y_end": height,
            "framing_mode": "contain",
            "cut_source": "full_page",
            "confidence": 1.0,
            "protected_regions_count": len(protected_regions),
        }
        if output_dir:
            out_p = os.path.join(output_dir, fname)
            cv2.imwrite(out_p, cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR))
            with open(os.path.join(output_dir, f"{base_name}_metadata.json"), "w", encoding="utf-8") as f:
                json.dump([meta], f, indent=2)
        return [img_np], [meta]

    effective_height = gray.shape[0]
    cropped_img_np = img_np
    gray_cropped = gray

    # 2. Detect True Gutters
    gutters = detect_true_gutters(gray_cropped, min_gap_height=35)

    # 3. Form Candidate Cut Points with Minimum Panel Height (>= 450px)
    MIN_PANEL_HEIGHT = 450
    cut_points = [0]
    for g_start, g_end in gutters:
        mid_y = (g_start + g_end) // 2
        if mid_y - cut_points[-1] >= MIN_PANEL_HEIGHT:
            cut_points.append(mid_y)

    if cut_points[-1] < effective_height - 250:
        cut_points.append(effective_height)
    elif cut_points[-1] != effective_height:
        cut_points[-1] = effective_height

    final_cut_points = sorted(list(set(cut_points)))

    # 4. Build Candidate Boxes & Validate Against Face / Text Guard Rails
    candidate_boxes: List[Box] = []
    for i in range(len(final_cut_points) - 1):
        y_s, y_e = final_cut_points[i], final_cut_points[i + 1]
        candidate_boxes.append((0, y_s, width, y_e))

    panel_images = []
    metadata_list = []
    validation_summaries = []

    for i, raw_box in enumerate(candidate_boxes):
        neighboring = [b for j, b in enumerate(candidate_boxes) if j != i]
        safe_box = expand_box_safely(raw_box, width, effective_height, neighboring, margin_ratio=0.03)

        val_res = validate_crop_candidate(
            crop=safe_box,
            image_width=width,
            image_height=effective_height,
            protected_regions=protected_regions,
            coverage=coverage,
            boundary_score=0.95,
            neighboring_boxes=None,
            mode="validated_crop",
        )

        validation_summaries.append({
            "decision": val_res.decision,
            "score": val_res.score,
            "hard_failures": val_res.hard_failures,
            "soft_warnings": val_res.soft_warnings,
        })

        x1, y1, x2, y2 = safe_box
        seg_h = y2 - y1

        # Classify Video Framing Mode:
        # - Mode C (vertical_pan): continuous tall scene (seg_h >= 1.6x width)
        # - Mode B (crop): validated safe crop with high confidence
        # - Mode A (contain): safe fallback with blurred canvas
        if seg_h >= int(width * 1.6):
            framing_mode = "vertical_pan"
        elif val_res.approved:
            framing_mode = "crop"
        else:
            framing_mode = "contain"

        panel_crop = cropped_img_np[y1:y2, x1:x2, :]
        panel_images.append(panel_crop)

        fname = f"{base_name}_p{len(panel_images):02d}.png"
        meta = {
            "index": len(panel_images),
            "filename": fname,
            "x_start": x1,
            "x_end": x2,
            "y_start": y1,
            "y_end": y2,
            "height": seg_h,
            "framing_mode": framing_mode,
            "decision": val_res.decision,
            "validation_score": val_res.score,
            "hard_failures": val_res.hard_failures,
            "confidence": val_res.score,
        }
        metadata_list.append(meta)

        if output_dir:
            out_p = os.path.join(output_dir, fname)
            cv2.imwrite(out_p, cv2.cvtColor(panel_crop, cv2.COLOR_RGB2BGR))

    # Save debug preview image in a separate debug folder so it doesn't get confused with panels
    if output_dir and save_debug_previews:
        debug_dir = os.path.join(os.path.dirname(output_dir), "debug_previews")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, f"{base_name}_debug_cuts.jpg")
        try:
            draw_debug_preview(cropped_img_np, candidate_boxes, protected_regions, validation_summaries, debug_path)
        except Exception:
            pass

        with open(os.path.join(output_dir, f"{base_name}_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2)

    return panel_images, metadata_list


def slice_manhwa_strip(image_path: str, output_dir: str) -> List[str]:
    """
    Backward-compatibility wrapper function returning list of sliced panel filepaths.
    """
    if not image_path or not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        return []
    _, meta = slice_strip(image_path, output_dir)
    return [os.path.join(output_dir, m.get("filename", f"panel_{m['index']:03d}.png")) for m in meta]


def process_manhwa_images(image_paths: List[str], output_panels_dir: str) -> List[str]:
    """
    Processes chapter image paths, producing clean scene panels with true gutter detection.
    """
    processed_paths = []
    os.makedirs(output_panels_dir, exist_ok=True)

    valid_paths = [p for p in image_paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
    for path in valid_paths:
        result_paths = slice_manhwa_strip(path, output_panels_dir)
        processed_paths.extend(result_paths)

    return processed_paths

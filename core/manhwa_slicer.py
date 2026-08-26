import os
import sys
import json
import cv2
import numpy as np
from PIL import Image
from typing import List, Tuple, Dict, Any, Optional

def compute_row_edge_density(gray_img: np.ndarray) -> np.ndarray:
    """
    Per-row edge density via Sobel gradients. Background-color-agnostic:
    a solid white row, solid black row, and a smooth gradient row all
    read as ~0 edge density. A row with a motion streak, bubble tail,
    or SFX line reads as high edge density even if its mean brightness
    happens to be very light or very dark (the case row_std/row_mean
    gets wrong on gradient transition panels).
    """
    sobelx = cv2.Sobel(gray_img, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray_img, cv2.CV_64F, 0, 1, ksize=3)
    edge_density = np.sum(np.abs(sobelx) + np.abs(sobely), axis=1) / float(gray_img.shape[1])
    return edge_density


def otsu_threshold(values: np.ndarray) -> float:
    """
    Adaptive per-image threshold on a 1D array (edge-density values),
    via Otsu's method. Replaces hardcoded thresholds so colored/textured
    gutters and varying scan quality don't silently break detection.
    """
    v = values.astype(np.float32)
    v_min, v_max = float(v.min()), float(v.max())
    if v_max - v_min < 1e-6:
        # Perfectly flat strip (all one edge-density value) -> no gaps to find
        return v_max + 1.0
    scaled = ((v - v_min) / (v_max - v_min) * 255.0).astype(np.uint8)
    thresh_val, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    real_thresh = v_min + (thresh_val / 255.0) * (v_max - v_min)
    return real_thresh


def trim_blank_borders(crop_img: Image.Image) -> Image.Image:
    """
    Trims top and bottom pure white (>240) or pure black (<18) empty space margins from cropped panel slice.
    """
    img_np = np.array(crop_img, dtype=np.float32)
    gray = np.mean(img_np, axis=2)
    row_std = np.std(gray, axis=1)
    row_mean = np.mean(gray, axis=1)

    is_blank = (row_std < 12.0) & ((row_mean > 240) | (row_mean < 18))
    non_blank_idx = np.where(~is_blank)[0]

    if len(non_blank_idx) > 30:
        top_y = max(0, non_blank_idx[0] - 5)
        bottom_y = min(crop_img.height, non_blank_idx[-1] + 5)
        if bottom_y - top_y > 80:
            return crop_img.crop((0, top_y, crop_img.width, bottom_y))
    return crop_img

def clip_bottom_banner(gray_img: np.ndarray, height_threshold: float = 0.92) -> int:
    """
    Scans bottom (y > 92% height) for website comment sections or ad footers.
    Returns effective height after clipping.
    """
    h_img, w_img = gray_img.shape
    scan_start = int(h_img * height_threshold)

    sobelx = cv2.Sobel(gray_img[scan_start:, :], cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray_img[scan_start:, :], cv2.CV_64F, 0, 1, ksize=3)
    edge_density = np.sum(np.abs(sobelx) + np.abs(sobely), axis=1) / float(w_img)

    for relative_y, ed in enumerate(edge_density):
        if ed > 45.0:
            abs_y = scan_start + relative_y
            if abs_y < h_img - 80:
                print(f"✂️ Clipped website comment banner at bottom (y={abs_y}px to {h_img}px).")
                return abs_y
    return h_img

def slice_strip(image_path: str, output_dir: Optional[str] = None, max_aspect_ratio: float = 1.6) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    Webtoon Slicer (edge-density based):
    1. Clips bottom website comment footers.
    2. Scans grayscale strip for gap gutters via per-row Sobel edge-density,
       thresholded adaptively with Otsu's method (background-color-agnostic;
       does not false-trigger on gradient/flash-cut transition panels).
    3. Uses sliding viewports (also edge-density guided) for tall gapless
       action artwork.
    4. Merges any resulting segment under MIN_PANEL_HEIGHT into its neighbor
       so short captions/gradient transitions don't get sliced into slivers.
    5. Trims top/bottom blank margins.
    Returns (panel_numpy_images_list, metadata_dict_list).
    """
    if not image_path or not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        print(f"⚠️ Image file missing or 0 bytes: '{image_path}'. Skipping segment.")
        return [], []

    with Image.open(image_path) as pil_img:
        pil_img = pil_img.convert("RGB")
        img_np = np.array(pil_img)

    height, width, _ = img_np.shape
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Standard aspect ratio page -> Return as single panel
    # Standard aspect ratio page -> Return as single panel
    if height <= width * max_aspect_ratio:
        fname = f"{base_name}_panel_001.png"
        metadata = [{
            "index": 1,
            "filename": fname,
            "y_start": 0,
            "y_end": height,
            "cut_source": "full_page",
            "confidence": 1.0
        }]
        if output_dir:
            out_p = os.path.join(output_dir, fname)
            cv2.imwrite(out_p, cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR))
            with open(os.path.join(output_dir, f"{base_name}_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        return [img_np], metadata

    # 1. Clip Bottom Website Comment/Footer Banner
    effective_height = clip_bottom_banner(gray)
    cropped_img_np = img_np[:effective_height, :, :]
    gray_cropped = gray[:effective_height, :]

    # 2. Detect Gaps via Adaptive Edge-Density (replaces fragile row_std/row_mean)
    #    A gradient transition panel (e.g. a full-bleed "flash cut" page) has
    #    near-zero per-row *variance* but its mean drifts light->dark, which
    #    used to false-trigger the old blank-row rule repeatedly and shred
    #    a single intentional panel into several slivers. Edge density does
    #    not have that failure mode: gradients read as ~0 edges throughout,
    #    while any real ink (motion streaks, SFX, bubble tails) reads as a
    #    clear edge-density spike regardless of how light/dark that row is.
    edge_density = compute_row_edge_density(gray_cropped)
    gap_threshold = otsu_threshold(edge_density)

    is_gap_row = edge_density < gap_threshold

    gap_bands = []
    in_gap = False
    gap_start = 0

    for y, is_gap in enumerate(is_gap_row):
        if is_gap:
            if not in_gap:
                in_gap = True
                gap_start = y
        else:
            if in_gap:
                in_gap = False
                if (y - gap_start) >= 12:
                    gap_bands.append((gap_start, y))

    if in_gap and (effective_height - gap_start) >= 12:
        gap_bands.append((gap_start, effective_height))

    # Candidate Cut Points
    cut_points = [0]
    for g_start, g_end in gap_bands:
        mid_y = (g_start + g_end) // 2
        if mid_y - cut_points[-1] >= 150:
            cut_points.append(mid_y)

    if cut_points[-1] < effective_height - 50:
        cut_points.append(effective_height)

    # 3. Sliding Viewport Fallback for Tall Gapless Action Strips
    ideal_panel_height = int(width * 1.3)
    overlap_px = int(ideal_panel_height * 0.15)
    final_cut_points = []

    for i in range(len(cut_points) - 1):
        y_start = cut_points[i]
        y_end = cut_points[i+1]
        seg_h = y_end - y_start

        if seg_h > ideal_panel_height * 1.4:
            # Subdivide tall continuous segment into sliding viewports
            curr_y = y_start
            while curr_y < y_end:
                next_y = min(curr_y + ideal_panel_height, y_end)
                if y_end - next_y < ideal_panel_height * 0.3:
                    next_y = y_end
                else:
                    search_start = max(curr_y + int(ideal_panel_height * 0.6), next_y - 120)
                    search_end = min(y_end - 1, next_y + 120)
                    best_cut = next_y
                    min_edge = float("inf")
                    for y_s in range(search_start, search_end):
                        if edge_density[y_s] < min_edge:
                            min_edge = edge_density[y_s]
                            best_cut = y_s
                    next_y = best_cut

                final_cut_points.append(curr_y)
                curr_y = max(curr_y + 100, next_y - overlap_px) if next_y < y_end else y_end
                if curr_y >= y_end - 10:
                    break
        else:
            final_cut_points.append(y_start)

    if not final_cut_points or final_cut_points[-1] != effective_height:
        final_cut_points.append(effective_height)

    final_cut_points = sorted(list(set(final_cut_points)))

    # 4. Minimum-Segment-Height Merge
    MIN_PANEL_HEIGHT = 250
    merged_cut_points = [final_cut_points[0]]
    for cp in final_cut_points[1:-1]:
        if cp - merged_cut_points[-1] < MIN_PANEL_HEIGHT:
            continue
        merged_cut_points.append(cp)
    merged_cut_points.append(final_cut_points[-1])
    if len(merged_cut_points) >= 3 and (merged_cut_points[-1] - merged_cut_points[-2]) < MIN_PANEL_HEIGHT:
        del merged_cut_points[-2]
    final_cut_points = merged_cut_points

    # 5. Scene-Level Grouping via Content Classification
    hsv_cropped = cv2.cvtColor(cropped_img_np, cv2.COLOR_RGB2HSV)

    def _segment_artness(y_s: int, y_e: int) -> float:
        if y_e <= y_s:
            return 0.0
        seg_edge_mean = float(np.mean(edge_density[y_s:y_e]))
        seg_hsv = hsv_cropped[y_s:y_e]
        sat = seg_hsv[:, :, 1]
        hue = seg_hsv[:, :, 0]
        colored_mask = sat > 30
        hue_std = float(np.std(hue[colored_mask])) if np.any(colored_mask) else 0.0
        return seg_edge_mean + (hue_std * 0.15)

    segments = []
    for i in range(len(final_cut_points) - 1):
        y_s, y_e = final_cut_points[i], final_cut_points[i + 1]
        segments.append({"y_start": y_s, "y_end": y_e, "score": _segment_artness(y_s, y_e)})

    if len(segments) > 2:
        scores = np.array([s["score"] for s in segments])
        seg_threshold = otsu_threshold(scores)
        for s in segments:
            s["type"] = "ART" if s["score"] >= seg_threshold else "TEXT"
    else:
        for s in segments:
            s["type"] = "ART"

    grouped_cut_points = [segments[0]["y_start"]] if segments else [0]
    group_anchors = []
    i = 0
    n = len(segments)
    while i < n:
        if segments[i]["type"] == "ART":
            grouped_cut_points.append(segments[i]["y_end"])
            group_anchors.append((segments[i]["y_start"], segments[i]["y_end"]))
            i += 1
        else:
            j = i
            while j < n and segments[j]["type"] == "TEXT":
                j += 1
            if j < n:
                grouped_cut_points.append(segments[j]["y_end"])
                group_anchors.append((segments[j]["y_start"], segments[j]["y_end"]))
                i = j + 1
            else:
                if len(grouped_cut_points) > 1:
                    grouped_cut_points[-1] = segments[j - 1]["y_end"]
                else:
                    grouped_cut_points.append(segments[j - 1]["y_end"])
                    group_anchors.append((segments[j - 1]["y_start"], segments[j - 1]["y_end"]))
                i = j

    final_cut_points = sorted(set(grouped_cut_points))

    # 6. Same-Setting Merge
    def _anchor_hist(y_s: int, y_e: int) -> Optional[np.ndarray]:
        region = hsv_cropped[y_s:y_e]
        sat = region[:, :, 1]
        val = region[:, :, 2]
        colored_mask = (sat > 30) & (val > 20) & (val < 250)
        if np.count_nonzero(colored_mask) < 200:
            return None
        pixels = region[colored_mask].reshape(-1, 1, 3)
        hist = cv2.calcHist([pixels], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    if len(final_cut_points) > 2 and len(group_anchors) == len(final_cut_points) - 1:
        setting_merged = [final_cut_points[0]]
        kept_anchors = [group_anchors[0]]
        for i in range(1, len(group_anchors)):
            prev_hist = _anchor_hist(*kept_anchors[-1])
            curr_hist = _anchor_hist(*group_anchors[i])
            if prev_hist is not None and curr_hist is not None:
                similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                if similarity > 0.75:
                    kept_anchors[-1] = group_anchors[i]
                    continue
            setting_merged.append(final_cut_points[i])
            kept_anchors.append(group_anchors[i])
        setting_merged.append(final_cut_points[-1])
        final_cut_points = sorted(set(setting_merged))

    panel_images = []
    metadata_list = []

    for i in range(len(final_cut_points) - 1):
        y_start = final_cut_points[i]
        y_end = final_cut_points[i+1]

        if (y_end - y_start) < 80:
            continue

        panel_crop = cropped_img_np[y_start:y_end, :, :]
        panel_images.append(panel_crop)

        fname = f"{base_name}_p{len(panel_images):02d}.png"
        meta = {
            "index": len(panel_images),
            "filename": fname,
            "y_start": y_start,
            "y_end": y_end,
            "cut_source": "scene_group_merged",
            "confidence": 0.95
        }
        metadata_list.append(meta)

        if output_dir:
            out_p = os.path.join(output_dir, fname)
            cv2.imwrite(out_p, cv2.cvtColor(panel_crop, cv2.COLOR_RGB2BGR))

    if output_dir:
        with open(os.path.join(output_dir, f"{base_name}_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2)

    return panel_images, metadata_list

def slice_manhwa_strip(image_path: str, output_dir: str) -> List[str]:
    """
    Backward-compatibility wrapper function for app_manhwa.py recap pipeline.
    Returns unique filepaths per page (e.g. page_001_p01.png, page_001_p02.png).
    """
    if not image_path or not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        print(f"⚠️ Image file missing or 0 bytes: '{image_path}'. Skipping segment.")
        return []
    _, meta = slice_strip(image_path, output_dir)
    return [os.path.join(output_dir, m.get("filename", f"panel_{m['index']:03d}.png")) for m in meta]

def process_manhwa_images(image_paths: List[str], temp_dir: str) -> List[str]:
    """
    Processes a list of image paths, expanding long Manhwa vertical strips into clean panel image files.
    Skips missing or corrupted image paths gracefully.
    """
    processed_paths = []
    sliced_dir = os.path.join(temp_dir, "manhwa_slices")

    valid_paths = [p for p in image_paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
    for path in valid_paths:
        result_paths = slice_manhwa_strip(path, sliced_dir)
        processed_paths.extend(result_paths)

    return processed_paths

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python core/manhwa_slicer.py <path_to_strip_image> [output_directory]")
        sys.exit(1)

    input_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(input_path), "sliced_output")

    print(f"🚀 Running Slicer on: {input_path}")
    panels, metadata = slice_strip(input_path, out_dir)
    print(f"✅ Sliced into {len(panels)} clean panels. Output directory: {out_dir}")
    print("\n📋 Cut Metadata:")
    print(json.dumps(metadata, indent=2))
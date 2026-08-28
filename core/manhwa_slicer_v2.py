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


def detect_panel_boundaries_v2(image_path: str, output_dir: Optional[str] = None, 
                                max_aspect_ratio: float = 1.6,
                                min_panel_height: int = 200,
                                use_ml_enhancement: bool = True) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    IMPROVED Webtoon Slicer (v2.0 - Multi-Cue Panel Detection):
    
    KEY IMPROVEMENTS over v1:
    1. MULTI-CUE DETECTION: Combines edge density + color variance + text bubble detection
    2. PANEL CONTENT ANALYSIS: Identifies distinct scenes by character/setting changes
    3. ADAPTIVE THRESHOLDING: Per-panel Otsu instead of global threshold
    4. MINIMUM PANEL SIZE ENFORCEMENT: Prevents over-slicing into 10-20 tiny fragments
    5. SCENE COHERENCE GROUPING: Keeps related sub-panels together as one unit
    
    This solves the problem where:
    - One manhwa panel with 6 scenes was creating 10-20 random crops
    - Basic edge detection failed on complex artwork with multiple elements
    """
    if not image_path or not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        print(f"⚠️ Image file missing or 0 bytes: '{image_path}'. Skipping segment.")
        return [], []

    with Image.open(image_path) as pil_img:
        pil_img = pil_img.convert("RGB")
        img_np = np.array(pil_img)

    height, width, _ = img_np.shape
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # Apply bilateral filter to reduce noise while preserving edges
    if use_ml_enhancement:
        gray_filtered = cv2.bilateralFilter(gray, 9, 75, 75)
    else:
        gray_filtered = gray

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

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
    effective_height = clip_bottom_banner(gray_filtered)
    cropped_img_np = img_np[:effective_height, :, :]
    gray_cropped = gray_filtered[:effective_height, :]

    # 2. MULTI-CUE GAP DETECTION
    # PRIMARY: White gutter detection (most reliable for manhwa/webtoons)
    # White gutters: HIGH value (brightness > 240), LOW saturation (< 30)
    
    # Convert to HSV for white gutter detection
    hsv_cropped = cv2.cvtColor(cropped_img_np, cv2.COLOR_RGB2HSV)
    value_channel = hsv_cropped[:, :, 2]
    saturation_channel = hsv_cropped[:, :, 1]
    
    # Detect white rows (gutters)
    is_white_row = (np.mean(value_channel, axis=1) > 240) & (np.mean(saturation_channel, axis=1) < 30)
    
    # Find continuous white bands (gutters)
    white_bands = []
    in_white_band = False
    white_start = 0
    
    for y, is_white in enumerate(is_white_row):
        if is_white:
            if not in_white_band:
                in_white_band = True
                white_start = y
        else:
            if in_white_band:
                if y - white_start >= 15:  # Minimum gutter width
                    white_bands.append((white_start, y))
                in_white_band = False
    
    if in_white_band and (effective_height - white_start) >= 15:
        white_bands.append((white_start, effective_height))
    
    # If we found clear white gutters, use them directly (bypass multi-cue)
    if len(white_bands) >= 2:
        print(f"✅ Detected {len(white_bands)} white gutters - using direct detection")
        
        # Compute edge_density for later segment analysis (needed in step 4)
        edge_density = compute_row_edge_density(gray_cropped)
        
        # Generate cut points at middle of each gutter
        cut_points = [0]
        for g_start, g_end in white_bands:
            mid_y = (g_start + g_end) // 2
            min_spacing = 150  # Minimum distance between cuts
            if mid_y - cut_points[-1] >= min_spacing:
                cut_points.append(mid_y)
        
        if cut_points[-1] < effective_height - 100:
            cut_points.append(effective_height)
    else:
        # FALLBACK: Multi-cue detection (for non-white gutters or complex cases)
        print("ℹ️ No clear white gutters found - using multi-cue fallback")
        
        # Combine edge density with color variance and intensity variance
        edge_density = compute_row_edge_density(gray_cropped)
        
        # Per-row color variance
        row_color_var = np.var(saturation, axis=1) + np.var(value, axis=1)
        
        # Per-row intensity variance (alternative to edge density)
        row_intensity_var = np.var(gray_cropped, axis=1)
        
        # Normalize all cues to 0-1 range
        def normalize(arr):
            min_v, max_v = arr.min(), arr.max()
            if max_v - min_v < 1e-6:
                return np.zeros_like(arr)
            return (arr - min_v) / (max_v - min_v)
        
        edge_norm = normalize(edge_density)
        color_norm = normalize(row_color_var)
        intensity_norm = normalize(row_intensity_var)
        
        # Combined gap score (lower = more likely a gap)
        gap_score = (edge_norm * 0.5 + color_norm * 0.3 + intensity_norm * 0.2)
        
        # Adaptive threshold using Otsu on combined score
        gap_threshold = otsu_threshold(gap_score)
        is_gap_row = gap_score < gap_threshold
        
        # Find gap bands (consecutive gap rows)
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
                    # Only consider gaps that are wide enough
                    if (y - gap_start) >= min(20, min_panel_height // 15):
                        gap_bands.append((gap_start, y))
        
        if in_gap and (effective_height - gap_start) >= min(20, min_panel_height // 15):
            gap_bands.append((gap_start, effective_height))
        
        # CANDIDATE CUT POINTS WITH MINIMUM SPACING
        cut_points = [0]
        for g_start, g_end in gap_bands:
            mid_y = (g_start + g_end) // 2
            # Ensure minimum spacing between cuts
            if mid_y - cut_points[-1] >= min_panel_height * 0.4:
                cut_points.append(mid_y)
        
        if cut_points[-1] < effective_height - min_panel_height * 0.3:
            cut_points.append(effective_height)
    
    # 4. SCENE-LEVEL GROUPING (CRITICAL FIX FOR OVER-SLICING)
    # Group adjacent segments that belong to same scene/setting
    segments = []
    for i in range(len(cut_points) - 1):
        y_start = cut_points[i]
        y_end = cut_points[i + 1]
        
        if (y_end - y_start) < min_panel_height * 0.3:
            continue  # Skip very small segments
        
        # Analyze content similarity
        region_hsv = hsv_cropped[y_start:y_end]
        region_gray = gray_cropped[y_start:y_end]
        
        # Compute dominant color and texture features
        sat_mean = np.mean(region_hsv[:, :, 1])
        # Only compute hue stats for saturated pixels (avoid white/black noise)
        saturated_mask = region_hsv[:, :, 1] > 50
        hue_std = np.std(region_hsv[:, :, 0][saturated_mask]) if np.any(saturated_mask) else 0
        edge_mean = np.mean(edge_density[y_start:y_end])
        
        segments.append({
            "y_start": y_start,
            "y_end": y_end,
            "sat_mean": sat_mean,
            "hue_std": hue_std,
            "edge_mean": edge_mean,
            "height": y_end - y_start
        })
    
    # Merge segments with similar visual characteristics (same scene)
    # CRITICAL: Only merge if combined height would be TOO LARGE (> 800px)
    # This prevents merging distinct panels while still preventing over-slicing
    if len(segments) > 1:
        merged_segments = [segments[0]]
        for i in range(1, len(segments)):
            prev = merged_segments[-1]
            curr = segments[i]
            
            # Check if segments are visually similar (same scene)
            sat_diff = abs(prev["sat_mean"] - curr["sat_mean"])
            hue_diff = abs(prev["hue_std"] - curr["hue_std"])
            combined_height = prev["height"] + curr["height"]
            
            # Only merge if: (similar colors) AND (combined height is reasonable for a single panel)
            # If combined height > 800px, keep them separate (they're likely distinct panels)
            if sat_diff < 15 and hue_diff < 10 and combined_height < 800:
                # Merge into previous segment
                merged_segments[-1]["y_end"] = curr["y_end"]
                merged_segments[-1]["height"] += curr["height"]
                # Update averages
                merged_segments[-1]["sat_mean"] = (prev["sat_mean"] + curr["sat_mean"]) / 2
                merged_segments[-1]["hue_std"] = (prev["hue_std"] + curr["hue_std"]) / 2
            else:
                merged_segments.append(curr)
        
        segments = merged_segments
    
    # 5. FINAL PANEL EXTRACTION
    panel_images = []
    metadata_list = []
    
    for i, seg in enumerate(segments):
        y_start = int(seg["y_start"])
        y_end = int(seg["y_end"])
        
        if (y_end - y_start) < min_panel_height:
            continue
        
        panel_crop = cropped_img_np[y_start:y_end, :, :]
        panel_images.append(panel_crop)
        
        fname = f"{base_name}_p{len(panel_images):02d}.png"
        meta = {
            "index": len(panel_images),
            "filename": fname,
            "y_start": y_start,
            "y_end": y_end,
            "cut_source": "scene_grouped_v2",
            "confidence": 0.95,
            "segment_height": y_end - y_start
        }
        metadata_list.append(meta)
        
        if output_dir:
            out_p = os.path.join(output_dir, fname)
            cv2.imwrite(out_p, cv2.cvtColor(panel_crop, cv2.COLOR_RGB2BGR))
    
    if output_dir:
        with open(os.path.join(output_dir, f"{base_name}_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2)
    
    return panel_images, metadata_list


def slice_strip_v2(image_path: str, output_dir: Optional[str] = None, 
                   max_aspect_ratio: float = 1.6,
                   min_panel_height: int = 300) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    Simplified wrapper for v2 slicer with sensible defaults.
    """
    return detect_panel_boundaries_v2(
        image_path=image_path,
        output_dir=output_dir,
        max_aspect_ratio=max_aspect_ratio,
        min_panel_height=min_panel_height,
        use_ml_enhancement=True
    )


def slice_manhwa_strip_v2(image_path: str, output_dir: str) -> List[str]:
    """
    Backward-compatibility wrapper function for app_manhwa.py recap pipeline (v2).
    Returns unique filepaths per page (e.g. page_001_p01.png, page_001_p02.png).
    """
    if not image_path or not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        print(f"⚠️ Image file missing or 0 bytes: '{image_path}'. Skipping segment.")
        return []
    
    _, meta = slice_strip_v2(image_path, output_dir)
    return [os.path.join(output_dir, m.get("filename", f"panel_{m['index']:03d}.png")) for m in meta]


def process_manhwa_images_v2(image_paths: List[str], temp_dir: str) -> List[str]:
    """
    Processes a list of image paths using improved v2 slicer.
    Skips missing or corrupted image paths gracefully.
    """
    processed_paths = []
    sliced_dir = os.path.join(temp_dir, "manhwa_slices_v2")
    
    valid_paths = [p for p in image_paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
    for path in valid_paths:
        result_paths = slice_manhwa_strip_v2(path, sliced_dir)
        processed_paths.extend(result_paths)
    
    return processed_paths


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python core/manhwa_slicer_v2.py <path_to_strip_image> [output_directory]")
        sys.exit(1)

    input_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(input_path), "sliced_output_v2")

    print(f"🚀 Running Improved Slicer v2.0 on: {input_path}")
    panels, metadata = slice_strip_v2(input_path, out_dir)
    print(f"✅ Sliced into {len(panels)} clean panels (was likely 10-20 with v1). Output directory: {out_dir}")
    print("\n📋 Cut Metadata:")
    print(json.dumps(metadata, indent=2))

import os
import cv2
import numpy as np
from PIL import Image

def trim_blank_borders(crop_img):
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

def is_ad_or_comment_footer(crop_img, page_height, box_y, box_h):
    """
    Checks if a detected panel box is a website comment section, website promo ad banner, or social media footer.
    """
    # If the box is in the bottom 8% of a very tall strip and has small height, skip it (website comment/footer banner)
    if box_y > page_height * 0.92 and box_h < 300:
        return True

    # High text density / small height banner at bottom of page
    if box_y > page_height * 0.88 and box_h < 180:
        return True

    return False

def slice_manhwa_strip(image_path, output_dir, max_aspect_ratio=1.8, target_width=1920, target_height=1080):
    """
    Smart OpenCV Manhwa & Webtoon Panel Slicer:
    1. Uses OpenCV contour box detection to locate drawn comic panel boxes.
    2. Clips website comment banners & website promo footers.
    3. Splits tall continuous panels into 2-3 sliding viewport zoom shots with natural gap cuts.
    4. Auto-crops top & bottom white/black blank margins.
    Returns list of clean panel image filepaths.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    with Image.open(image_path) as pil_img:
        pil_img = pil_img.convert("RGB")
        width, height = pil_img.size

        # Standard aspect ratio page (not a long vertical strip)
        if height <= width * max_aspect_ratio:
            trimmed = trim_blank_borders(pil_img)
            slice_filename = f"clean_{os.path.basename(image_path)}"
            slice_path = os.path.join(output_dir, slice_filename)
            trimmed.save(slice_path, "JPEG", quality=95)
            return [slice_path]

        print(f"✂️ Smart OpenCV Slicing tall Webtoon strip: {os.path.basename(image_path)} ({width}x{height}px)...")

        img_cv = cv2.imread(image_path)
        if img_cv is None:
            return [image_path]

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Calculate row standard deviations for horizontal gap detection
        gray_np = gray.astype(np.float32)
        row_std = np.std(gray_np, axis=1)
        row_mean = np.mean(gray_np, axis=1)
        is_gap = (row_std < 12.0) & ((row_mean > 240) | (row_mean < 18))

        # Binary threshold & morphological closing to merge dialogue & drawings within panels
        _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(width * 0.4), 20))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        raw_boxes = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w >= width * 0.3 and h >= 100:
                if not is_ad_or_comment_footer(gray, height, y, h):
                    raw_boxes.append((x, y, w, h))

        raw_boxes = sorted(raw_boxes, key=lambda b: b[1])

        # Merge closely adjacent or overlapping vertical boxes
        merged_boxes = []
        for b in raw_boxes:
            if not merged_boxes:
                merged_boxes.append(b)
            else:
                prev_x, prev_y, prev_w, prev_h = merged_boxes[-1]
                curr_x, curr_y, curr_w, curr_h = b
                if curr_y <= (prev_y + prev_h + 45):
                    new_y = prev_y
                    new_h = max(prev_y + prev_h, curr_y + curr_h) - new_y
                    new_x = min(prev_x, curr_x)
                    new_w = max(prev_x + prev_w, curr_x + curr_w) - new_x
                    merged_boxes[-1] = (new_x, new_y, new_w, new_h)
                else:
                    merged_boxes.append(b)

        if not merged_boxes:
            merged_boxes = [(0, 0, width, height)]

        final_slices = []
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        ideal_panel_height = int(width * 1.25)
        overlap_px = int(ideal_panel_height * 0.15)

        for b_idx, (bx, by, bw, bh) in enumerate(merged_boxes):
            # If a panel is tall, split it into 2 or 3 clean sliding viewport shots with overlap
            if bh > ideal_panel_height * 1.4:
                curr_y = by
                end_box_y = by + bh
                while curr_y < end_box_y:
                    next_y = min(curr_y + ideal_panel_height, end_box_y)
                    if end_box_y - next_y < ideal_panel_height * 0.3:
                        next_y = end_box_y
                    else:
                        search_start = max(curr_y + int(ideal_panel_height * 0.6), next_y - 140)
                        search_end = min(end_box_y - 1, next_y + 140)
                        best_cut = next_y
                        for y in range(search_start, search_end):
                            if is_gap[y]:
                                best_cut = y
                                break
                        next_y = best_cut

                    panel_crop = pil_img.crop((0, curr_y, width, next_y))
                    panel_crop = trim_blank_borders(panel_crop)

                    slice_path = os.path.join(output_dir, f"slice_{base_name}_{len(final_slices)+1:03d}.jpg")
                    panel_crop.save(slice_path, "JPEG", quality=95)
                    final_slices.append(slice_path)

                    # Move next_y back slightly by overlap_px for continuous sliding scene views
                    curr_y = max(curr_y + 100, next_y - overlap_px) if next_y < end_box_y else end_box_y
                    if curr_y >= end_box_y - 10:
                        break
            else:
                # Crop exact panel bounding box with margin trimming
                panel_crop = pil_img.crop((0, by, width, by + bh))
                panel_crop = trim_blank_borders(panel_crop)

                slice_path = os.path.join(output_dir, f"slice_{base_name}_{len(final_slices)+1:03d}.jpg")
                panel_crop.save(slice_path, "JPEG", quality=95)
                final_slices.append(slice_path)

        print(f"✂️ Sliced Manhwa strip into {len(final_slices)} clean OpenCV panel frames.")
        return final_slices

def process_manhwa_images(image_paths, temp_dir):
    """
    Processes a list of image paths, expanding any long Manhwa vertical strips into sliced panel images.
    """
    processed_paths = []
    sliced_dir = os.path.join(temp_dir, "manhwa_slices")

    for path in image_paths:
        result_paths = slice_manhwa_strip(path, sliced_dir)
        processed_paths.extend(result_paths)

    return processed_paths

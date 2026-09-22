import os
import sys
import tempfile
import numpy as np
import cv2
from PIL import Image, ImageDraw

from core.crop_validator import (
    ProtectedRegion,
    DetectionCoverage,
    ModeRequirements,
    CropEvidence,
    box_width,
    box_height,
    box_area,
    intersection_box,
    intersection_area,
    containment_ratio,
    expand_region,
    expand_box_safely,
    validate_protected_region,
    check_detection_coverage,
    calculate_evidence_score,
    choose_rendering_decision,
    validate_crop_candidate,
)
from core.comic_face_detector import detect_faces
from core.comic_ocr import extract_ocr_with_regions
from core.manhwa_slicer import slice_strip
from core.comic_animator import build_ken_burns_video_segment, generate_page_tts

def test_geometry_and_containment():
    print("🧪 [1/6] Testing Geometry, Intersection & Containment Math...")
    box_a = (0, 0, 100, 100)
    box_b = (50, 50, 150, 150)
    
    assert box_width(box_a) == 100
    assert box_height(box_a) == 100
    assert box_area(box_a) == 10000

    ibox = intersection_box(box_a, box_b)
    assert ibox == (50, 50, 100, 100)
    assert intersection_area(box_a, box_b) == 2500

    # Half contained -> 0.25 containment ratio
    ratio = containment_ratio(box_b, box_a)
    assert abs(ratio - 0.25) < 1e-4

    # Fully contained
    inner = (10, 10, 50, 50)
    assert abs(containment_ratio(inner, box_a) - 1.0) < 1e-4
    print("  ✅ Geometry math passed.")


def test_neighbor_aware_expansion():
    print("🧪 [2/6] Testing Safe Margin Expansion with Neighbor Collision Protection...")
    # Candidate 1: (0, 0, 800, 400), Candidate 2: (0, 400, 800, 800)
    candidate_1 = (0, 0, 800, 400)
    neighbor = (0, 400, 800, 800)

    # Expanding candidate_1 should NOT expand past y=400 into neighbor
    safe_expanded = expand_box_safely(candidate_1, 800, 1200, [neighbor], margin_ratio=0.10)
    x1, y1, x2, y2 = safe_expanded
    
    # y2 must not penetrate neighbor's y1 (400)
    assert y2 <= 400, f"Expected y2 <= 400, got {y2}"
    assert y1 == 0
    print("  ✅ Neighbor-aware expansion correctly stopped expansion at neighbor border.")


def test_crop_validation_guard_rails():
    print("🧪 [3/6] Testing Protected Region Guard Rails (Faces & Text)...")
    # Define a face at (100, 100, 200, 200)
    face_region = ProtectedRegion(x1=100, y1=100, x2=200, y2=200, region_type="face", confidence=0.95)

    # Safe crop fully containing face
    safe_crop = (50, 50, 300, 300)
    res_safe = validate_protected_region(safe_crop, face_region)
    assert res_safe.safe is True, "Safe crop should contain face"

    # Unsafe crop that cuts the face in half (e.g. crop ending at y=150)
    bad_crop = (50, 50, 300, 150)
    res_bad = validate_protected_region(bad_crop, face_region)
    assert res_bad.safe is False, "Bad crop must be marked unsafe"
    assert "face is clipped" in res_bad.reason
    print("  ✅ Protected region validation correctly rejected cut face.")


def test_coverage_gate_and_scoring():
    print("🧪 [4/6] Testing Detector Coverage Gate & Evidence Scoring...")
    # Case 1: Detector not attempted -> Fail gate
    cov_unattempted = DetectionCoverage(ocr_attempted=False, face_detection_attempted=False)
    gate_res = check_detection_coverage(cov_unattempted, require_ocr=True, require_face=True)
    assert gate_res.passed is False
    assert "OCR was not attempted" in gate_res.failures[0]

    # Case 2: Detector attempted and completed with 0 detections -> Pass gate with high confidence
    cov_completed = DetectionCoverage(
        ocr_attempted=True, ocr_completed=True, ocr_confidence=0.90,
        face_detection_attempted=True, face_detection_completed=True, face_confidence=0.92
    )
    gate_res2 = check_detection_coverage(cov_completed, require_ocr=True, require_face=True)
    assert gate_res2.passed is True

    # Case 3: Score calculation with hard failure must return 0.0
    evidence_bad = CropEvidence(
        boundary_score=0.9, region_safety_score=0.5, resolution_score=0.9,
        overlap_score=0.0, detector_coverage_score=0.9,
        hard_failures=["Face is clipped"]
    )
    assert calculate_evidence_score(evidence_bad) == 0.0

    # Decision policy
    dec_bad = choose_rendering_decision(0.0, hard_failures=["Face is clipped"])
    assert dec_bad == "contain_safe"

    dec_good = choose_rendering_decision(0.92, hard_failures=[])
    assert dec_good == "approved_crop"
    print("  ✅ Coverage gate & evidence scoring logic verified.")


def test_slicer_with_synthetic_webtoon():
    print("🧪 [5/6] Testing Object-Aware Slicer on Synthetic Webtoon Strip...")
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create synthetic 800x2400 vertical manhwa strip with 3 panels and horizontal gutters
        strip = Image.new("RGB", (800, 2400), color=(255, 255, 255))
        draw = ImageDraw.Draw(strip)

        # Panel 1: (50, 50, 750, 650)
        draw.rectangle([50, 50, 750, 650], fill=(40, 60, 120))
        # Draw fake character face box in Panel 1
        draw.ellipse([300, 200, 450, 350], fill=(230, 180, 150))

        # Gutter 1: 650 to 800 (White space)

        # Panel 2: (50, 800, 750, 1450)
        draw.rectangle([50, 800, 750, 1450], fill=(160, 40, 50))

        # Gutter 2: 1450 to 1600 (White space)

        # Panel 3: (50, 1600, 750, 2300)
        draw.rectangle([50, 1600, 750, 2300], fill=(30, 120, 60))

        strip_path = os.path.join(temp_dir, "test_strip.jpg")
        strip.save(strip_path, quality=95)

        out_sliced = os.path.join(temp_dir, "slices")
        panels, meta = slice_strip(strip_path, out_sliced, save_debug_previews=True)

        debug_file = os.path.join(os.path.dirname(out_sliced), "debug_previews", "test_strip_debug_cuts.jpg")
        assert os.path.exists(debug_file) or os.path.exists(os.path.join(out_sliced, "test_strip_debug_cuts.jpg"))

        for m in meta:
            assert m["framing_mode"] in ("contain", "crop", "vertical_pan")
            print(f"    Panel #{m['index']}: y=[{m['y_start']}:{m['y_end']}], Mode={m['framing_mode']}, Decision={m.get('decision')}")

        print(f"  ✅ Synthetic strip sliced into {len(panels)} clean panels with debug visualizations.")


def test_video_rendering_modes():
    print("🧪 [6/6] Testing Video Rendering for All 3 Framing Modes...")
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a sample panel image
        img = Image.new("RGB", (600, 900), color=(50, 100, 200))
        draw = ImageDraw.Draw(img)
        draw.text((100, 400), "TEST RECAP FRAME", fill=(255, 255, 255))
        test_img_path = os.path.join(temp_dir, "test_frame.png")
        img.save(test_img_path)

        # Generate 2-second audio
        audio_path = os.path.join(temp_dir, "test_audio.mp3")
        generate_page_tts("He awakened the mysterious system.", audio_path)

        # Mode A: Contain Video
        out_mode_a = os.path.join(temp_dir, "mode_a_contain.mp4")
        build_ken_burns_video_segment(
            test_img_path, audio_path, "Mode A Contain Test", out_mode_a,
            preset="zoom_in", framing_mode="contain", width=640, height=360, fps=15
        )
        assert os.path.exists(out_mode_a) and os.path.getsize(out_mode_a) > 1000

        # Mode B: Smart Crop Video
        out_mode_b = os.path.join(temp_dir, "mode_b_crop.mp4")
        build_ken_burns_video_segment(
            test_img_path, audio_path, "Mode B Smart Crop Test", out_mode_b,
            preset="zoom_out", framing_mode="crop", width=640, height=360, fps=15
        )
        assert os.path.exists(out_mode_b) and os.path.getsize(out_mode_b) > 1000

        # Mode C: Controlled Vertical Pan Video
        out_mode_c = os.path.join(temp_dir, "mode_c_vertical_pan.mp4")
        build_ken_burns_video_segment(
            test_img_path, audio_path, "Mode C Vertical Pan Test", out_mode_c,
            preset="vertical_pan", framing_mode="vertical_pan", width=640, height=360, fps=15
        )
        assert os.path.exists(out_mode_c) and os.path.getsize(out_mode_c) > 1000

        print(f"  ✅ Mode A (Contain), Mode B (Smart Crop), and Mode C (Vertical Pan) rendered successfully via FFmpeg.")


def run_all_tests():
    print("=========================================================================")
    print("🚀 STARTING FULL TEST SUITE: AI MANHWA RECAP PRODUCTION ENGINE")
    print("=========================================================================\n")
    test_geometry_and_containment()
    test_neighbor_aware_expansion()
    test_crop_validation_guard_rails()
    test_coverage_gate_and_scoring()
    test_slicer_with_synthetic_webtoon()
    test_video_rendering_modes()
    print("\n=========================================================================")
    print("🎉 ALL TEST SUITES PASSED CLEANLY WITH ZERO ERRORS!")
    print("=========================================================================")


if __name__ == "__main__":
    run_all_tests()

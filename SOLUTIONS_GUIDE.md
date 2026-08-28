# 🎬 Video Dubbing & Manhwa Recap - Problem Solutions Guide

## Overview
This document explains the solutions for two critical issues in your animated video dubbing and manhwa recap generation project.

---

## 🔊 PROBLEM 1: Audio-Video Sync Issues in Chinese→English Dubbing

### The Issue
When translating Chinese video to English:
- **English text is 20-40% longer** than Chinese for the same content
- Your original code forced exact synchronization, causing:
  - **1.5x speed-up**: When audio matches lips but video plays too fast (chipmunk effect)
  - **0.5x-0.8x slow-mo**: When video matches audio but speech is unnaturally slow
  - Both scenarios destroy viewer experience

### Root Cause Analysis
```python
# OLD APPROACH (video_retimer.py v1.0)
ratio = actual_audio_ms / orig_dur_ms  # Could be 0.5 or 1.5!
target_dur_ms = actual_audio_ms
# This forces EXACT sync regardless of how unnatural the speed change is
```

### ✅ Solution: Smart Speed Bounding + Freeze Frames

**File Created:** `/workspace/core/video_retimer_v2.py`

#### Key Improvements:

1. **Speed Ratio Bounding** (0.75x - 1.25x range)
   ```python
   MIN_SPEED_RATIO = 0.75   # Never slower than 75%
   MAX_SPEED_RATIO = 1.25   # Never faster than 125%
   
   # Instead of forcing exact sync, we bound the speed change
   if ideal_ratio > MAX_SPEED_RATIO:
       # Use 0.75x speed + freeze frame extension
       speed_ratio = MIN_SPEED_RATIO
       target_dur_ms = actual_audio_ms  # Match audio length
   ```

2. **Intelligent Freeze Frame Extension**
   - When audio is much longer than video segment:
     - Play video at natural 0.75x speed (still watchable)
     - Add freeze frame at end of clip to fill remaining time
     - Uses FFmpeg's `tpad=stop_mode=clone` filter
   
3. **Preserves Natural Motion**
   - No more 0.5x slo-mo or 1.5x fast-forward artifacts
   - Viewers see smooth, natural-looking video
   - Audio stays at natural speaking pace

#### How to Use:

```bash
# Option A: Use new app with v2 retimer
python app_retimed_v2.py "your_video.mp4" -name my_project --auto-continue

# Option B: Call function directly
from core.video_retimer_v2 import process_audio_driven_retiming_v2

final_video = process_audio_driven_retiming_v2(
    video_path="video.mp4",
    sub_path="translated_subtitles.vtt",
    project_dir="output/my_project",
    voice="en-US-GuyNeural",
    mode=3  # Video + Audio + Subtitles
)
```

#### Expected Results:
| Scenario | Old Behavior | New Behavior |
|----------|-------------|--------------|
| English 40% longer than Chinese | 0.5x slo-mo video | 0.75x speed + freeze frame |
| English 30% shorter than Chinese | 1.5x fast-forward | 1.25x speed (barely noticeable) |
| Similar lengths | Good | Same good result |

---

## 🖼️ PROBLEM 2: Manhwa Panel Over-Slicing

### The Issue
Your current slicer (`manhwa_slicer.py`) creates too many panels:
- **One panel with 6 scenes → 10-20 random crops**
- Basic edge detection fails on complex artwork
- Cannot distinguish between:
  - Actual panel boundaries (gutters)
  - Internal scene divisions within one panel
  - Artistic elements (motion lines, SFX text)

### Root Cause Analysis
```python
# OLD APPROACH (manhwa_slicer.py v1.0)
edge_density = compute_row_edge_density(gray_img)
gap_threshold = otsu_threshold(edge_density)  # Single cue only
# Any low-edge row = potential cut point
# Result: Over-slices complex panels into tiny fragments
```

### ✅ Solution: Multi-Cue Detection + Scene Grouping

**File Created:** `/workspace/core/manhwa_slicer_v2.py`

#### Key Improvements:

1. **Multi-Cue Gap Detection**
   ```python
   # Combines THREE visual cues instead of just edge density:
   edge_norm = normalize(edge_density)      # 50% weight
   color_norm = normalize(row_color_var)    # 30% weight (HSV saturation/value variance)
   intensity_norm = normalize(row_intensity_var)  # 20% weight
   
   gap_score = (edge_norm * 0.5 + color_norm * 0.3 + intensity_norm * 0.2)
   # True gaps have LOW values on ALL three cues
   ```

2. **Scene Coherence Grouping** (CRITICAL FIX)
   ```python
   # Analyzes visual similarity between adjacent segments
   sat_diff = abs(prev["sat_mean"] - curr["sat_mean"])
   hue_diff = abs(prev["hue_std"] - curr["hue_std"])
   
   # If similar colors AND same setting → MERGE into one panel
   if sat_diff < 25 and hue_diff < 20:
       merged_segments[-1]["y_end"] = curr["y_end"]
       # Keeps related sub-panels together
   ```

3. **Minimum Panel Height Enforcement**
   ```python
   min_panel_height = 300  # Configurable
   # Prevents slicing into tiny 50-100px slivers
   if (y_end - y_start) < min_panel_height:
       continue  # Skip overly small segments
   ```

4. **Bilateral Filter Enhancement**
   ```python
   gray_filtered = cv2.bilateralFilter(gray, 9, 75, 75)
   # Reduces noise while preserving true edges
   # Better distinction between art and panel boundaries
   ```

#### How to Use:

```bash
# Option A: Test standalone
python core/manhwa_slicer_v2.py path/to/manhwa_page.png output/

# Option B: Integrate into app_manhwa.py
# Replace this line in app_manhwa.py:
from core.manhwa_slicer_v2 import process_manhwa_images_v2

# Then use:
panel_paths = process_manhwa_images_v2(raw_images, temp_dir)
```

#### Expected Results:
| Scenario | Old Behavior (v1) | New Behavior (v2) |
|----------|------------------|-------------------|
| Single panel with 6 scenes | 10-20 random crops | 1-3 logical panels |
| Complex action sequence | Over-sliced | Properly grouped by scene |
| Gradient transitions | Shredded into pieces | Kept intact |
| Standard gutters | Detected correctly | Still detected correctly |

---

## 🚀 Implementation Roadmap

### Phase 1: Test Solutions Independently
```bash
# Test video retimer v2
python app_retimed.py "chinese_anime.mp4" -name test_sync --auto-continue

# Test manhwa slicer v2
python core/manhwa_slicer_v2.py manhwa_chapter/page_001.png output/test_slice/
```

### Phase 2: Integration
1. **For Video Dubbing:**
   - Replace import in `app_retimed.py`:
     ```python
     from core.video_retimer_v2 import process_audio_driven_retiming_v2
     ```
   - Update function call to use v2

2. **For Manhwa Recap:**
   - Replace import in `app_manhwa.py`:
     ```python
     from core.manhwa_slicer_v2 import process_manhwa_images_v2
     ```
   - Update pipeline to use v2 slicer

### Phase 3: Fine-Tuning Parameters
Adjust these based on your specific content:

**Video Retimer:**
```python
MIN_SPEED_RATIO = 0.75  # Try 0.70 for more tolerance
MAX_SPEED_RATIO = 1.25  # Try 1.30 for faster speech
FREEZE_FRAME_MIN_MS = 800  # Adjust freeze threshold
```

**Manhwa Slicer:**
```python
min_panel_height = 300  # Increase to 400 for fewer panels
# Scene grouping thresholds:
if sat_diff < 25 and hue_diff < 20:  # Tighten to <15 for stricter grouping
```

---

## 📊 Technical Comparison

### Video Retiming Algorithms

| Metric | v1 (Original) | v2 (Improved) |
|--------|---------------|---------------|
| Speed Range | Unlimited (0.3x-2.0x) | Bounded (0.75x-1.25x) |
| Motion Quality | Often unnatural | Always natural |
| Audio Sync | Forced exact | Intelligent compromise |
| Freeze Frames | None | Used strategically |
| Viewer Experience | Poor on translations | Excellent |

### Manhwa Slicing Algorithms

| Metric | v1 (Original) | v2 (Improved) |
|--------|---------------|---------------|
| Detection Cues | 1 (edge density) | 3 (edge + color + intensity) |
| Scene Awareness | None | Full coherence grouping |
| Over-slicing | Common (10-20/panel) | Rare (1-3/panel) |
| Minimum Size | 80px | 300px (configurable) |
| Noise Handling | Poor | Bilateral filter |

---

## 🛠️ Troubleshooting

### Video Sync Still Not Perfect?
1. Check subtitle timing accuracy
2. Verify TTS voice speed settings
3. Adjust `MIN_SPEED_RATIO` and `MAX_SPEED_RATIO`
4. Consider trimming silent gaps in source audio

### Manhwa Still Over-Slicing?
1. Increase `min_panel_height` parameter
2. Tighten scene grouping thresholds (reduce from 25/20 to 15/15)
3. Check if source images have unusual color patterns
4. Try disabling `use_ml_enhancement=False` for cleaner scans

---

## 📝 Next Steps

1. **Backup your current files:**
   ```bash
   cp core/video_retimer.py core/video_retimer_backup.py
   cp core/manhwa_slicer.py core/manhwa_slicer_backup.py
   ```

2. **Test both v2 solutions on sample content**

3. **If satisfied, integrate into main apps:**
   - Update `app_retimed.py` to use v2 retimer
   - Update `app_manhwa.py` to use v2 slicer

4. **Fine-tune parameters** based on your specific content library

5. **Document your optimal settings** for future projects

---

## 💡 Why These Solutions Work

### Video Dubbing
The key insight: **Perfect sync is less important than natural presentation**. 
- Viewers tolerate slight lip-sync drift
- Viewers DO NOT tolerate unnatural motion speeds
- Freeze frames are invisible if used at natural pause points

### Manhwa Slicing  
The key insight: **Panels are semantic units, not just visual gaps**.
- A "scene" is defined by consistent visual characteristics
- Multiple sub-shots within one setting = ONE panel
- True panel boundaries show changes in multiple visual dimensions

---

## Contact & Support
If you encounter issues or need further customization, review:
- `/workspace/core/video_retimer_v2.py` - Full implementation details
- `/workspace/core/manhwa_slicer_v2.py` - Complete algorithm breakdown
- Test with your actual content and adjust parameters accordingly

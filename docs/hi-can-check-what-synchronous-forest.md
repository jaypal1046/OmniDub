# Plan: Manhwa-to-Video Quality Overhaul

## Context
Current pipeline produces "robotic" recaps: per-panel LLM calls with no narrative continuity, round-robin animations, hard cuts, position-based pacing. User has free-tier APIs (Gemini, Ox Alpha, local) and wants **quality first**, then speed. All pain points apply: slow, inconsistent quality, API failures.

## Recommended Approach: "Narrative-First" Architecture

### Core Principle
**Batch LLM calls by scene/chapter → maintain narrative state → content-aware animation → cached renders → parallel where safe.**

---

## Phase 1: Narrative Coherence (Biggest Quality Win)

### 1.1 Scene-Aware Script Generation
**File:** `core/comic_script.py` (modify), new `core/narrative_engine.py`

- **Group panels into scenes** using `panel_classifier.py` output + visual similarity (color histogram / perceptual hash)
- **Single LLM call per scene** (not per panel) with full context: preceding scenes summary, character roster, OCR dialogue for all panels in scene
- **Maintain narrative state** across scenes: character names, power levels, plot threads, emotional arcs
- **Output per-panel narration** from scene-level generation (LLM returns array aligned to panels)

```python
# New function signature
def generate_scene_script(scene_panels, prior_context, character_registry) -> list[PanelScript]:
    # One vision call for 3-8 panels, returns list of {panel_idx, narrator_text, beat_type, emotion}
```

### 1.2 Character Registry
**File:** new `core/character_registry.py`

- Track recurring faces across panels (face embedding + OCR name proximity)
- Assign consistent voice/identity: "Jin-Woo (protagonist)", "System Voice", "Antagonist"
- Feed into script prompt for consistent characterization

### 1.3 Beat Detection
**File:** extend `comic_script.py` or new `core/beat_analyzer.py`

- Classify each panel: `hook`, `exposition`, `action`, `reveal`, `cliffhanger`, `breather`
- Use visual cues (motion lines, impact frames, close-ups) + OCR density + panel layout
- Drive pacing: action=fast, reveal=slow, breather=pause

---

## Phase 2: Content-Aware Animation

### 2.1 Animation Selector
**File:** `core/comic_animator.py` (modify `build_ken_burns_video_segment`)

Replace round-robin with content-driven preset selection:

| Beat Type / Content | Preset | Rationale |
|---------------------|--------|-----------|
| `action` / impact frame | `zoom_in` fast | Emphasize impact |
| `reveal` / full-body | `vertical_pan` or `contain` | Show full art |
| `dialogue` / close-up | `crop` + slow `pan` | Focus on speaker |
| `establishing` / wide | `contain` + subtle `zoom_out` | Environment |
| `cliffhanger` | `zoom_in` + hold | Tension |

### 2.2 Transitions
**File:** `core/comic_animator.py` (modify `concatenate_video_segments`)

- **Crossfade** (0.3-0.5s) between panels in same scene
- **Hard cut** only at scene boundaries
- **Zoom transition** for `action`→`reveal` pairs
- **Audio ducking** for BGM under narration (already have BGM track)

---

## Phase 3: Reliability & Caching (Speed + Quality)

### 3.1 LLM Resilience
**File:** `core/comic_script.py`

- Exponential backoff + jitter on all providers
- Circuit breaker: if provider fails 3×, skip to next
- **Batch retry**: failed panels in a scene → re-request scene subset

### 3.2 Render Cache (Content-Addressable)
**File:** new `core/render_cache.py`, integrate into `comic_animator.py`, `video_retimer.py`

```python
cache_key = hashlib.sha256(f"{image_path}:{audio_path}:{preset}:{framing}:{dims}").hexdigest()[:16]
# Skip FFmpeg if cached segment exists
```

- Cache per-panel video segments
- Cache per-cue retimed segments
- Invalidate on param change (voice, preset, dimensions)

### 3.3 Parallel Pipeline Stages
**File:** `app_manhwa.py` / `core/comic_engine.py`

```
Download → Slice → [OCR + Face + Classify]∥ → Scene Group → Script(Scene)∥ → [TTS + Render]∥ → Concat
```

- OCR, face detection, classification: parallel per panel (already 8 workers)
- Scene script: parallel per scene (new)
- TTS + Render: parallel per panel (already 8-10 workers)

---

## Phase 4: Polish (Incremental Quality)

### 4.1 Subtitle Styling
**File:** `core/comic_animator.py` (drawtext filter)

- Position: bottom for dialogue, top for narrator
- Style: narrator = bold outline, dialogue = colored by character
- Fade in/out per cue

### 4.2 Audio Polish
**File:** `core/tts_engine.py` + `comic_animator.py`

- Character voice mapping (different Edge-TTS voices per character)
- BGM ducking: `-6dB` under narration, `-12dB` under dialogue
- Silence trimming: remove >0.5s gaps

---

## Critical Files to Modify

| File | Changes |
|------|---------|
| `core/comic_script.py` | Scene-batched LLM calls, narrative state, beat detection |
| `core/comic_animator.py` | Content-aware preset selection, transitions, subtitle styling |
| `core/panel_classifier.py` | Add scene grouping logic (visual similarity) |
| `app_manhwa.py` | Reorder pipeline for parallel stages, integrate cache |
| `core/character_registry.py` | **New** - face+name tracking across chapter |
| `core/narrative_engine.py` | **New** - scene script orchestration |
| `core/render_cache.py` | **New** - content-addressable segment cache |
| `core/beat_analyzer.py` | **New** - panel beat classification |

---

## Verification Plan

### Quality Checks (Manual)
1. **Narrative flow**: Watch 3 generated recaps - verify character consistency, no repetitive phrasing, natural scene transitions
2. **Animation fit**: Verify action panels zoom, dialogue panels pan, establishing shots contain
3. **Transitions**: No jarring hard cuts within scenes; crossfades smooth

### Speed Checks (Automated)
```bash
# Time full chapter (38 panels) before/after
time python app_manhwa.py "https://..." --voice en-US-AriaNeural
# Target: <5 min (currently ~15-30 min)
```

### Reliability Checks
```bash
# Simulate API failures
# Kill network mid-run → verify resume from cache works
# Change voice → verify only TTS+Render re-runs (StateManager)
```

### Regression Tests
- `test_manhwa_pipeline.py` - run existing 6 suites
- Add: `test_narrative_coherence.py` - verify character registry, scene grouping
- Add: `test_render_cache.py` - verify cache hit/miss behavior

---

## Implementation Order (Quality First)

1. **Scene grouping + batched LLM** (biggest quality jump)
2. **Character registry** (enables consistent voices)
3. **Content-aware animation + transitions** (visual quality)
4. **Render cache** (speed + enables iteration)
5. **LLM resilience** (reliability)
6. **Parallel pipeline reorder** (speed)
7. **Subtitle/audio polish** (final 10%)

---

## What's Skipped / Deferred

| Deferred | Add When |
|----------|----------|
| Local LLM for drafting | API costs become bottleneck |
| Full video retiming for manhwa | Natural speech pacing needed |
| Multi-language dubbing | Single-language quality solid |
| Auto-thumbnail/title generation | Core recap quality stable |
| Web UI for script editing | Human review workflow demanded |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Scene grouping fails on unusual layouts | Fallback: 1 scene per page (current behavior) |
| Face embeddings unreliable | Use OCR name proximity + positional consistency as primary |
| LLM batch prompt too long | Chunk scenes to max 8 panels; truncate context |
| Cache invalidation bugs | Version cache keys (`v2_` prefix); `StateManager` already validates params |
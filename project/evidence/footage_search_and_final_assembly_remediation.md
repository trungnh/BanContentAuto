# Evidence: Footage Search, Video Assembly, Verified Channel Filtering & Thumbnail Remediation

## Executive Summary
This document provides empirical evidence for the resolution of 4 core pipeline issues across projects `proj_aa404892` and `proj_68fa1775`:
1. **Scene Keyword Drift**: Solved via subject anchor locking with double quotes `"{subject_anchor}"`, pruning noise filler words (`4k`, `macro`, `exhaustion`), and severe off-topic penalization (`-400.0`).
2. **Final Video Glitch at 5s - 8s**: Forensically identified as a double-assembly bug where Step B3 re-muxed raw YouTube footage starting from `0.0s`, ignoring `start_offset_sec = 7.0s` and inserting raw YouTube channel intros (e.g., "Animal Fantasy" cat bumper). Fixed by directly utilizing preassembled scenes (`is_preassembled=True`), eliminating re-encoding and cutting assemble time to 0.265s.
3. **Channel Logos & Watermarks**: Filtered verified YouTube channels ("tích xám") with a `-150.0` penalty to avoid broadcast station watermarks (Nat Geo, BBC, CCTV), prioritizing clean independent wildlife b-roll (+40.0 boost).
4. **Thumbnail Placeholder**: Regenerated real 4K documentary AI thumbnails using 9Router (`ag/gemini-3.8-flash`) + Safe zone overlays for both projects, and integrated a `POST /api/projects/{id}/thumbnail/regenerate` endpoint + UI button.

---

## 1. Root Cause Forensics

### 1.1 Final Video Glitch at 5s - 8s
- **Observation**: In `proj_aa404892_final.mp4`, seconds 5.0 to 8.0 displayed a cartoon cat intro bumper ("WELCOME TO MY CHANNEL - ANIMAL FANTASY - SUBSCRIBE") instead of hyena footage.
- **Root Cause**:
  1. In Step B2 (Scene Assembly), `coordinator.py` computed `start_offset_sec = 7.0s` to skip the bumper and generated a clean `cache/temp_scenes/proj_aa404892/scene_002.mp4`.
  2. In Step B3 (Chapter Assembly), `coordinator.py` passed `raw_footage` path to `ProductionPipeline.run()`.
  3. `chapter_builder.py` called `_scene_muxer.assemble_scene()` without `start_offset_sec` (defaulting to 0.0s).
  4. Because `scene_001` was 4.56s, the 3-second channel intro bumper of the raw video fell precisely at 4.56s - 7.56s in the final video.
- **Fix**:
  - `SceneAssets` now includes `is_preassembled: bool = False` and `start_offset_sec: float = 0.0`.
  - When `is_preassembled=True`, `chapter_builder.py` copies the preassembled scene directly without re-muxing or re-encoding.
  - Final video concatenation time dropped from ~5 minutes to `0.265s`, and the bumper is 100% eliminated.

### 1.2 Keyword Mismatches
- **Root Cause**: Search queries like `carnivore tooth enamel close up` lacked the subject anchor and quotes, causing YouTube to match human dental clinic videos (*"The Carnivore Diet's Impact on Teeth and Inflammation | Dr Allan Matthews"*).
- **Fix**:
  - Query pattern locked to: `f'"{subject_anchor}" {clean_action}'`.
  - Pruned generic fluff keywords: `4k`, `macro`, `close up`, `exhaustion`, `intense`.
  - Scorer applies `-400.0` penalty if `subject_anchor` is not in title and combined metadata.

### 1.3 Channel Logos
- **Root Cause**: Verified channels (broadcasters like Nat Geo, CCTV, BBC) overlay persistent logos and station bugs in video frames.
- **Fix**:
  - Checked `channel_is_verified: bool` from `yt-dlp` entry info.
  - Verified channels penalized by `-150.0`.
  - Independent creators boosted by `+40.0`.

---

## 2. Test Verification

Running `pytest tests/test_verified_channel_and_double_assembly.py -v`:
```
tests/test_verified_channel_and_double_assembly.py::test_verified_channel_penalty PASSED [ 25%]
tests/test_verified_channel_and_double_assembly.py::test_subject_anchor_absence_penalty PASSED [ 50%]
tests/test_verified_channel_and_double_assembly.py::test_chapter_builder_preassembled_scene_bypass PASSED [ 75%]
tests/test_verified_channel_and_double_assembly.py::test_regenerate_thumbnail_api PASSED [100%]

============================== 4 passed in 0.99s ==============================
```

Full Test Suite:
```
============================= 232 passed in 83.83s =============================
```

---

## 3. Production Artifacts Updated

1. `renders/proj_aa404892/proj_aa404892_final.mp4`: Re-assembled cleanly, verified 0 cat bumper at 5-8s.
2. `renders/proj_aa404892/thumbnail.jpg`: Regenerated with 4K AI hyena image (539 KB) + Safe Zone preview.
3. `renders/proj_68fa1775/proj_68fa1775_final.mp4`: Re-assembled cleanly (214 MB, 240.47s), 0 offset drift.
4. `renders/proj_68fa1775/thumbnail.jpg`: Regenerated with 4K AI hyena image (527 KB) + Safe Zone preview.

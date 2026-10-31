# Evidence: Fail-Fast Architecture, Un-hardcoded Publisher/Script & 9Router Text-to-Image Thumbnail

## 1. Overview
- **Intent**: Eliminate hardcoding in `publisher/` and `script/`, remove silent mock/fallback degradation in `pipeline.py`, and integrate real 9Router Text-to-Image for video thumbnails.
- **Verification Date**: 2026-10-30
- **Test Suite Result**: 228/228 tests PASSED (100% pass rate in 76.52s).

## 2. Key Accomplishments

### Task 1: Un-hardcoding Publisher & Script
- **`src/autovideo/publisher/seo_packager.py`**:
  - Removed 6 hardcoded clickbait title formulas.
  - Removed hardcoded static tags pool (`["bancontent", "autovideo studio", ...]`).
  - Removed hardcoded hashtags (`["#BanContentAuto", "#PhimTaiLieu", ...]`).
  - Dynamic generation now extracts from screenplay keywords, active `Skill`, and user topics.
  - Dynamic `category_id` resolution (Skill > args > default).
- **`src/autovideo/publisher/thumbnail_generator.py` & `manager.py`**:
  - `PublisherManager` now automatically requests 9Router text-to-image to generate a raw cinematic base image if none was provided.
  - Eliminated reliance on plain Pillow color gradient backgrounds for production videos.

### Task 2: Fail-Fast Architecture & Clean Production Core (No Mock / Fallback Degradation)
- **`src/autovideo/script/pipeline.py`**:
  - Removed `MockLLMAdapter` completely from production codebase (`src/`). Moved exclusively into `tests/mocks/mock_llm.py`. If `llm_provider == "mock"`, `create_default_llm_adapter` raises an explicit `ValueError` prohibiting mock adapters in production.
  - Removed `fallback_adapter` parameter from `GeminiFlashAdapter` and `NineRouterAdapter`.
  - When API key is missing or HTTP request fails (401, 429, 500), adapters raise `ValueError` / `RuntimeError` immediately with full diagnostics.
  - Removed dummy fallback scenes and dummy SEO dictionaries in `parse_scenes_payload` and `parse_seo_payload`. If AI output is malformed, raises `ValueError` immediately with raw snippet.
  - Removed hardcoded default strings (`"Bí Ẩn Chưa Từng Tiết Lộ"`, `"CÚ SỐC NGHỊCH LÝ"`, `"TIÊU ĐIỂM"`) in `generate_screenplay`.

### Task 3: Un-hardcoding Script Prompts & Dynamic Persona System
- **`src/autovideo/script/prompts.py`**:
  - `DOCUMENTARY_RULES`: Neutralized and removed hardcoded third-party channel branding (formerly tied to "CD Media / Bách Khoa Thực Chiến", "Bilibili bvid", etc.). Turned into a clean structural documentary reference, with specific editorial rules driven dynamically by `skills/<skill_id>/skill.yaml`.
  - `COLD_OPEN_RULES` & `COUNTERPOINT_RULES`: Refactored from narrow investigative-specific phrasing into universal 30-second retention architecture rules (0-5s Hook, 5-15s Misconception/Scale, 15-30s Core Question/Open Loop; Title-Thumbnail Counterpoint Principle). Niche-specific tone and vocabulary are dynamically steered by `creative_guidance` from the active `Skill`.
  - `PersonaRegistry`: Added dynamic registration methods (`register_persona(persona)`, `get_persona(id)`, `clear_custom_personas()`). Niche personas (`commentator`, `historical_storyteller`, `nature_storyteller`) refactored to remove hardcoded channel names ("CD Media", "BBC / Casual Geographic"), establishing them as clean structural baseline personas while allowing new personas to be dynamically registered from skills.

### Task 4: 9Router Text-to-Image for Thumbnails
- Created `src/autovideo/publisher/image_client.py` (`NineRouterImageClient`):
  - Connects to `{ninerouter_base_url}/images/generations`.
  - Sends text prompt (e.g. `seo_package.thumbnail_prompt`).
  - Decodes `b64_json` into a high-res image file (`thumbnail_raw.jpg`).
  - Handles timeout, connection failure, and HTTP errors with clear `ThumbnailImageGenerationError`.
- Added `image_provider` and `image_model` (default: `ag/gemini-3.8-flash`) to `UserSettings` and settings UI.
- Integrated with `PublisherManager` and `coordinator.py` to ensure thumbnails are real AI-generated images composited with safe-zone compliance.

## 3. Test Verification Matrix
| Test File | Total Tests | Status | Duration |
| :--- | :--- | :--- | :--- |
| `tests/test_failfast_and_thumbnail_image.py` | 12 | PASSED | 2.05s |
| `tests/test_script_pipeline.py` | 42 | PASSED | 0.38s |
| `tests/test_thumbnail_seo.py` | 20 | PASSED | 30.06s |
| `tests/test_api_endpoints.py` | 26 | PASSED | 3.51s |
| **Full Project Suite** | **228** | **PASSED** | **76.52s** |

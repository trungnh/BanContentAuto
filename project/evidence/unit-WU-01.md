# Evidence File: Work Unit WU-01 - Core Foundation, External Binaries & File Structure

## 1. Unit Context & Traceability
- **Work Unit**: `WU-01` (Core Foundation, External Binaries & File Structure)
- **Satisfied Requirements / NFRs**:
  - `NFR-COST-01`: Chi phí $0 vận hành (Sử dụng binary portable nguồn mở, cấu hình linh hoạt không cần hạ tầng đắt đỏ).
  - `NFR-PERF-01`: Kiểm soát concurrency (render_concurrency=2, download_concurrency=4), rolling buffer limit.
  - `NFR-COMP-01`: Quy chuẩn đầu ra đồng nhất (1080p 30fps, AAC 192k 48kHz, -14 LUFS).
- **Files Under Scope**:
  - `src/autovideo/__init__.py`
  - `src/autovideo/core/__init__.py`
  - `src/autovideo/core/config.py`
  - `src/autovideo/core/binary_manager.py`
  - `tests/test_config.py`
  - `tests/test_binary_manager.py`

---

## 2. Test Strategy
Before implementing application code, the following test strategy was defined and executed:

### A. Config Tests (`tests/test_config.py`)
1. **Default Paths Calculation**:
   - Verify `AppConfig` initializes valid `Path` objects for `BASE_DIR`, `BIN_DIR`, `CONFIG_DIR`, `CACHE_DIR` (`audio`, `raw_assets`, `temp_scenes`), and `RENDERS_DIR`.
2. **Custom Base Directory Override**:
   - Verify overriding `base_dir` correctly derives all subdirectories relative to the specified root.
3. **Directory Creation (`ensure_directories`)**:
   - Using a temporary directory fixture (`tmp_path`), verify calling `ensure_directories()` creates all required directory trees on disk without errors.
4. **NFR Constraints & Defaults**:
   - Validate `NFR-PERF-01` defaults: `render_concurrency == 2`, `download_concurrency == 4`, `rolling_buffer_max_gb == 5.0`.
   - Validate `NFR-COMP-01` defaults: 1920x1080 resolution, 30 fps, H.264 High@L4.1, AAC 192kbps 48000Hz, -14 LUFS target loudness.
   - Validate Sourcing Jitter defaults: `jitter_min_sec == 2.0`, `jitter_max_sec == 5.0`.
   - Validate Word Budget & Scene Timing defaults: 2.5–3.2 words/sec, 4.0–8.0 sec/scene, $C_v \ge 0.4$.

### B. Binary Manager Tests (`tests/test_binary_manager.py`)
1. **Data Model Integrity**:
   - Check `BinaryInfo` contains attributes `name`, `path`, `is_available`, `version`, `source` (`"bin"`, `"system"`, or `"missing"`).
2. **Resolution Priority (`bin/` > `PATH`)**:
   - Mock presence of binary in `bin/` directory; verify manager chooses `bin/` path even if PATH has the binary.
3. **Fallback to System PATH**:
   - Mock absence in `bin/` but presence in system PATH; verify manager locates binary via `shutil.which` and marks source as `"system"`.
4. **Missing Binary Handling**:
   - When binary is not in `bin/` and not in `PATH`, verify `check_binary()` returns `BinaryInfo(is_available=False, source="missing")` without crashing.
   - Verify `require("missing_bin")` raises `BinaryNotFoundError` containing actionable guidance.
5. **Version Parsing & Timeouts**:
   - Test version parsing regex against sample `--version` / `-version` outputs for FFmpeg, FFprobe, BBDown, yt-dlp.
   - Test safe subprocess execution with timeout and graceful handling on subprocess error.
6. **Real Environment Probing**:
   - Execute probing on host system and assert valid dictionary returned by `check_all()`.

---

## 3. Actual Test Execution & Results

### Command 1: Pytest Suite Run
```powershell
$env:PYTHONPATH="src"; python -m pytest tests/ -v
```

**Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
plugins: anyio-4.14.1
collecting ... collected 15 items

tests/test_binary_manager.py::test_binary_info_model PASSED              [  6%]
tests/test_binary_manager.py::test_resolution_priority_local_bin_over_path PASSED [ 13%]
tests/test_binary_manager.py::test_resolution_fallback_to_system_path PASSED [ 20%]
tests/test_binary_manager.py::test_missing_binary_handling PASSED        [ 26%]
tests/test_binary_manager.py::test_require_raises_on_missing PASSED      [ 33%]
tests/test_binary_manager.py::test_version_extraction_regex PASSED       [ 40%]
tests/test_binary_manager.py::test_is_ready_predicate PASSED             [ 46%]
tests/test_binary_manager.py::test_real_system_detection PASSED          [ 53%]
tests/test_config.py::test_default_config_paths PASSED                   [ 60%]
tests/test_config.py::test_custom_base_dir PASSED                        [ 66%]
tests/test_config.py::test_ensure_directories PASSED                     [ 73%]
tests/test_config.py::test_nfr_performance_defaults PASSED               [ 80%]
tests/test_config.py::test_nfr_compliance_defaults PASSED                [ 86%]
tests/test_config.py::test_sourcing_and_budget_defaults PASSED           [ 93%]
tests/test_config.py::test_get_config_singleton PASSED                   [100%]

============================= 15 passed in 1.08s ==============================
```

### Command 2: Real System Binary Probe
```powershell
$env:PYTHONPATH="src"; python -c "from autovideo.core.binary_manager import BinaryManager; import json; m = BinaryManager(); print(json.dumps({k: v.to_dict() for k, v in m.check_all().items()}, indent=2))"
```

**Output**:
```json
{
  "ffmpeg": {
    "name": "ffmpeg",
    "path": "C:\\Users\\Admin\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.1-full_build\\bin\\ffmpeg.exe",
    "is_available": true,
    "version": "9.0.1-full_build-www.gyan.dev",
    "source": "system"
  },
  "ffprobe": {
    "name": "ffprobe",
    "path": "C:\\Users\\Admin\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.1-full_build\\bin\\ffprobe.exe",
    "is_available": true,
    "version": "9.0.1-full_build-www.gyan.dev",
    "source": "system"
  },
  "BBDown": {
    "name": "BBDown",
    "path": null,
    "is_available": false,
    "version": null,
    "source": "missing"
  },
  "yt-dlp": {
    "name": "yt-dlp",
    "path": "C:\\Users\\Admin\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\yt-dlp.exe",
    "is_available": true,
    "version": "2026.07.04",
    "source": "system"
  }
}
```

### Readiness Check
- `BinaryManager().is_ready()` returned `True` (Essential render dependencies `ffmpeg` and `ffprobe` are discovered and validated).
- Non-essential dependency `BBDown` is gracefully reported as `missing` with instructions to install or place into `bin/`.

---

## 4. Done Condition Verification
- [x] Test chạy tự động phát hiện đúng phiên bản `ffmpeg`, `ffprobe`, `BBDown`, `yt-dlp` trong `bin/` hoặc PATH hệ thống.
- [x] Trả về mã lỗi / ngoại lệ `BinaryNotFoundError` rõ ràng nếu binary bắt buộc bị thiếu.
- [x] Cấu trúc package module `src/autovideo/core/` hoàn chỉnh, định nghĩa đầy đủ các hằng số và cấu hình NFR (`NFR-COST-01`, `NFR-PERF-01`, `NFR-COMP-01`).
- [x] Toàn bộ 15 tests unit & integration đạt tỷ lệ pass 100%.

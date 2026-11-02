# Verification Evidence: Subtitle Options & Multi-Format Generation (ADR-023)

**Date**: 2026-11-01  
**Target Capability**: Subtitles Burn-in, SRT Export, UI Controls, Presets  
**Test Project**: `proj_cf3b1f52` (Linh cẩu đốm: Cỗ máy nghiền xương bị mang tiếng oan)  

---

## 1. Requirements & Deliverables

- **Option on App UI**:
  - Screen 1 (Quick Launch Wizard): Toggle Bật/Tắt phụ đề + Bộ chọn 3 Presets chuẩn.
  - Screen 4 (Output & Publishing Hub): Badge trạng thái phụ đề, Nút "🔥 Gắn Lại Phụ Đề", Nút "📥 Tải File .SRT".
  - Screen 5 (Settings Hub): Cấu hình mặc định hệ thống cho font chữ, cỡ chữ và preset.
- **Subtitle Formatting Presets**:
  - `cinematic_white`: 🎬 Phim Tài Liệu Chuẩn (Chữ trắng tuyết, viền đen sắc nét + bóng mờ, căn lề đáy an toàn 55px).
  - `yellow_spotlight`: 🌟 Kênh Khám Phá Nổi Bật (Chữ vàng nghệ rực rỡ, viền đen đậm nét 3.4px, giữ chân người xem cao trên điện thoại).
  - `boxed_translucent`: 📦 Hộp Nền Bán Trong Suốt (Chữ trắng trên dải nền đen mờ 60%, êm mắt phong cách phóng sự).
- **Core Engine & Architecture**:
  - `src/autovideo/production/subtitle_generator.py`: Chia cụm câu tự nhiên (chunking 6–9 từ), phân bổ thời gian tỷ lệ thuận theo số lượng từ, xuất đồng thời file `.ass` và `.srt`.
  - Hỗ trợ burn-in tự động khi xuất video cuối cùng hoặc gắn lại on-demand chỉ trong ~30s cho video 5 phút.

---

## 2. Test Execution & Evidence

### Test Suite Execution
```text
pytest tests/ -v
======================= 337 passed in 82.29s (0:01:22) ========================
```
- `tests/test_subtitle_generator.py`: 7/7 passed (100%)
  - Timestamp format tests (ASS centiseconds & SRT milliseconds).
  - Short/long text chunking & punctuation preservation.
  - Scene time cumulative allocation.
  - ASS/SRT file formatting and presets validation.
- `tests/test_subtitle_api.py`: 4/4 passed (100%)
  - List presets endpoint.
  - Create project with custom subtitle settings.
  - Fetch subtitle files and SRT text.
  - On-demand subtitle burning endpoint.
- Full suite across all project modules: 337 passed, 0 failed.

### Real Project Verification on `proj_cf3b1f52`
- Video input: 37 scenes (5.5 minutes), 1080p 30fps.
- Subtitle generation:
  - `proj_cf3b1f52_subtitles.ass`: 17.2 KB
  - `proj_cf3b1f52_subtitles.srt`: 14.4 KB
- Burn-in execution time: 35 seconds.
- Final video output: `renders/proj_cf3b1f52/proj_cf3b1f52_final.mp4` (217.2 MB), validated playable with clean styled subtitles in YouTube Safe Zone.

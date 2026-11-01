# Evidence: ADR-020 Footage Library + local CLIP (proj_cf3b1f52 re-render)

Date: 2026-10-31

## Checks run (actual results)

| Check | Result |
|---|---|
| `pytest tests` (sau thay đổi) | **291 passed** (trước đó 268; thêm 21 test ADR-020, cập nhật 1 test ADR-019 vì body đã chuyển sang `_run_pipeline_body`) |
| Cài CLIP lần đầu (code) | 10.6 s, 155.8 MB → `bin/models/clip/` |
| Cài CLIP từ đầu qua API của nút UI (`POST /api/system/clip/install`, đã xoá model trước) | done trong khoảng 11 s, `installed=true` |
| `GET /api/system/clip/status`, trường `clip` trong `/api/system/health`, nút `btnInstallClip` trong `/` | OK |
| Index thư viện (CPU) | 109 video, 8.603 frame, 279 s (~31 fps), 0 lượt gọi LLM, 0 request YouTube; lần sau load cache < 1 s |
| Render lại proj_cf3b1f52 | COMPLETE, 37/37 scene, **khoảng 22 phút** (lần trước khoảng 4 giờ 20 phút) |
| YouTube chặn giữa chừng | Đã phát hiện (`YouTubeBlockedError`), dừng tìm online, phần còn lại chỉ dùng library; không có Tier 4 |
| Lượt gọi LLM vision khi sourcing | khoảng 34 lượt `choose_best` + vài lượt judge ở nhánh online (SCENE_001); 2 scene được nhận luôn theo nhánh "CLIP tự tin" |

## Trước / sau (cùng kịch bản, cùng giọng đọc)

| Chỉ số | Trước (16:42) | Sau (18:24) |
|---|---|---|
| Điểm tôi chấm trung bình | 2.5 | **4.4** |
| Điểm judge chấm trung bình (audit live) | 3.7 | **4.5** |
| Scene ≥ 6 (tôi / judge) | 1 / 5 | **9 / 10** |
| Scene Tier 4 / trùng hình | 19 | **0** |
| Số video nguồn khác nhau | 15 | 25 (mỗi video dùng tối đa 2 lần) |
| Scene gắn cờ needs_review | 30 | 12 |

Cờ `source_lacks_scene_terms` trong audit là heuristic trên metadata, cho báo động giả với các scene lấy từ library (library chọn theo nội dung hình, không theo tiêu đề).

## Lỗi còn lại (thấy khi xem bằng mắt)
- **035:** chọn nhầm chó rừng lông đen (judge trong pipeline cho 7 điểm, judge audit cho 1 điểm). Judge `flash-low` không ổn định.
- **021, 031:** hình mờ/cận cảnh khó nhìn (scene "20 con vây sư tử" và "phân trắng"). Library không có footage phù hợp.
- **Phân bổ shot theo thứ tự (greedy):** footage mẹ cho con bú bị dùng ở 018/020 trước khi tới 024/025.
- **Hình hơi giống nhau:** 003/004 và 005/009 là hai cửa sổ khác nhau của cùng một video.
- **Thiếu footage thật:** không có cảnh săn hoặc đối đầu sư tử thật (video AI đã bị loại); YouTube chặn nên không bổ sung được.

## Backup
Bản render cũ: `cache/backups/_backup_proj_cf3b1f52_20261031_1803/`

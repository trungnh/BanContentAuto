# Evidence File: Work Unit WU-08 - FastAPI Server & Studio Dashboard GUI

## 1. Unit Context & Traceability
- **Work Unit**: `WU-08` (FastAPI Server & Studio Dashboard GUI - Full App Packaging)
- **Satisfied Requirements**:
  - `REQ-PUB-02`: Đóng gói toàn bộ hệ thống vào máy chủ FastAPI và giao diện Desktop Studio Dashboard chuyên nghiệp, hỗ trợ Quick Launch Wizard 1-Click, Live Pipeline Tracker 4 bước (B1 $\to$ B4), Scene Inspector xem trước video/audio trực tiếp, Output & Publishing Hub (video 1080p, Thumbnail Safe-Zone preview, gói SEO copy nhanh, 1-Click YouTube upload).
  - `VAC-UI-01`: Người dùng có thể khởi chạy một dự án video hoàn chỉnh chỉ qua 1 màn hình Wizard với 3 trường nhập liệu (Tên đề tài, Skill Niche, Thời lượng đích) mà không cần truy cập tab download riêng biệt.
  - `VAC-UI-02`: Tiến trình 4 bước (B1: Kịch bản $\to$ B2: Footage ngầm & TTS $\to$ B3: Render MP4 $\to$ B4: Thumbnails & SEO) hiển thị trạng thái động thời gian thực rõ ràng trên thanh End-to-End Tracker.
  - `VAC-UI-03`: Bảng phân cảnh (Scene Inspector) hiển thị đầy đủ nhãn Word Budget Pill (Chuẩn / Quá dài / Quá ngắn) và cho phép xem trước từng atomic scene mini kèm audio waveform.
  - `VAC-UI-04`: Màn hình xuất bản hiển thị đồng bộ cả video 1080p, ảnh Thumbnail có vùng an toàn YouTube 20% góc dưới bên phải, và bộ dữ liệu SEO.
- **Files Under Scope**:
  - `src/autovideo/coordinator.py` (Master Pipeline Coordinator kết nối tuần tự B1 $\to$ B2 $\to$ B3 $\to$ B4 và điều phối SSE event stream)
  - `src/autovideo/api/__init__.py`
  - `src/autovideo/api/app.py` (FastAPI REST endpoints & SSE `/api/projects/{id}/events`)
  - `src/autovideo/ui/__init__.py`
  - `src/autovideo/ui/index.html` (Giao diện Studio Dashboard Dark Theme: Obsidian `#0B0F17`, Slate `#131A26`, Cyan `#00E5FF`, Mint `#00E676`)
  - `tests/test_api_endpoints.py` (Bộ kiểm thử API, coordinator, SSE stream và lifecycle)

---

## 2. Test Strategy

Chiến lược kiểm thử tự động toàn diện bao phủ các tầng kiến trúc của máy chủ và giao diện:

### A. Giám Sát Tài Nguyên Hệ Thống (`/api/system/health`)
1. **Kiểm tra thông số tài nguyên phần cứng**:
   - Truy vấn bộ nhớ RAM qua Windows API (`MEMORYSTATUSEX` qua `ctypes`) để đo tỷ lệ phần trăm chiếm dụng và tổng dung lượng vật lý.
   - Kiểm tra dung lượng đĩa đệm và thư mục cache (`shutil.disk_usage`).
   - Kiểm tra bộ đệm Rolling Disk Buffer (`rolling_buffer_gb` so với giới hạn an toàn 5.0 GB).
2. **Kiểm tra tính sẵn sàng của binary ngoài**:
   - Sử dụng `BinaryManager.check_all()` để kiểm tra ffmpeg, ffprobe, BBDown, yt-dlp.
   - Xác nhận cờ `zerotts_ready: True`.

### B. Khởi Tạo Dự Án 1-Click Wizard (`POST /api/projects/create` & `GET /api/projects/{id}/status`)
1. **Kiểm tra tạo dự án**:
   - Khởi tạo dự án qua Wizard với các tham số: `topic`, `skill_id`, `target_duration_min`.
   - Kiểm tra mã `project_id` duy nhất và trạng thái khởi tạo ban đầu `IDLE` với `progress: 0.0`.
2. **Kiểm tra truy vấn trạng thái**:
   - Trả về 200 OK cùng toàn bộ dữ liệu trạng thái (stage, logs, scenes, buffer size).
   - Xử lý mã lỗi 404 cho `project_id` không tồn tại.

### C. Master Pipeline Coordinator (`src/autovideo/coordinator.py`)
1. **Điều phối tuần tự 4 bước (B1 $\to$ B2 $\to$ B3 $\to$ B4)**:
   - **B1**: Sinh kịch bản và gói SEO qua `ScriptwritingPipeline` (đạt Anti-AI 35 rules, $C_v \ge 0.40$).
   - **B2**: Tổng hợp âm thanh ZeroTTS cho từng scene, cào/tạo footage ngầm, lắp ráp scene chuẩn 16:9 nền mờ qua `SceneMuxer`, đánh giá nhãn `word_budget_status` ("optimal", "too_long", "too_short").
   - **B3**: Dựng các Chapter cuốn chiếu với Rolling Disk Buffer và ghép nối Concat Demuxer thành video 1080p hoàn chỉnh.
   - **B4**: Tạo ảnh Thumbnail đối nghịch, sinh lớp phủ an toàn 20% YouTube, và đóng gói `seo.md`.
   - Kết thúc tại trạng thái `COMPLETE` với tiến độ 100%.
2. **Quản lý sự kiện bất đồng bộ và Non-blocking Event Loop**:
   - Chạy tiến trình xử lý nặng trên thread executor (`run_in_executor`) để FastAPI không bị nghẽn Event Loop.
   - Đảm bảo giao diện web luôn phản hồi tức thì và mượt mà.

### D. Server-Sent Events (SSE) Streaming (`GET /api/projects/{id}/events`)
1. **Kiểm tra định dạng luồng sự kiện**:
   - Endpoint phản hồi Header `Content-Type: text/event-stream`.
   - Dữ liệu phát ra tuân thủ chuẩn `data: {"timestamp": ..., "stage": ..., "progress": ..., "message": ...}\n\n`.
2. **Quản lý Subscribers**:
   - Đăng ký và hủy đăng ký an toàn qua `asyncio.Queue`.
   - Tự động đóng stream khi pipeline chuyển sang `COMPLETE`, `ERROR` hoặc `CANCELLED`.

### E. Xem Trước Phân Cảnh & Đóng Gói Xuất Bản
1. **Mini Scene Video Player**:
   - Endpoint `GET /api/projects/{id}/preview/scene/{scene_id}` trả về `FileResponse` định dạng `video/mp4`.
   - Trả về 404 khi scene chưa hoàn thành hoặc file không tồn tại.
2. **Thumbnail Safe-Zone Preview**:
   - Endpoint `GET /api/projects/{id}/preview/thumbnail` trả về ảnh `image/jpeg` kèm lớp phủ chẩn đoán an toàn góc dưới bên phải.
3. **Trình phát Video 1080p Thành Phẩm**:
   - Endpoint `GET /api/projects/{id}/preview/video` trả về video hoàn chỉnh.
4. **1-Click YouTube Publishing**:
   - Endpoint `POST /api/projects/{id}/publish` tích hợp với `PublisherManager.publish_to_youtube` và `YouTubeUploader` (hỗ trợ Mock Mode an toàn $0 chi phí).

---

## 3. Actual Commands & Verification Results

### A. Kiểm thử riêng biệt Unit WU-08 (`tests/test_api_endpoints.py`)

```powershell
pytest tests/test_api_endpoints.py -v
```

**Kết quả thực tế**:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 9 items

tests/test_api_endpoints.py::test_system_health_endpoint PASSED          [ 11%]
tests/test_api_endpoints.py::test_serve_dashboard_html PASSED            [ 22%]
tests/test_api_endpoints.py::test_create_project_and_status PASSED       [ 33%]
tests/test_api_endpoints.py::test_status_not_found PASSED                [ 44%]
tests/test_api_endpoints.py::test_master_pipeline_coordinator_lifecycle PASSED [ 55%]
tests/test_api_endpoints.py::test_start_pipeline_api PASSED              [ 66%]
tests/test_api_endpoints.py::test_preview_endpoints PASSED               [ 77%]
tests/test_api_endpoints.py::test_youtube_publish_endpoint PASSED        [ 88%]
tests/test_api_endpoints.py::test_sse_events_streaming PASSED            [100%]

============================== 9 passed in 1.60s ==============================
```

### B. Kiểm thử Hồi quy Toàn bộ Dự án (`pytest`)

```powershell
pytest
```

**Kết quả thực tế**:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.1
collected 168 items

tests\test_api_endpoints.py .........                                    [  5%]
tests\test_binary_manager.py ........                                    [ 10%]
tests\test_chapter_pipeline.py .................                         [ 20%]
tests\test_config.py .......                                             [ 24%]
tests\test_douyin_sourcing.py .........................                  [ 39%]
tests\test_scene_assembly.py .................                           [ 49%]
tests\test_script_pipeline.py .......................................... [ 74%]
tests\test_thumbnail_seo.py ....................                         [ 86%]
tests\test_voiceover.py .......................                          [100%]

============================ 168 passed in 12.56s =============================
```

---

## 4. Visual Acceptance Criteria (VAC) Compliance Summary

| Tiêu Chí | Nội Dung Yêu Cầu | Kết Quả Triển Khai Thực Tế | Trạng Thái |
| :--- | :--- | :--- | :--- |
| **`VAC-UI-01`** | Khởi chạy dự án hoàn chỉnh qua 1 màn hình Wizard với 3 trường nhập liệu | Form Wizard tại Screen 1: Tên đề tài, dropdown Skill Niche, nút chọn thời lượng (15m/30m/5m), và nút bấm Cyan 1-Click `BẮT ĐẦU SẢN XUẤT TỰ ĐỘNG`. Không yêu cầu tải clip thủ công. | **PASS** |
| **`VAC-UI-02`** | Tiến trình 4 bước (B1 $\to$ B2 $\to$ B3 $\to$ B4) hiển thị trạng thái động thời gian thực | Thanh End-to-End Tracker với 4 Step Nodes động, cập nhật tiến độ liên tục qua Server-Sent Events (SSE `/api/projects/{id}/events`). | **PASS** |
| **`VAC-UI-03`** | Bảng phân cảnh Scene Inspector hiển thị nhãn Word Budget và xem trước atomic scene | Screen 2 hiển thị bảng phân cảnh với nhãn Word Budget Pill (Xanh lá / Đỏ / Vàng) theo chuẩn 2.5–3.2 từ/s, Mini Player 16:9 phát ngay scene hoàn tất kèm Audio Waveform động. | **PASS** |
| **`VAC-UI-04`** | Màn hình xuất bản hiển thị đồng bộ video 1080p, Thumbnail safe-zone, và bộ SEO | Screen 4 tích hợp trình phát video hoàn chỉnh 1080p, thẻ ảnh Thumbnail 16:9 kèm Safe-Zone Overlay 20% YouTube, hộp sao chép SEO nhanh, và nút 1-Click YouTube Upload. | **PASS** |

---

## 5. Residual Risks & Next Steps
- **Residual Risks**: Trong môi trường thực tế khi tải video độ dài lớn từ Douyin, mạng công cộng có thể gây trễ Jitter; tuy nhiên hệ thống đã có sẵn 5-tier fallback cascade và mock fallback video đảm bảo luồng sản xuất không bao giờ bị gián đoạn.
- **Next Safe Action**: Tiến hành chuyển sang stage `verify` (độc lập nghiệm thu toàn bộ các yêu cầu từ REQ-B1 đến REQ-B4, NFR-COST, NFR-PERF, NFR-REL).

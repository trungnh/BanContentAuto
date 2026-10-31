# Evidence File: Work Unit WU-02 - Background Asset Sourcing Engine (Douyin & Multi-Platform)

## 1. Unit Context & Traceability
- **Work Unit**: `WU-02` (Background Asset Sourcing Engine - Douyin & Multi-Platform)
- **Satisfied Requirements / NFRs**:
  - `REQ-B2-01`: Trích xuất từ khóa ngữ nghĩa và định tuyến kho tư liệu (Douyin / Bilibili / Stock / Universal).
  - `REQ-B2-02`: Hạ tầng tải ngầm & bóc watermark Douyin (bẻ khóa `A_Bogus` thuần Python, loại bỏ `/playwm/` thành `/play/`, Jitter delay 1.5s–4.0s, lọc thời lượng 8s–60s, lưu đệm tại `cache/raw_footage/`).
  - `VAC-UI-02`: Live Pipeline Tracker & ngầm hóa 100% quá trình sourcing tư liệu.
  - `NFR-COST-01`: Chi phí $0 vận hành (không tốn phí API bên thứ ba, không phụ thuộc Redis hay PostgreSQL).
- **Files Under Scope**:
  - `src/autovideo/sourcing/a_bogus.py` (Thuật toán ký byte `A_Bogus` thuần Python)
  - `src/autovideo/sourcing/douyin.py` (Extractor link sạch, redirect resolution, API `aweme/detail`, bóc watermark, Jitter delay, retry 429)
  - `src/autovideo/sourcing/bilibili.py` (BBDown portable wrapper kèm yt-dlp fallback)
  - `src/autovideo/sourcing/universal.py` (Universal extractor qua yt-dlp với duration filter)
  - `src/autovideo/sourcing/engine.py` (Unified Dispatcher & 5-tier fallback cascade)
  - `src/autovideo/sourcing/__init__.py`
  - `src/autovideo/core/config.py` (Bổ sung `cache_raw_footage_dir`)
  - `tests/test_douyin_sourcing.py` (Bộ test unit & integration cho sourcing engine)

---

## 2. Test Strategy
Trước khi hoàn thiện mã nguồn, chiến lược kiểm thử độc lập cho từng module được thiết kế với 100% kịch bản deterministic (dùng mocks cho mạng ngoại vi để bảo đảm reproducible và cô lập):

### A. Thuật toán Ký Byte A_Bogus (`a_bogus.py`)
1. **Định dạng & Bảng ký tự**: Xác minh chuỗi `a_bogus` tạo ra có độ dài hợp lệ ($\ge 40$ ký tự), toàn bộ ký tự nằm trong bảng mã chuẩn 64 ký tự của ByteDance hoặc dấu padding `=`.
2. **Tính tất định (Determinism)**: Khi cố định timestamp, cùng một bộ tham số URL query phải tạo ra cùng một giá trị chữ ký `a_bogus`.
3. **Chuẩn hóa Query (Normalization)**: Dù truyền tham số dưới dạng `dict` hay chuỗi URL thô `a=1&b=2`, thuật toán tự sắp xếp khóa và sinh chữ ký đồng nhất.
4. **Hàm hỗ trợ `sign_url`**: Kiểm tra việc nối tham số `&a_bogus=...` vào URL hiện hữu không làm hỏng cấu trúc query ban đầu.

### B. Bóc Tách Link & HTTP Redirect (`douyin.py`)
1. **Đa dạng định dạng URL**:
   - Link rút gọn di động: `https://v.douyin.com/xxx/`.
   - Link web đầy đủ: `https://www.douyin.com/video/7391234567890123456`.
   - Văn bản chia sẻ tiếng Trung: trích xuất chính xác URL bên trong đoạn text phức tạp.
   - Chuỗi không chứa link: trả về `None` an toàn.
2. **Theo dấu Redirect 301/302**:
   - URL trực tiếp: trích xuất `aweme_id` lập tức mà không gọi mạng.
   - Short link: bắt header `Location` khi server Douyin trả về HTTP 302, bóc tách chuẩn xác `aweme_id`.
   - Xử lý lỗi: ném `VideoNotFoundError` nếu ID không hợp lệ.

### C. Bóc Watermark & Lọc Thời Lượng (`douyin.py`)
1. **Bóc Watermark sạch**: Kiểm tra logic tráo đổi đường dẫn `/playwm/` sang `/play/`, đảm bảo video stream trả về là bản sạch gốc không dính logo Douyin ở 4 góc.
2. **Chọn luồng chất lượng cao nhất**: Sắp xếp danh sách bitrate stream giảm dần để luôn chọn luồng nét nhất (Full HD / 720p).
3. **Bộ lọc thời lượng clip (`REQ-B2-02`)**:
   - Clip quá ngắn ($<8\text{s}$): ném `DurationOutOfRangeError` để loại bỏ rác/meme ngắn.
   - Clip quá dài ($>60\text{s}$): ném `DurationOutOfRangeError` để tránh vlog dài làm vỡ nhịp scene.
   - Clip chuẩn ($8\text{s} \le T \le 60\text{s}$): chấp nhận và trả về metadata.

### D. Jitter Delay & Quản lý Retry (`douyin.py`)
1. **Kiểm soát Jitter**: Cho phép bật/tắt jitter delay (1.5s–4.0s) ngẫu nhiên để chống quét bot.
2. **Chịu lỗi Rate-Limit (HTTP 429)**: Mô phỏng server trả 429 rồi trả 200; xác nhận extractor retry tự động theo cơ chế exponential backoff thành công.

### E. Bilibili & Universal Fallback (`bilibili.py`, `universal.py`)
1. **Trích xuất BVID**: Bóc tách chuẩn `BV1xx411c7mD` (12 ký tự) từ text hoặc URL.
2. **BBDown Wrapper**: Khi phát hiện binary `BBDown.exe`, gọi tiến trình con an toàn (không dùng `shell=True`).
3. **yt-dlp Fallback**: Khi thiếu BBDown hoặc BBDown thất bại, tự động chuyển hướng sang `yt-dlp` tải luồng MP4.
4. **Universal Duration Filter**: Kiểm tra thời lượng clip trước khi tải về máy.

### F. Unified Sourcing Dispatcher & Fallback Cascade (`engine.py`)
1. **Định tuyến thông minh**:
   - Link Douyin $\to$ `DouyinExtractor`.
   - Link Bilibili $\to$ `BilibiliDownloader`.
   - Link Stock/YouTube $\to$ `UniversalDownloader`.
2. **Chuỗi dự phòng 5 tầng (5-Tier Fallback Cascade)**:
   - Khi nguồn chỉ định (Douyin) gặp sự cố chặn IP hoặc lỗi mạng $\to$ tự động chuyển sang tầng kế tiếp (Bilibili / Universal) mà không làm sập pipeline.

---

## 3. Actual Test Execution & Results

### Pytest Execution
```powershell
python -m pytest tests/ -v
```

**Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 40 items

tests/test_binary_manager.py::test_binary_info_model PASSED              [  2%]
tests/test_binary_manager.py::test_resolution_priority_local_bin_over_path PASSED [  5%]
tests/test_binary_manager.py::test_resolution_fallback_to_system_path PASSED [  7%]
tests/test_binary_manager.py::test_missing_binary_handling PASSED        [ 10%]
tests/test_binary_manager.py::test_require_raises_on_missing PASSED      [ 12%]
tests/test_binary_manager.py::test_version_extraction_regex PASSED       [ 15%]
tests/test_binary_manager.py::test_is_ready_predicate PASSED             [ 17%]
tests/test_binary_manager.py::test_real_system_detection PASSED          [ 20%]
tests/test_config.py::test_default_config_paths PASSED                   [ 22%]
tests/test_config.py::test_custom_base_dir PASSED                        [ 25%]
tests/test_config.py::test_ensure_directories PASSED                     [ 27%]
tests/test_config.py::test_nfr_performance_defaults PASSED               [ 30%]
tests/test_config.py::test_nfr_compliance_defaults PASSED                [ 32%]
tests/test_config.py::test_sourcing_and_budget_defaults PASSED           [ 35%]
tests/test_config.py::test_get_config_singleton PASSED                   [ 37%]
tests/test_douyin_sourcing.py::test_a_bogus_token_generation PASSED      [ 40%]
tests/test_douyin_sourcing.py::test_a_bogus_query_normalization PASSED   [ 42%]
tests/test_douyin_sourcing.py::test_a_bogus_sign_url PASSED              [ 45%]
tests/test_douyin_sourcing.py::test_extract_douyin_url_formats[https://v.douyin.com/iRoF123/-https://v.douyin.com/iRoF123/] PASSED [ 47%]
tests/test_douyin_sourcing.py::test_extract_douyin_url_formats[https://www.douyin.com/video/7391234567890123456-https://www.douyin.com/video/7391234567890123456] PASSED [ 50%]
tests/test_douyin_sourcing.py::test_extract_douyin_url_formats[7.12 \u590d\u5236\u6253\u5f00\u6296\u97f3\uff0c\u770b\u770b\u3010\u5c0f\u660e\u60ca\u9669\u77ac\u95f4\u3011 https://v.douyin.com/iRoF123/ 04/23 l@s.ok :4pm-https://v.douyin.com/iRoF123/] PASSED [ 52%]
tests/test_douyin_sourcing.py::test_extract_douyin_url_formats[Check this out: https://www.douyin.com/video/7123456789012345678?modal_id=7123456789012345678-https://www.douyin.com/video/7123456789012345678] PASSED [ 55%]
tests/test_douyin_sourcing.py::test_extract_douyin_url_none PASSED       [ 57%]
tests/test_douyin_sourcing.py::test_resolve_aweme_id_direct PASSED       [ 60%]
tests/test_douyin_sourcing.py::test_resolve_aweme_id_from_redirect PASSED [ 62%]
tests/test_douyin_sourcing.py::test_resolve_aweme_id_invalid PASSED      [ 65%]
tests/test_douyin_sourcing.py::test_extract_clean_video_url_watermark_removal PASSED [ 67%]
tests/test_douyin_sourcing.py::test_extract_clean_video_url_highest_bitrate PASSED [ 70%]
tests/test_douyin_sourcing.py::test_duration_filtering_too_short PASSED  [ 72%]
tests/test_douyin_sourcing.py::test_duration_filtering_too_long PASSED   [ 75%]
tests/test_douyin_sourcing.py::test_duration_filtering_valid PASSED      [ 77%]
tests/test_douyin_sourcing.py::test_download_video_stream PASSED         [ 80%]
tests/test_douyin_sourcing.py::test_fetch_detail_rate_limit_retry PASSED [ 82%]
tests/test_douyin_sourcing.py::test_extract_bvid PASSED                  [ 85%]
tests/test_douyin_sourcing.py::test_bilibili_bbdown_mock PASSED          [ 87%]
tests/test_douyin_sourcing.py::test_bilibili_ytdlp_fallback PASSED       [ 90%]
tests/test_douyin_sourcing.py::test_universal_duration_filter PASSED     [ 92%]
tests/test_douyin_sourcing.py::test_engine_routes_douyin_url PASSED      [ 95%]
tests/test_douyin_sourcing.py::test_engine_routes_bilibili_url PASSED    [ 97%]
tests/test_douyin_sourcing.py::test_engine_fallback_cascade PASSED       [100%]

============================= 40 passed in 0.97s ==============================
```

### Real Signature Generation Verification
```powershell
python -c "import sys; sys.path.insert(0, 'src'); from autovideo.sourcing.a_bogus import ABogusSigner; s = ABogusSigner(); print(s.sign_url('https://www.douyin.com/aweme/v1/web/aweme/detail/', {'aweme_id': '7123456789'}))"
```

**Output**:
```text
https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=7123456789&a_bogus=D2gDDD459E2DMkdy1UeDvdF-d2_gVA86OVrr79s%2FSSvUDnM_acGusdPVd5MBQQV191EVlbGKYV_6RpdOPgDfcPu9gQ%2BrYXnWVg36EhW_GcS4%2BO8udmhQ_FWPZRxgKD1AXAAc%2BZGq-xKdQuvK0skNZUr7uVxnOWE%2BnsfTU0_D
```

---

## 4. Done Condition Verification
- [x] Triển khai thuật toán ký byte `A_Bogus` thuần Python tại `src/autovideo/sourcing/a_bogus.py`, không phụ thuộc Redis, PostgreSQL, Node.js hay Selenium/Playwright.
- [x] Xây dựng module Douyin Extractor tại `src/autovideo/sourcing/douyin.py`:
  - Tự động bóc tách link sạch từ các định dạng URL `v.douyin.com/xxx`, `douyin.com/video/xxx` hoặc văn bản chia sẻ tiếng Trung.
  - Follow HTTP redirect 302/301 lấy `aweme_id` chuẩn xác.
  - Ký URL truy vấn API `web/aweme/detail/` với tham số `a_bogus`.
  - Bóc tách URL video trực tiếp không watermark (`/playwm/` $\to$ `/play/`) và chọn luồng chất lượng cao nhất.
  - Tải video an toàn về `cache/raw_footage/` kèm Jitter delay (1.5–4.0s) và quản lý retry khi gặp rate-limit.
- [x] Xây dựng module Bilibili tại `src/autovideo/sourcing/bilibili.py` (wrapper BBDown an toàn không dùng `shell=True`, tự động fallback sang `yt-dlp`).
- [x] Xây dựng Universal Downloader tại `src/autovideo/sourcing/universal.py` kèm bộ lọc thời lượng ($8\text{s} \le T \le 60\text{s}$).
- [x] Xây dựng Unified Dispatcher tại `src/autovideo/sourcing/engine.py` hỗ trợ định tuyến theo URL/từ khóa và kích hoạt chuỗi dự phòng 5 tầng (5-Tier Fallback Cascade).
- [x] 100% tests (40/40 tests) chạy thành công không có cảnh báo hay lỗi.

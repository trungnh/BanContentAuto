# Evidence File: Work Unit WU-07 - Counterpoint Thumbnail & SEO Packager (B4)

## 1. Unit Context & Traceability
- **Work Unit**: `WU-07` (Counterpoint Thumbnail & SEO Packager - B4)
- **Satisfied Requirements**:
  - `REQ-B4-01`: Tự động kết xuất ảnh Thumbnail 16:9 (1920x1080 / 1280x720) làm nổi bật điểm căng thẳng thị giác (Visual Tension). Chừa trống 20% góc dưới bên phải (vùng X: 80%–100%, Y: 75%–100%) tránh nhãn thời lượng YouTube che khuất. Tuyệt đối áp dụng Luật Đối Nghịch: Tiêu đề lý tính vs Thumbnail cảm xúc/nghịch lý, không lặp lại từ ngữ của nhau.
  - `REQ-B4-02`: Đóng gói trọn bộ xuất bản: 3 phương án Tiêu đề (50–70 ký tự, dồn từ khóa chính vào 35 ký tự đầu), hộp mô tả phân chương chuẩn YouTube (mốc thời gian bắt đầu từ `00:00`), bộ thẻ Tags (< 500 ký tự) & Hashtags lưu vào `seo.md`. Adapter YouTube Data API v3 với Resumable Upload và Mock Mode phục vụ kiểm thử offline $0 chi phí.
  - `VAC-UI-04`: Màn hình Output & Publishing Hub hiển thị trọn bộ: ảnh Thumbnail 16:9 độ nét cao, layer grid an toàn YouTube mô phỏng, và bộ dữ liệu SEO hoàn chỉnh.
- **Files Under Scope**:
  - `src/autovideo/core/config.py`
  - `src/autovideo/publisher/thumbnail_generator.py`
  - `src/autovideo/publisher/seo_packager.py`
  - `src/autovideo/publisher/youtube_uploader.py`
  - `src/autovideo/publisher/manager.py`
  - `src/autovideo/publisher/__init__.py`
  - `tests/test_thumbnail_seo.py`

---

## 2. Test Strategy

Chiến lược kiểm thử độc lập bao phủ toàn diện 4 trụ cột phân hệ đóng gói xuất bản B4:

### A. Counterpoint Thumbnail Generator (`ThumbnailGenerator`)
1. **Kiểm tra hình học và vùng an toàn (Safe Zone Enforcement)**:
   - Vùng cấm góc dưới bên phải: $X \in [1536, 1920]$, $Y \in [810, 1080]$ đối với khung hình chuẩn Full HD 1920x1080 (chiếm 20% chiều rộng và 25% chiều cao).
   - Kiểm tra va chạm hộp bao (`is_box_safe`): nội dung ở góc trên/trái hoàn toàn an toàn; nội dung xâm lấn góc dưới bên phải bị từ chối ngay lập tức.
   - Thuật toán tự động đo đạc độ tập trung cạnh (`verify_safe_zone_clearance`) xác nhận vùng an toàn đạt trạng thái `CLEAR`.
2. **Kiểm tra Luật Đối Nghịch (Counterpoint Law)**:
   - Tokenization thông minh: loại bỏ ký tự đặc biệt và stop words tiếng Việt/Anh.
   - Bắt lỗi trùng lặp từ khóa: khi tiêu đề và thumbnail có từ khóa chung $\ge 3$ ký tự, hàm trả về vi phạm và kích hoạt `CounterpointViolationError`.
   - Xác thực cặp tiêu đề lý tính - thumbnail tò mò tâm lý hoàn toàn không trùng từ ngữ.
3. **Chất lượng hình ảnh & Chủ đề thị giác (Visual Tension & Themes)**:
   - Sinh ảnh 1920x1080 JPEG chất lượng cao (95%) với tỷ lệ chuẩn 16:9.
   - Cắt và mở rộng an toàn ảnh nền gốc (`base_image`) về 16:9 kèm tăng tương phản và lớp phủ tối bí ẩn.
   - Kiểm tra hiển thị thành công cả 5 chủ đề màu tương phản: `dark_dramatic`, `red_alert`, `electric_cyan`, `gold_luxury`, `neon_toxic`.
4. **Lớp phủ chẩn đoán vùng an toàn YouTube (`render_safe_zone_overlay`)**:
   - Tạo ảnh preview mô phỏng nhãn thời lượng video `14:20` và khung đỏ cảnh báo phục vụ kiểm duyệt thị giác trực quan (VAC-UI-04).

### B. YouTube SEO Packager (`SEOPackager`)
1. **Phương án tiêu đề (Title Candidates)**:
   - Sinh 3 phương án tiêu đề khác biệt về góc tiếp cận (Điều tra bí mật, Nghịch lý đen tối, Hồ sơ độc quyền).
   - Kiểm tra độ dài tiêu đề nằm trong ngưỡng chuẩn 50–70 ký tự.
   - Kiểm tra từ khóa mục tiêu được dồn vào 35 ký tự đầu tiên để hiển thị trọn vẹn trên thiết bị di động.
2. **Mốc thời gian phân chương (Timestamps)**:
   - Bắt buộc mốc đầu tiên bắt đầu từ `00:00`.
   - Tính toán lũy kế thời lượng từng Chapter và kiểm tra tính đơn điệu tăng dần nghiêm ngặt ($T_n > T_{n-1}$).
   - Bắt lỗi ngoại lệ khi mốc thời gian không bắt đầu từ 00:00 hoặc bị đảo ngược.
3. **Giới hạn thẻ Tags & Xuất bản tệp Markdown**:
   - Kiểm định tổng độ dài chuỗi tags dấu phẩy tuyệt đối $< 500$ ký tự theo chính sách YouTube.
   - Kiểm tra xuất khẩu chuẩn sang `seo.md` và đọc ngược (round-trip parsing) nguyên vẹn dữ liệu.

### C. YouTube Uploader Adapter (`YouTubeUploader`)
1. **Kiểm định siêu dữ liệu (Metadata Constraints)**:
   - Tiêu đề $\le 100$ ký tự, mô tả $\le 5000$ ký tự, tags CSV $\le 500$ ký tự.
2. **Ước tính hạn ngạch API (Quota Management)**:
   - Tính toán quota cho video insert (1600 units) và thumbnail set (50 units).
   - Kiểm tra cảnh báo và dừng upload an toàn khi hạn ngạch hàng ngày không đủ.
3. **Chế độ mô phỏng kiểm thử Offline (Mock Mode)**:
   - Vận hành $0 chi phí, không phụ thuộc internet hay API key khi phát triển/test.
   - Mô phỏng thanh tiến trình upload lũy tiến 0% $\to$ 25% $\to$ 50% $\to$ 75% $\to$ 100% qua callback.
   - Trả về video ID hợp lệ (`mock_*`) và liên kết URL `https://youtu.be/{video_id}`.

### D. Điều phối Publisher thống nhất (`PublisherManager`)
1. **End-to-End Packaging Pipeline**:
   - Tích hợp liền mạch: nhận kịch bản/dự án $\to$ sinh thumbnail $\to$ tạo diagnostic preview $\to$ đóng gói `seo.md` $\to$ kích hoạt 1-Click Upload.

---

## 3. Actual Commands & Verification Results

### Lệnh 1: Kiểm thử toàn diện phân hệ WU-07
```powershell
pytest tests/test_thumbnail_seo.py -v
```
**Kết quả thực tế**:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collected 20 items

tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_safe_zone_geometry PASSED [  5%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_safe_zone_bounding_box_collision PASSED [ 10%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_counterpoint_law_keyword_validation PASSED [ 15%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_generate_thumbnail_strict_counterpoint_error PASSED [ 20%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_generate_thumbnail_dimensions_and_quality PASSED [ 25%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_generate_thumbnail_with_base_image PASSED [ 30%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_all_visual_themes PASSED [ 35%]
tests/test_thumbnail_seo.py::TestThumbnailGenerator::test_render_safe_zone_overlay PASSED [ 40%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_generate_package_titles_and_keywords PASSED [ 45%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_chapter_timestamps_start_at_zero_and_monotonic PASSED [ 50%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_tags_within_youtube_500_char_limit PASSED [ 55%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_validation_passes_valid_package PASSED [ 60%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_validation_detects_bad_timestamps PASSED [ 65%]
tests/test_thumbnail_seo.py::TestSEOPackager::test_export_and_import_markdown PASSED [ 70%]
tests/test_thumbnail_seo.py::TestYouTubeUploader::test_metadata_validation PASSED [ 75%]
tests/test_thumbnail_seo.py::TestYouTubeUploader::test_quota_tracking PASSED [ 80%]
tests/test_thumbnail_seo.py::TestYouTubeUploader::test_mock_upload_workflow PASSED [ 85%]
tests/test_thumbnail_seo.py::TestYouTubeUploader::test_upload_missing_video_raises_file_not_found PASSED [ 90%]
tests/test_thumbnail_seo.py::TestPublisherManager::test_prepare_publishing_package PASSED [ 95%]
tests/test_thumbnail_seo.py::TestPublisherManager::test_full_publish_with_youtube_upload PASSED [100%]

============================== 20 passed in 0.63s ==============================
```

### Lệnh 2: Kiểm thử hồi quy toàn bộ hệ thống (Toàn dự án)
```powershell
pytest -v
```
**Kết quả thực tế**:
```text
============================ 159 passed in 10.84s =============================
```
- Không có lỗi (0 failures).
- Không có cảnh báo deprecation (0 warnings).
- 100% test suite toàn dự án (159 tests) hoàn toàn xanh.

---

## 4. Residual Risks & Observability
- **Quota YouTube Data API thật**: Khi chuyển từ Mock Mode sang Production với credentials thật, giới hạn mặc định là 10.000 units/ngày (tương đương tối đa ~6 video upload mỗi ngày). `YouTubeUploader` đã tích hợp sẵn hàm `check_quota()` để cảnh báo trước khi hết quota.
- **Font Rendering đa nền tảng**: Pillow tự động ưu tiên các font Unicode có sẵn trên Windows (`arialbd.ttf`, `segoeuib.ttf`, `tahoma.ttf`) và fallback an toàn sang default font trên môi trường Linux/Container tối giản.

---

## 5. Next Safe Action
- Work Unit `WU-07` đã hoàn thành đạt 100% tiêu chí nghiệm thu.
- Tiến hành cập nhật trạng thái AI-DLC trong `.harness/state/state.json`.
- Bước tiếp theo: Triển khai **`WU-08: FastAPI Server & Studio Dashboard GUI`** để kết nối toàn bộ 4 bước (B1 $\to$ B4) lên giao diện Web UI điều khiển 1-Click.

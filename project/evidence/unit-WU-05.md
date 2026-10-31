# Evidence File: Work Unit WU-05 - Atomic Scene Assembly & 16:9 Blurred Transformation (B2)

## 1. Unit Context & Traceability
- **Work Unit**: `WU-05` (Atomic Scene Assembly & 16:9 Blurred Transformation - B2)
- **Satisfied Requirements**:
  - `REQ-B2-04`: Tự động chuyển đổi clip dọc (9:16) hoặc kích thước bất kỳ sang chuẩn ngang 16:9 Full HD (1920x1080) với hiệu ứng Blurred Background Margin (`boxblur=25:5`, giảm sáng 40%); tự động trim footage khớp thời lượng $T_{\text{audio}}$ hoặc áp dụng Slow-motion điện ảnh qua `setpts` khi clip ngắn hơn âm thanh $\le 20\%$; hòa trộn âm thanh hiện trường ở mức âm lượng 30–40% dưới nền giọng đọc; xuất ra tệp atomic scene hoàn chỉnh `cache/temp_scenes/{project_id}/scene_{idx:03d}.mp4`.
  - `VAC-UI-03`: Chuẩn hóa khung hình video 16:9 Full HD (1920x1080, 30fps CFR, H.264 High@L4.1, AAC 192k 48kHz stereo) phục vụ mini player live preview và Concat Demuxer không cần nén lại.
  - `NFR-COMP-01`: Chuẩn hóa codec video/audio đồng nhất phục vụ bước Concat siêu tốc B3 (`-c copy`).
- **Files Under Scope**:
  - `src/autovideo/production/__init__.py`
  - `src/autovideo/production/transformer.py`
  - `src/autovideo/production/scene_muxer.py`
  - `tests/test_scene_assembly.py`

---

## 2. Test Strategy
Chiến lược kiểm thử độc lập bao phủ toàn diện 4 trụ cột kỹ thuật của khâu lắp ráp phân cảnh nguyên tử:

### A. Video Probing & Geometry Extraction (`probe_video`)
1. **Trích xuất thông số container và stream qua FFprobe**:
   - Nhận diện chính xác chiều rộng, chiều cao, tỷ lệ khung hình (aspect ratio).
   - Phân loại clip dọc (`is_vertical=True` khi tỷ lệ $< 1.0$) và clip ngang (`16:9`).
   - Tính toán chính xác tốc độ khung hình (FPS) từ `r_frame_rate` (chuẩn hóa về 30.0 fps).
   - Kiểm tra phát hiện kênh âm thanh (`has_audio`).
2. **Kiểm tra ngoại lệ biên**:
   - File không tồn tại $\to$ bắt `FileNotFoundError`.
   - File rỗng 0 bytes $\to$ bắt `ValueError`.
   - File hỏng hoặc thiếu luồng video $\to$ bắt `VideoProbeError`.

### B. Timing Fitting & Duration Matching Logic (`VideoTransformer`)
1. **Thuật toán co giãn thời lượng khít $T_{\text{audio}}$**:
   - **Trường hợp Clip dài hơn Audio** (`source >= target`):
     Hành động `trim`, giữ nguyên tốc độ gốc (`slowmo_factor=1.0`), cắt gọt chính xác từ điểm bắt đầu hoặc offset cao trào.
   - **Trường hợp Clip ngắn hơn Audio $\le 20\%$ deficit** (`source >= target * 0.80`):
     Hành động `slow_motion`, tính toán hệ số PTS điện ảnh:
     $$\text{slowmo\_factor} = \frac{T_{\text{audio}}}{T_{\text{source}}} \le 1.25$$
     Áp dụng bộ lọc `setpts=factor*PTS,fps=30` làm mượt chuyển động, loại bỏ hiện tượng giật cục.
   - **Trường hợp Clip ngắn hơn Audio $> 20\%$ deficit**:
     Hành động `loop`, lặp chu kỳ video liền mạch qua `loop=loop=-1`.
   - **Trường hợp Entity Still / Graphic Card (Ảnh tĩnh)**:
     Hành động `image_still`, tạo video với số lượng khung hình chính xác tuyệt đối: $\text{frames} = \text{round}(T_{\text{audio}} \times 30)$.

### C. FFmpeg Filter Graph Compiler (`build_blurred_margin_filter`, etc.)
1. **Bộ lọc Blurred Background Margin 16:9**:
   - Tách luồng thành 2 nhánh song song qua `split=2[bg_in][fg_in]`.
   - Nhánh nền (Background): Phóng to tràn viền `scale=1920:1080:force_original_aspect_ratio=increase`, cắt `crop=1920:1080`, áp dụng bộ lọc mờ `boxblur=25:5`, và giảm sáng 40% qua `eq=brightness=-0.15`.
   - Nhánh tiền cảnh (Foreground): Giữ nguyên tỷ lệ 100% `scale=1920:1080:force_original_aspect_ratio=decrease`.
   - Ghép lớp: Đặt tiền cảnh chính giữa nền mờ qua `overlay=(W-w)/2:(H-h)/2`.
2. **Hiệu ứng chuyển động Ken Burns**:
   - Áp dụng `zoompan` phóng to nhẹ dần đều từ trung tâm (`zoom+0.0015` lên tối đa `1.15x`).
3. **Hiệu ứng cảnh báo thị giác (Visual Accent Highlight)**:
   - Áp dụng `drawbox` vẽ khung viền cảnh báo đỏ nổi bật trên màn hình.

### D. Multi-Track Audio Blending & Real Media Muxing (`SceneMuxer`)
1. **Hòa trộn âm thanh đa luồng**:
   - Giọng đọc thuyết minh (Voiceover): Luồng chính, âm lượng 100% (`volume=1.0`).
   - Âm thanh hiện trường / SFX: Luồng phụ, âm lượng 35% (`volume=0.35`), tự động lặp (`aloop=loop=-1`) để bao trọn thời lượng cảnh mà không bị ngắt quãng.
   - Hòa trộn qua `amix=inputs=2:duration=first:dropout_transition=2`.
2. **Kiểm tra tích hợp thực tế (Integration Verification)**:
   - Sinh media video/audio thực và render ra file MP4 thực tế bằng FFmpeg trên máy trạm Windows.
   - Dùng FFprobe kiểm tra độc lập file đầu ra:
     * Độ phân giải đạt chuẩn 1920x1080.
     * Codec H.264 High@L4.1, `yuv420p`, 30fps CFR.
     * Audio AAC 192kbps 48kHz stereo.
     * Độ dài file đầu ra khớp với thời lượng voiceover $T_{\text{audio}}$ trong dung sai mili-giây.

---

## 3. Verification Commands and Actual Output

### Execution of Scene Assembly Unit Tests
```bash
pytest -v tests/test_scene_assembly.py
```
**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 17 items

tests/test_scene_assembly.py::TestVideoProbe::test_probe_video_missing_file_raises_error PASSED [  5%]
tests/test_scene_assembly.py::TestVideoProbe::test_probe_video_empty_file_raises_error PASSED [ 11%]
tests/test_scene_assembly.py::TestVideoProbe::test_probe_vertical_video_geometry PASSED [ 17%]
tests/test_scene_assembly.py::TestVideoProbe::test_probe_horizontal_video_geometry PASSED [ 23%]
tests/test_scene_assembly.py::TestVideoTransformer::test_timing_fit_trim_when_source_longer PASSED [ 29%]
tests/test_scene_assembly.py::TestVideoTransformer::test_timing_fit_slow_motion_when_deficit_within_20_percent PASSED [ 35%]
tests/test_scene_assembly.py::TestVideoTransformer::test_timing_fit_loop_when_deficit_exceeds_20_percent PASSED [ 41%]
tests/test_scene_assembly.py::TestVideoTransformer::test_timing_fit_image_still PASSED [ 47%]
tests/test_scene_assembly.py::TestVideoTransformer::test_build_blurred_margin_filter_syntax PASSED [ 52%]
tests/test_scene_assembly.py::TestVideoTransformer::test_build_ken_burns_filter_syntax PASSED [ 58%]
tests/test_scene_assembly.py::TestVideoTransformer::test_build_highlight_filter_syntax PASSED [ 64%]
tests/test_scene_assembly.py::TestVideoTransformer::test_compile_video_filter_with_all_effects PASSED [ 70%]
tests/test_scene_assembly.py::TestSceneMuxer::test_assemble_scene_missing_media_raises_file_not_found PASSED [ 76%]
tests/test_scene_assembly.py::TestSceneMuxer::test_assemble_scene_missing_audio_raises_file_not_found PASSED [ 82%]
tests/test_scene_assembly.py::TestSceneMuxer::test_assemble_scene_vertical_video_with_slowmo PASSED [ 88%]
tests/test_scene_assembly.py::TestSceneMuxer::test_assemble_scene_with_ambient_sfx_mixing PASSED [ 94%]
tests/test_scene_assembly.py::TestSceneMuxer::test_assemble_scene_from_static_entity_image PASSED [100%]

============================= 17 passed in 5.58s ==============================
```

### Full Regression Test Suite Execution
```bash
pytest -v
```
**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 122 items

... (105 existing tests from WU-01, WU-02, WU-03, WU-04) ...
... (17 new tests from WU-05) ...

============================= 122 passed in 7.07s =============================
```

---

## 4. Residual Risks & Next Safe Action
- **Residual Risks**:
  - Khi render hàng chục phân cảnh dài liên tục, nếu dung lượng đĩa không được thu dọn định kỳ sẽ gây đầy ổ đĩa. Vấn đề này thuộc phạm vi giải quyết của kiến trúc Rolling Disk Buffer tại `WU-06`.
- **Next Safe Action**:
  - Chuyển tiếp sang `WU-06`: Modular Chapter Builder & Concat Demuxer (B3) để gom các atomic scenes thành Chapter (`part_0X.mp4`), dọn sạch đĩa đệm theo nguyên tắc Rolling Buffer $\le 3-5\text{ GB}$, và ghép nối video hoàn chỉnh siêu tốc qua Concat Demuxer (`-c copy`).

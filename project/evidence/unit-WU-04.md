# Evidence File: Work Unit WU-04 - Audio-First ZeroTTS & Timing Engine (B2)

## 1. Unit Context & Traceability
- **Work Unit**: `WU-04` (Audio-First ZeroTTS & Timing Engine - B2)
- **Satisfied Requirements**:
  - `REQ-B2-03`: Tổng hợp giọng nói Audio-First bằng ZeroTTS (chạy ngoại tuyến trên CPU máy trạm, chi phí $0) hoặc MaziaoTTS API dự phòng; sử dụng thư viện `mutagen` (kèm fallback `ffprobe`) đo đạc chính xác thời lượng thực tế của file âm thanh $T_{\text{audio}}$ với sai số mục tiêu $\le 10\text{ms}$.
  - `NFR-COST-01`: Chi phí $0 vận hành khi sử dụng ZeroTTS offline CPU, không phụ thuộc API có phí.
- **Files Under Scope**:
  - `src/autovideo/voiceover/__init__.py`
  - `src/autovideo/voiceover/timing_probe.py`
  - `src/autovideo/voiceover/zerotts_adapter.py`
  - `src/autovideo/voiceover/maziao_adapter.py`
  - `src/autovideo/voiceover/manager.py`
  - `tests/test_voiceover.py`

---

## 2. Test Strategy
Chiến lược kiểm thử độc lập bao phủ toàn diện 4 phân hệ cốt lõi trước khi tích hợp vào pipeline:

### A. Precision Timing Probe Tests (`timing_probe.py`)
1. **Đo đạc độ chính xác sub-millisecond**:
   - Khởi tạo các file WAV mẫu thuần âm (sine wave) với số lượng mẫu (sample count) chuẩn xác tuyệt đối qua module chuẩn `wave`:
     - 1.000s @ 24000Hz (24,000 samples)
     - 2.500s @ 24000Hz (60,000 samples)
     - 0.350s @ 16000Hz (5,600 samples)
     - 5.125s @ 44100Hz (226,012 samples)
   - Kết quả đo thực tế đạt sai số $\le 0.005\text{s}$ ($\le 5\text{ms}$), vượt tiêu chuẩn yêu cầu $\le 10\text{ms}$.
2. **Cơ chế Fallback FFprobe**:
   - Khi mutagen trả về `None` (định dạng lạ hoặc header lỗi), hệ thống kích hoạt tự động fallback sang `ffprobe` và trích xuất `format.duration`.
3. **Bảo vệ biên & Ngoại lệ**:
   - Tệp không tồn tại $\to$ phát hiện `FileNotFoundError`.
   - Tệp 0 bytes $\to$ phát hiện `ValueError`.
   - Cả mutagen và ffprobe đều không đọc được $\to$ phát hiện `AudioProbeError`.

### B. ZeroTTS Offline Engine & Cadence Preprocessor Tests (`zerotts_adapter.py`)
1. **Bộ tách câu và gán nhịp thở / ngắt nghỉ dấu câu tiếng Việt**:
   - Dấu chấm (`.`): nghỉ dài ~500ms.
   - Dấu phẩy (`,`): nghỉ ngắn ~200ms.
   - Dấu gạch ngang / em-dash (`—`, `--`): đổi tông / nghỉ ~300ms.
   - Dấu chấm lửng (`...`, `…`): ngắt sâu / thở sâu ~700ms.
   - Dấu chấm cảm / hỏi (`!`, `?`): ngắt diễn cảm ~400ms.
   - Dấu hai chấm / chấm phẩy (`:`, `;`): ngắt giải thích ~350ms.
2. **Ước tính thời lượng (Estimated Duration)**:
   - Tính toán nhịp đọc chuẩn 2.85 từ/giây kết hợp tổng thời gian ngắt nghỉ dấu câu.
   - Điều biến theo hệ số tốc độ (speed multiplier: 1.5x nhanh hơn, 0.75x chậm hơn).
3. **Tổng hợp âm thanh ngoại tuyến ($0 Cost Deterministic)**:
   - Xuất file PCM 16-bit WAV chuẩn 24,000Hz.
   - Kiểm tra 4 giọng đọc tiếng Việt preset (`banmai`, `maichi`, `minhquang`, `thientam`).

### C. MaziaoTTS Fallback Adapter Tests (`maziao_adapter.py`)
1. **Chuẩn hóa Payload**:
   - Mode `paragraph`: đóng gói `parts`, `voiceId`, `config`, `modelId`.
   - Mode `subtitle`: gán `startTime` và `endTime`.
2. **Mock Mode & HTTP Polling Flow**:
   - Giả lập vòng đời: `submit_task` $\to$ `poll_until_complete` $\to$ `download_audio`.
3. **Xử lý lỗi & Timeout**:
   - Lỗi 401 Unauthorized $\to$ phát hiện `MaziaoAPIError` ngay lập tức.
   - Tác vụ quá thời gian chờ $\to$ phát hiện `MaziaoTimeoutError`.

### D. VoiceoverManager Orchestration Tests (`manager.py`)
1. **Audio Caching**:
   - Tính toán hash theo `(text, voice, speed)`.
   - Lần gọi thứ 2 trên cùng câu thoại $\to$ tái sử dụng file cache (`engine == "cached"`), bỏ qua re-synthesis để tiết kiệm CPU.
2. **Chuỗi dự phòng thất bại (Fallback Cascade)**:
   - Khi ZeroTTS gặp sự cố $\to$ VoiceoverManager tự động chuyển sang MaziaoTTS mà không làm đứt gãy luồng xử lý.
3. **Đồng bộ hóa thời lượng Screenplay (Audio-First Alignment)**:
   - Xử lý kịch bản mẫu 2 Chapters, 3 Scenes.
   - Cập nhật từng `scene.duration_sec` khớp chính xác với thời lượng audio thực tế được đo bằng `TimingProbe`.
   - Cập nhật tổng thời lượng kịch bản `screenplay.total_duration_sec`.

---

## 3. Verification Commands and Actual Output

### Execution of Voiceover Unit Tests
```bash
pytest -v tests/test_voiceover.py
```
**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 23 items

tests/test_voiceover.py::TestTimingProbe::test_probe_exact_wav_durations PASSED [  4%]
tests/test_voiceover.py::TestTimingProbe::test_probe_audio_duration_helper PASSED [  8%]
tests/test_voiceover.py::TestTimingProbe::test_probe_missing_file_raises_error PASSED [ 13%]
tests/test_voiceover.py::TestTimingProbe::test_probe_empty_file_raises_error PASSED [ 17%]
tests/test_voiceover.py::TestTimingProbe::test_ffprobe_fallback_when_mutagen_fails PASSED [ 21%]
tests/test_voiceover.py::TestTimingProbe::test_probe_error_when_both_methods_fail PASSED [ 26%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_punctuation_pause_values PASSED [ 30%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_preprocess_speech_segments PASSED [ 34%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_preprocess_speech_segments_em_dash PASSED [ 39%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_preprocess_empty_text PASSED [ 43%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_calculate_estimated_duration PASSED [ 47%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_synthesize_generates_valid_audio PASSED [ 52%]
tests/test_voiceover.py::TestZeroTTSAdapter::test_synthesize_preset_voices PASSED [ 56%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_build_submit_payload_paragraph PASSED [ 60%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_build_submit_payload_subtitle PASSED [ 65%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_mock_mode_synthesis PASSED [ 69%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_api_submit_and_poll_flow PASSED [ 73%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_api_error_on_client_failure PASSED [ 78%]
tests/test_voiceover.py::TestMaziaoTTSAdapter::test_poll_timeout_raises_maziao_timeout_error PASSED [ 82%]
tests/test_voiceover.py::TestVoiceoverManager::test_synthesize_single_scene PASSED [ 86%]
tests/test_voiceover.py::TestVoiceoverManager::test_audio_caching_skips_resynthesis PASSED [ 91%]
tests/test_voiceover.py::TestVoiceoverManager::test_fallback_cascade_when_zerotts_fails PASSED [ 95%]
tests/test_voiceover.py::TestVoiceoverManager::test_process_screenplay_aligns_durations PASSED [100%]

============================= 23 passed in 0.99s ==============================
```

### Full Regression Test Suite Execution
```bash
pytest
```
**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: F:\Trung\Projects\BanContentAuto
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.1
collected 105 items

tests\test_binary_manager.py ........                                    [  7%]
tests\test_config.py .......                                             [ 14%]
tests\test_douyin_sourcing.py .........................                  [ 38%]
tests\test_script_pipeline.py .......................................... [ 78%]
tests\test_voiceover.py .......................                          [100%]

============================= 105 passed in 1.65s =============================
```

---

## 4. Residual Risks & Next Safe Action
- **Residual Risks**:
  - Khi cài đặt các checkpoint mô hình TTS deep learning nặng thực tế trên CPU yếu (ví dụ VITS / Piper), tốc độ suy luận (RTF - Real Time Factor) cần được giám sát để duy trì RTF $\le 0.5$.
  - Caching audio dựa trên text hash đã sẵn sàng, giúp tránh lãng phí CPU khi người dùng tinh chỉnh kịch bản từng phần.
- **Next Safe Action**:
  - Chuyển tiếp sang `WU-05`: Atomic Scene Assembly & 16:9 Blurred Transformation (B2), nhận đầu vào là các file audio đã được sinh từ `VoiceoverManager` cùng footage từ Asset Sourcing Engine để cắt gọt video vừa khít $T_{\text{audio}}$ và áp hiệu ứng 16:9 Blurred Margin.

# Requirements: BanContentAuto (Dual-Mode Video Factory)

Status: approved

## Overview and Traceability

Tài liệu này chuẩn hóa toàn bộ các yêu cầu chức năng (FR) và phi chức năng (NFR) cho hệ thống **BanContentAuto** dựa trên sơ đồ tư duy thực chiến 4 bước:
- **B1**: Viết kịch bản (Scriptwriting, chia scene 4s–8s, gói SEO & Thumbnail prompt).
- **B2**: Tạo video tự động ngầm (Trích xuất keyword từ scene, tự động tìm và tải footage Douyin/Bilibili/Stock sạch không watermark, tạo âm thanh ZeroTTS/Maziao, cắt footage khớp audio).
- **B3**: Ghép & Render video hoàn chỉnh (Rolling Chapter Buffer, Concat Demuxer).
- **B4**: Tạo ảnh Thumbnails đối nghịch (Visual tension, chuẩn 16:9, chừa vùng an toàn).

Tham chiếu:
- Sơ đồ mindmap của người dùng (B1 -> B2 -> B3 -> B4).
- [project/brief.md](BanContentAuto/project/brief.md)
- [project/context.md](BanContentAuto/project/context.md)
- [docs/PHUONG_AN_CHOT_HE_THONG_DOWNLOAD_VA_SAN_XUAT_VIDEO.md](BanContentAuto/docs/PHUONG_AN_CHOT_HE_THONG_DOWNLOAD_VA_SAN_XUAT_VIDEO.md)
- [docs/SPEC_MULTI_VAULT_ENGINE.md](BanContentAuto/docs/SPEC_MULTI_VAULT_ENGINE.md)
- [docs/SPEC_SKILL_NICHE_SYSTEM.md](BanContentAuto/docs/SPEC_SKILL_NICHE_SYSTEM.md)
- [docs/BRIEF_SCRIPTWRITING_PIPELINE.md](BanContentAuto/docs/BRIEF_SCRIPTWRITING_PIPELINE.md)

---

## Functional Requirements (FR)

### 1. BƯỚC 1: BIÊN SOẠN KỊCH BẢN & ĐÓNG GÓI SEO (`REQ-B1-SCR`)

- **`REQ-B1-01` (Nạp Skill Niche & Đấu Nối LLM Provider)**:
  - Hệ thống cho phép người dùng lựa chọn Skill Niche (VD: *Warehouse Fails*, *Dashcam Near-Misses*, *Military Micro-History*, *Vietnam Folkloric*...).
  - Hỗ trợ kết nối linh hoạt với LLM Provider qua 9router, Gemini 2.0 Flash (free tier), hoặc OpenAI Codex.
  - *Acceptance Criteria*:
    1. Trích xuất đúng chỉ dẫn sáng tạo, trường từ vựng giác quan và điều cấm kỵ (anti-tropes) từ `skills/<skill_id>/`.
    2. Tự động áp dụng kịch bản theo đúng định vị phong cách đã chọn.

- **`REQ-B1-02` (Viết Kịch Bản & Khử Giọng AI 35 Patterns)**:
  - Hệ thống tự động sinh lời bình luận/thuyết minh theo Persona "Nhà báo điều tra / Bình luận viên sắc bén" (trực diện, hơi gai góc, đanh thép, không sáo rỗng).
  - Tuân thủ công thức **Cold Open 30 giây** ở phần mở đầu: 0–5s cú sốc số liệu; 5–15s phá ngộ nhận/quy đổi sức mua; 15–30s câu hỏi mở (Open Loop).
  - Kích hoạt bộ lọc Anti-AI Humanizer loại bỏ 100% 35 mẫu nhận diện viết lách AI từ *WikiProject AI Cleanup*.
  - *Acceptance Criteria*:
    1. Đạt hệ số biến thiên độ dài câu $C_v \ge 0.4$ (xen kẽ câu ngắn 3–5 từ và câu dài 20–35 từ).
    2. Tuyệt đối không xuất hiện các từ ngữ trong danh sách đen: *"bức tranh toàn cảnh"*, *"minh chứng hùng hồn"*, *"trong dòng chảy lịch sử"*, *"hơn nữa"*, *"không chỉ X mà còn Y"*.

- **`REQ-B1-03` (Bẻ Nhỏ Phân Cảnh & Ngân Sách Từ Vựng)**:
  - Kịch bản được phân rã thành các atomic scenes có thời lượng ngắn từ **4 giây đến 8 giây**.
  - Tính toán ngân sách từ vựng (Word Budget) theo nhịp thở giọng đọc chuẩn (2.5 – 3.2 từ/giây):
    - Cảnh 4s–5s: 14–24 từ (1 câu dứt khoát).
    - Cảnh 6s–8s: 25–35 từ (2 câu hoàn chỉnh).
  - *Acceptance Criteria*:
    1. Mỗi cảnh là một đơn vị ngữ pháp độc lập, kết thúc bằng dấu chấm rõ ràng, không bị ngắt ngang câu.

- **`REQ-B1-04` (Đóng Gói Master Plan & Gói SEO/Thumbnail)**:
  - Kết thúc Bước 1, hệ thống tự động xuất ra hai tệp chuẩn hóa:
    1. `screenplay.json` (Master Plan): Chứa danh sách toàn bộ các chapters, scenes, text thuyết minh, gợi ý SFX và yêu cầu góc máy.
    2. `seo.md`: Chứa 3 lựa chọn Tiêu đề lý tính (dồn từ khóa chính vào 35 ký tự đầu), Mô tả chuẩn SEO, danh sách Hashtags, mốc phân chương (Timestamps), và 1 Prompt tạo ảnh Thumbnail theo luật đối nghịch.

---

### 2. BƯỚC 2: TẠO VIDEO (TỰ ĐỘNG CÀO FOOTAGE NGẦM & GHÉP SCENE) (`REQ-B2-PROD`)

*Toàn bộ các thao tác tìm kiếm, tải clip, bóc watermark và khớp audio được thực thi ngầm 100%, không yêu cầu người dùng thao tác thủ công.*

- **`REQ-B2-01` (Trích Xuất Từ Khóa Ngữ Nghĩa Từng Scene)**:
  - Tự động phân tích nội dung lời thoại của từng scene để sinh ra các bộ từ khóa tìm kiếm:
    - Từ khóa tiếng Trung để cào Douyin / Bilibili (ví dụ: `翻车现场`, `车祸瞬间`, `监控实拍`, `作死瞬间`).
    - Từ khóa tiếng Anh để truy vấn Pexels / Pixabay / Archive.org.

- **`REQ-B2-02` (Hạ Tầng Tải Ngầm & Bóc Watermark Douyin / Bilibili / Stock)**:
  - Tự động kích hoạt module downloader ngầm tương ứng:
    - **Douyin Engine**: Bẻ khóa chữ ký `A_Bogus` thuần Python (không cần Redis/Postgres), bóc tách trực tiếp link video gốc độ phân giải cao nhất không dính watermark Douyin ở cả 4 góc. Hỗ trợ Jitter Delay 1.5s–4.0s và tự động đọc `cookies.txt` chống chặn IP.
    - **Bilibili Engine**: Tự động gọi `bin/BBDown.exe` tải luồng DASH và mux video/audio 1080p.
    - **Stock / Universal**: Tự động gọi Pexels API hoặc `yt-dlp` cho các nguồn phụ trợ.
  - *Acceptance Criteria*:
    1. Video tải về máy được tự động lưu tạm tại `cache/raw_footage/`.
    2. Loại bỏ các clip có độ dài không phù hợp ($<8\text{s}$ hoặc vlog dài $>60\text{s}$).

- **`REQ-B2-03` (Tổng Hợp Giọng Nói Audio-First & Đo Đạc Sub-ms)**:
  - Từng câu thoại scene được tổng hợp bằng **ZeroTTS** (chạy ngoại tuyến trên CPU máy trạm, chi phí $0) hoặc **MaziaoTTS API**.
  - Dùng thư viện `mutagen` đo đạc chính xác thời lượng thực tế của file âm thanh: $T_{\text{audio}}$ với sai số $\le 10\text{ms}$.

- **`REQ-B2-04` (Cắt Gọt Footage Khớp Audio & Biến Đổi 16:9 Nền Mờ)**:
  - Nếu clip nguồn là video dọc (9:16) từ Douyin $\to$ tự động áp bộ lọc FFmpeg Blurred Background Margin sang tỷ lệ chuẩn 16:9 Full HD (1920x1080).
  - Tự động trim đoạn video cao trào khớp chính xác với thời lượng $T_{\text{audio}}$. Nếu clip ngắn hơn audio $\le 20\%$ $\to$ tự động áp hiệu ứng Slow-motion điện ảnh.
  - Hòa trộn âm thanh hiện trường ở mức âm lượng 30–40% dưới nền giọng đọc.
  - Xuất ra tệp atomic scene hoàn chỉnh: `cache/scenes/scene_XXX.mp4`.

---

### 3. BƯỚC 3: GHÉP & RENDER VIDEO HOÀN CHỈNH (`REQ-B3-REND`)

- **`REQ-B3-01` (Kiến Trúc Chapter Cuốn Chiếu - Rolling Disk Buffer)**:
  - Hệ thống gom các atomic scenes thành các Chapter (5–10 phút mỗi Chapter).
  - Render tuần tự từng Chapter thành file `part_0X.mp4`.
  - *Acceptance Criteria*:
    1. Ngay khi Chapter hoàn tất, hệ thống tự động xóa sạch các file tạm `scene_*.mp4` của Chapter đó.
    2. Dung lượng đĩa trống tiêu hao tối đa luôn $\le 3–5\text{ GB}$, không gây đầy ổ cứng dù video dài 30–120 phút.

- **`REQ-B3-02` (Ghép Nối Siêu Tốc Concat Demuxer)**:
  - Sử dụng cờ FFmpeg `-f concat -c copy` để nối các tệp `part_*.mp4` đã chuẩn hóa đồng nhất thông số (1920x1080, 30fps, H.264 High@L4.1, AAC 192kbps).
  - *Acceptance Criteria*:
    1. Xuất file video hoàn chỉnh 20–30 phút chỉ trong **30–45 giây**, không tiêu tốn CPU nén lại toàn bộ video (Zero Re-encode).
    2. Tệp hoàn chỉnh được lưu tại `renders/<project_id>_final.mp4`.

---

### 4. BƯỚC 4: TẠO ẢNH THUMBNAILS & ĐÓNG GÓI XUẤT BẢN (`REQ-B4-PUB`)

- **`REQ-B4-01` (Tạo Ảnh Thumbnail Đối Nghịch Chuẩn 16:9)**:
  - Đọc prompt kịch bản và concept từ `seo.md`.
  - Tự động kết xuất ảnh Thumbnail 16:9 (1280x720 hoặc 1920x1080) làm nổi bật điểm căng thẳng thị giác (Visual Tension).
  - *Acceptance Criteria*:
    1. Tuyệt đối chừa trống 20% góc dưới bên phải (tránh nhãn thời lượng video của YouTube đè lên).
    2. Không lặp lại từ ngữ của Tiêu đề (áp dụng Luật Đối Nghịch Title - Thumbnail).

- **`REQ-B4-02` (1-Click YouTube Publishing & Batch Queue)**:
  - Cung cấp giao diện xem trước toàn bộ sản phẩm xuất xưởng: Video 1080p, ảnh Thumbnail, bộ thẻ SEO.
  - Hỗ trợ nút bấm đăng tải trực tiếp lên YouTube qua YouTube Data API v3 hoặc lưu kho chờ duyệt thủ công.
  - Hỗ trợ chạy hàng loạt (Batch Queue) nhiều dự án tự động xuyên đêm.

---

## Non-Functional Requirements (NFR)

- **`NFR-COST-01` (Chi Phí $0 Vận Hành)**: Sử dụng Gemini Flash free tier (15 RPM), ZeroTTS CPU offline, binary FFmpeg/BBDown đóng gói sẵn, không có phí API bắt buộc.
- **`NFR-PERF-01` (CPU Friendly)**: Kiểm soát đa tiến trình an toàn (`render_concurrency=2`, `download_concurrency=4`), vận hành trơn tru trên laptop/desktop phổ thông (4-8 cores, 8-16GB RAM).
- **`NFR-REL-01` (Phục Hồi Sự Cố - Fault Tolerance)**: Hỗ trợ `--resume`; khi gặp sự cố, hệ thống phát hiện các Chapter đã render và tiếp tục tự động mà không làm lại từ đầu.

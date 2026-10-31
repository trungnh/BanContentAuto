# UI Design Specification: BanContentAuto Studio Dashboard

Status: approved

## 1. TỔNG QUAN THIẾT KẾ & TRIẾT LÝ VẬN HÀNH

Tài liệu này định nghĩa thiết kế giao diện Full App cho ứng dụng máy trạm Windows **BanContentAuto Studio**.
- **Nguyên tắc cốt lõi**: **Script-Driven Automation** (Người dùng không phải làm các tác vụ cào download thủ công; việc tìm và tải footage Douyin/Bilibili/Stock được hệ thống thực thi ngầm 100% theo từng phân cảnh kịch bản).
- **Quy trình 4 bước chuẩn**:
  - **B1**: Viết kịch bản & Gói SEO/Thumbnail.
  - **B2**: Tạo video (Cào footage ngầm + TTS + Cắt gọt scene).
  - **B3**: Ghép & Render video hoàn chỉnh (Rolling Buffer).
  - **B4**: Tạo ảnh Thumbnails đối nghịch & Xuất bản YouTube.

---

## 2. BỐ CỤC KHUNG NHÌN STUDIO WORKSPACE (LAYOUT ARCHITECTURE)

Ứng dụng sử dụng cấu trúc giao diện **Studio Workspace Hiện Đại** (phong cách CapCut Desktop kết hợp Pipeline Tracker trực quan):

```
+---------------------------------------------------------------------------------------------------------------+
|  BANCONTENT AUTO STUDIO  [v2.0]     [Project: P340 - Khoanh Khac Suyt Chet]   [CPU: 18% | RAM: 32% | Buffer: 1.2GB] |
+---------------------------------------------------------------------------------------------------------------+
| SIDEBAR      | WORKSPACE CHÍNH                                                                                |
|              |                                                                                                |
| [1] Tạo Dự Án|  TIẾN ĐỘ TOÀN BỘ PIPELINE (END-TO-END TRACKER)                                                 |
|     Mới      |  --------------------------------------------------------------------------------------------  |
|              |  [ B1: Kịch Bản ] ====> [ B2: Footage Ngầm & TTS ] ====> [ B3: Render MP4 ] ====> [ B4: Thumb ]|
| [2] Kịch Bản |       (Hoàn tất)               (Đang xử lý: Scene 28/70)         (Chờ xử lý)          (Chờ xử lý)  |
|     Studio   |                                                                                                |
|              | +-------------------------------------------------------+ +----------------------------------+ |
| [3] Giám Sát | | BẢNG PHÂN CẢNH THỜI GIAN THỰC (SCENE INSPECTOR)       | | XEM TRƯỚC PHÂN CẢNH (PREVIEW)    | |
|     Pipeline | |                                                       | |                                  | |
|              | | Scene 01 [0:00-0:05] Hook: Xe tải trượt dốc           | |  +----------------------------+  | |
| [4] Kết Quả  | | Lời thoại: "Chỉ còn đúng một tích tắc..."             | |  | [ Mini Video Player 16:9 ] |  | |
|     Xuất Bản | | Từ khóa ngầm: [dashcam near miss, 车祸瞬间]            | |  |                            |  | |
|              | | Footage: [Douyin Clean] [Nền mờ 16:9] [Status: OK]    | |  |  Scene 01 Live Preview     |  | |
| [5] Cài Đặt  | | Audio: ZeroTTS (4.82s) [Word Budget: 16 từ - Chuẩn]   | |  +----------------------------+  | |
|     Hệ Thống | | ----------------------------------------------------- | |                                  | |
|              | | Scene 02 [0:05-0:12] Xe nâng lật trong kho            | | Audio Waveform: [||||||||||||||] | |
|              | | Lời thoại: "Sai lầm này đã thổi bay cả tỷ đồng..."    | | Nguồn: Douyin #aweme_7419...     | |
|              | | Từ khóa ngầm: [forklift accident, 翻车现场]           | | Độ dài: 4.82s | Ngân sách: 16 từ | |
|              | | Footage: [Bilibili HD] [Status: Đang tải...]          | | Watermark: [CLEAN 100%]          | |
|              | +-------------------------------------------------------+ +----------------------------------+ |
|              |                                                                                                |
|              | NHẬT KÝ VẬN HÀNH (LIVE LOGS):                                                                  |
|              | [22:15:02] B1: Đã biên soạn 70 scenes. Anti-AI Check: PASS (0/35 patterns).                   |
|              | [22:15:10] B2: Đang tự động cào Douyin clip cho Scene 01 -> Trích xuất MP4 sạch không logo.     |
+--------------+------------------------------------------------------------------------------------------------+
```

---

## 3. CHI TIẾT 4 PHÂN HỆ MÀN HÌNH CHÍNH (SCREEN INVENTORY)

### Màn hình 1: Khởi Tạo Dự Án 1-Click (Quick Launch Wizard)
- **Mục tiêu**: Người dùng bắt đầu một dự án mới trong chưa đầy 1 phút.
- **Thành phần**:
  - *Tên Dự Án / Chủ đề*: Ô nhập text (ví dụ: *"Khoảnh khắc thoát chết khó tin P340"* hoặc *"Lịch sử xe tăng T-54"*).
  - *Bộ chọn Skill Niche (Dropdown)*: Lựa chọn phong cách kênh:
    - `Fails & Tai Nạn Lao Động` (MEO-Style Compilation).
    - `Dashcam & Giao Thông Gay Cấn`.
    - `Thiên Tai & Thời Tiết Cực Đoan`.
    - `Lịch Sử Quân Sự Vi Mô`.
  - *Thời lượng đích*: Lựa chọn nhanh (15 phút, 30 phút, hoặc Tùy chỉnh).
  - *Nút bấm hành động*: **"BẮT ĐẦU SẢN XUẤT TỰ ĐỘNG (FULL PIPELINE)"** (màu Cyan nổi bật).

---

### Màn hình 2: Kịch Bản Studio & Scene Inspector (Script Studio)
- **Mục tiêu**: Cho phép người dùng duyệt kịch bản B1, xem trước phân cảnh trước khi render hoặc để app tự động chạy tiếp.
- **Thành phần**:
  - *Bảng phân cảnh (Scene List Table)*: Hiển thị tuần tự từng scene từ 4s–8s:
    - Số thứ tự & Mốc thời gian (`0:00 - 0:05`).
    - Lời thoại thuyết minh tiếng Việt.
    - Nhãn đo ngân sách từ vựng (Word Budget Pill: Xanh lá = Đạt chuẩn 2.5–3.2 từ/s; Đỏ = Quá dài; Vàng = Quá ngắn).
    - Bộ từ khóa trích xuất tự động phục vụ cho Bước 2 cào footage ngầm.
  - *Anti-AI Badge*: Đèn xanh xác nhận kịch bản đã qua bộ lọc 35 patterns (không sáo rỗng, nhịp câu biến thiên $C_v \ge 0.4$).
  - *Nút Tùy Chỉnh Nhanh*: "Tái tạo lời thoại với Persona", "Chỉnh sửa câu chữ thủ công".

---

### Màn hình 3: Giám Sát Tiến Độ Video Thời Gian Thực (Pipeline Live Monitor)
- **Mục tiêu**: Theo dõi trực quan tiến trình B2 (Tải footage ngầm + Audio) và B3 (Render ghép Chapter).
- **Thành phần**:
  - *Bộ đếm tiến trình*: Hiển thị cụ thể (Ví dụ: *"Đang cào & cắt footage: 42/70 scenes"*).
  - *Scene Mini Player*: Khung phát video 16:9 xem thử ngay đoạn atomic scene vừa ghép xong (đã áp dụng nền mờ 16:9 cho Douyin và ghép audio ZeroTTS).
  - *Chapter Render Progress*: Thanh tiến trình render cuốn chiếu theo từng Chapter (Part 01 $\to$ Part 02) và đồng hồ đo giải phóng bộ đệm đĩa cứng (`Buffer: 1.2 GB / 5.0 GB Safe Limit`).

---

### Màn hình 4: Đóng Gói Xuất Bản & YouTube Hub (Output & Publishing Hub)
- **Mục tiêu**: Xem toàn bộ thành quả B3 và B4 sẵn sàng xuất bản lên YouTube.
- **Thành phần**:
  - *Trình phát video Full HD 1080p*: Xem lại toàn bộ video 20–30 phút.
  - *Thẻ Thumbnail Đối Nghịch (B4 Output)*:
    - Hiển thị ảnh Thumbnail 16:9 độ nét cao.
    - Grid an toàn mô phỏng YouTube: Kiểm tra đảm bảo góc dưới bên phải không bị che khuất bởi nhãn thời lượng video.
  - *Bảng gói SEO (`seo.md` Package)*:
    - 3 lựa chọn Tiêu đề đối nghịch với Thumbnail.
    - Hộp mô tả video chuẩn SEO đã điền sẵn danh sách mốc thời gian Chapters (`00:00 Hook`, `03:20 Sự cố...`).
    - Danh sách Hashtags & Tags.
  - *Nút bấm hành động*: **"1-Click Đăng Lên YouTube"** (qua YouTube Data API v3) hoặc **"Mở Thư Mục Chứa File"**.

---

### Màn hình 5: Cài Đặt Hệ Thống & Quản Lý Cấu Hình (Settings & System Health Hub)
- **Mục tiêu**: Quản lý tập trung các khóa API, thông số tài nguyên máy trạm, cấu hình cào footage ngầm, giọng đọc ZeroTTS và bảo vệ đĩa cứng.
- **Thành phần**:
  - *Thẻ 1: Trí Tuệ Nhân Tạo & Biên Kịch (B1)*:
    - Khóa Google Gemini API Key (hỗ trợ che/hiện mật khẩu, nút kiểm tra kết nối trực tiếp).
    - Bộ chọn Model LLM (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`).
  - *Thẻ 2: Hạ Tầng Footage Sạch & Douyin (B2)*:
    - Quản lý Douyin Cookie / Token và nhãn chỉ báo thuật toán ký số `A_Bogus`.
    - Điều chỉnh độ trễ ngẫu nhiên Jitter chống chặn IP (Min 2.0s - Max 5.0s).
  - *Thẻ 3: Giọng Đọc & Chuẩn Hóa Âm Thanh (B2)*:
    - Bộ chọn giọng đọc tiếng Việt đa vùng miền (Edge TTS & ZeroTTS).
    - Thanh trượt tốc độ đọc (0.8x - 1.3x) và chuẩn âm lượng YouTube (-14.0 LUFS).
  - *Thẻ 4: Quản Lý Đĩa Cứng & Bộ Đệm Rolling Buffer (B3)*:
    - Giới hạn Rolling Buffer (mặc định 5.0 GB), số luồng render đồng thời (1-4).
    - Tự động dọn dẹp các part chapter sau khi nối video hoàn chỉnh.
    - Bảng đo dung lượng cache thời gian thực (Audio, Footage, Scenes) và nút 1-Click **"Dọn dẹp cache ngay"**.
  - *Thẻ 5: Tình Trạng Công Cụ Ngoại Vi (Binaries Status)*:
    - Bảng trạng thái trực quan cho `ffmpeg`, `ffprobe`, `yt-dlp`, `BBDown` kèm nút quét lại.
  - *Nút bấm hành động*: **"LƯU CẤU HÌNH HỆ THỐNG"** (màu Cyan nổi bật).

---

## 4. DESIGN SYSTEM & TOKENS (VIDEO PRODUCTION THEME)

- **Bảng Màu Chủ Đạo (Dark Theme)**:
  - *Background Obsidian*: `#0B0F17` (tối sâu, tôn vinh hình ảnh video).
  - *Surface / Sidebar*: `#131A26` (slate gray đậm phân tầng).
  - *Card Container*: `#1C2536` (khối chứa nội dung các scene).
  - *Accent Cyan (Action)*: `#00E5FF` (nút kích hoạt, tiến trình chính).
  - *Success Mint*: `#00E676` (báo hiệu Clean Watermark, đạt Word Budget).
  - *Alert Crimson*: `#FF3B30` (cảnh báo lỗi tải, từ vựng vượt ngân sách).
- **Typography**:
  - Tiêu đề & Văn bản: Inter / SF Pro Display.
  - Số liệu thời lượng, từ khóa và mã ID: JetBrains Mono / Roboto Mono.

---

## 5. TIÊU CHÍ NGHIỆM THU THỊ GIÁC (VISUAL ACCEPTANCE CRITERIA)

- **`VAC-UI-01`**: Người dùng có thể khởi chạy một dự án video hoàn chỉnh chỉ qua 1 màn hình Wizard với 3 trường nhập liệu mà không cần truy cập tab download riêng biệt.
- **`VAC-UI-02`**: Tiến trình 4 bước (B1 $\to$ B2 $\to$ B3 $\to$ B4) hiển thị trạng thái động thời gian thực rõ ràng trên thanh End-to-End Tracker.
- **`VAC-UI-03`**: Bảng phân cảnh (Scene Inspector) hiển thị đầy đủ nhãn Word Budget và cho phép xem trước từng atomic scene mini kèm audio waveform.
- **`VAC-UI-04`**: Màn hình xuất bản hiển thị đồng bộ cả video 1080p, ảnh Thumbnail có vùng an toàn YouTube, và bộ dữ liệu SEO.
- **`VAC-UI-05`**: Màn hình Cài Đặt Hệ Thống cho phép lưu trữ và kiểm tra toàn diện API Keys, Cookie, cấu hình giọng đọc, giới hạn Rolling Buffer và trạng thái 4 binary ngoại vi.

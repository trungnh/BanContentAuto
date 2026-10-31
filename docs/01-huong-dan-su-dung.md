# Hướng Dẫn Sử Dụng: BanContentAuto Studio Dashboard (v2.0)

Hệ thống **BanContentAuto** là ứng dụng độc lập trên máy tính Windows cá nhân (chi phí vận hành **$0**), tự động hóa quy trình tạo video compilation và documentary dài chuẩn bị kiếm tiền YouTube (YPP) từ stock/footage đa nguồn (Douyin, Bilibili, YouTube, Pexels) theo quy trình 4 bước khép kín:
- **B1**: Viết kịch bản theo nhịp thở giọng đọc (Word Budget 2.5–3.2 từ/s), khử giọng AI 35 patterns & công thức Cold Open 30s.
- **B2**: Tự động cào footage ngầm không watermark, tổng hợp giọng đọc ZeroTTS CPU offline, cắt gọt và chuyển đổi 16:9 nền mờ.
- **B3**: Ghép video theo Chapter cuốn chiếu (Rolling Disk Buffer $\le 3–5\text{ GB}$), ghép nối siêu tốc bằng Concat Demuxer.
- **B4**: Tạo ảnh Thumbnail đối nghịch 16:9 (chừa vùng an toàn 20% YouTube) & hoàn thiện bộ SEO xuất bản.

---

## 🚀 1. Khởi Động Nhanh (1-Click Start)

Cách đơn giản nhất để khởi chạy ứng dụng là nhấp đúp chuột vào file:
👉 **`start.bat`** (ở thư mục gốc của dự án).

Tệp này sẽ tự động:
1. Nhận diện đường dẫn môi trường Python và thư mục `src/`.
2. Kiểm tra tính sẵn sàng của các công cụ nhị phân hỗ trợ (`ffmpeg`, `ffprobe`, `yt-dlp`, `BBDown`).
3. Khởi chạy máy chủ FastAPI tại `http://127.0.0.1:8000`.
4. **Tự động mở trình duyệt web** đưa bạn vào giao diện **Studio Dashboard**.

---

## 🛠️ 2. Yêu Cầu Môi Trường & Cài Đặt (Prerequisites)

Nếu bạn vừa clone mã nguồn về máy mới, hãy đảm bảo các yêu cầu sau:

### 2.1. Python & Thư Viện
- Yêu cầu Python **3.11** hoặc **3.12** (đã tích chọn *"Add Python to PATH"* khi cài đặt).
- Cài đặt các thư viện cần thiết bằng lệnh:
```bash
pip install fastapi uvicorn pydantic mutagen pillow yt-dlp httpx pytest
```

### 2.2. Các Công Cụ Nhị Phân (`bin/` hoặc System PATH)
Hệ thống ưu tiên nhận diện file trong thư mục `bin/` của dự án trước, sau đó mới quét trong PATH hệ thống:
1. **`ffmpeg.exe` & `ffprobe.exe`**: Cần thiết để xử lý biến đổi 16:9 nền mờ, slow-mo, cắt audio và ghép video.
   - *Cách 1*: Tải FFmpeg build (ví dụ từ Gyan.dev) và copy `ffmpeg.exe`, `ffprobe.exe` vào thư mục `bin/` của dự án.
   - *Cách 2*: Thêm thư mục chứa FFmpeg vào biến môi trường PATH của Windows (hệ thống hiện đã tự nhận diện phiên bản 9.0.1 trên máy bạn).
2. **`yt-dlp.exe`**: Tự động nhận diện từ PATH hoặc copy vào `bin/` để tải video YouTube/Stock/Douyin fallback.
3. **`BBDown.exe`** (Tùy chọn): Nếu muốn tải video chất lượng 4K/1080p 60fps từ Bilibili, tải file `BBDown.exe` thả vào thư mục `bin/`.

---

## 🖥️ 3. Hướng Dẫn Sử Dụng Giao Diện Studio Dashboard

Khi mở giao diện tại `http://127.0.0.1:8000`, bạn sẽ thấy giao diện **Dark Theme phong cách Video Production Studio**:

```
+----------------------------------------------------------------------------------------------------+
|  BANCONTENT AUTO STUDIO  [v2.0]     [P340 - Khoảnh Khắc Suýt Chết]    [CPU: 18% | Buffer: 1.2 GB]  |
+----------------------------------------------------------------------------------------------------+
|  TIẾN ĐỘ 4 BƯỚC:  [ B1: Kịch Bản ] ===> [ B2: Footage Ngầm ] ===> [ B3: Render MP4 ] ===> [ B4: Thumb ]
+----------------------------------------------------------------------------------------------------+
```

### Bước 1: Khởi Tạo Dự Án 1-Click (Quick Launch Wizard)
1. Ở khung **Khởi Tạo Dự Án (Wizard)** bên trái:
   - **Tên đề tài**: Nhập chủ đề video (ví dụ: *"Khoảnh khắc thoát chết khó tin P340"* hoặc *"Lịch sử xe tăng T-54"*).
   - **Skill Niche**: Chọn ngách phù hợp từ menu (ví dụ: *Fails & Khoảnh Khắc Giật Gân*, *Dashcam Giao Thông*, *Lịch Sử Quân Sự*...).
   - **Thời lượng**: Chọn 15 phút, 30 phút, hoặc tùy chỉnh.
2. Nhấn nút: **"BẮT ĐẦU SẢN XUẤT TỰ ĐỘNG (FULL PIPELINE)"**.

### Bước 2: Theo Dõi Kịch Bản & Khử Giọng AI (B1)
- Hệ thống tự động sinh lời bình luận theo Persona *"Bình luận viên sắc bén"*.
- **Huy hiệu Anti-AI**: Hiển thị trạng thái `Anti-AI: 0/35 vi phạm (100% Sạch)`.
- **Thước đo Word Budget**: Từng cảnh hiển thị nhãn thời lượng và số từ:
  - 🟢 **Xanh lá (Optimal)**: Đạt chuẩn 2.5–3.2 từ/giây (chuẩn nhịp thở đọc).
  - 🟡 **Vàng (Too Short)** hoặc 🔴 **Đỏ (Too Long)**: Cảnh báo nếu câu quá ngắn/dài.

### Bước 3: Giám Sát Cào Footage Ngầm & Ghép Scene (B2 & B3)
- **Tự động 100%**: Hệ thống tự trích xuất từ khóa tiếng Trung/tiếng Anh $\to$ tự cào Douyin/Bilibili/Stock sạch logo $\to$ đọc ZeroTTS CPU $\to$ co giãn thời lượng và biến đổi nền mờ 16:9.
- **Xem trước phân cảnh (Mini Video Player)**: Nhấp vào từng scene để xem trước clip đã cắt ghép kèm thanh hiển thị sóng âm (Audio Waveform).
- **Khống chế đĩa đệm (Rolling Disk Buffer)**: Bạn có thể nhìn thấy chỉ số đĩa đệm luôn được giải phóng sau mỗi Chapter để giữ mức tiêu hao ổ cứng luôn $\le 3–5\text{ GB}$.

### Bước 4: Đóng Gói Xuất Bản & YouTube Hub (B4)
Khi thanh tiến trình đạt 100%:
- **Trình phát Video 1080p**: Xem lại toàn bộ video hoàn chỉnh.
- **Thumbnail Safe-Zone Preview**: Xem trước ảnh bìa Thumbnail, kèm khung đỏ kiểm tra đảm bảo góc dưới bên phải không bị che khuất bởi nhãn thời lượng video của YouTube.
- **Bộ dữ liệu SEO**: Copy nhanh 3 lựa chọn Tiêu đề đối nghịch, Hộp mô tả video kèm mốc Chapters (`00:00 Hook`, `03:20 Sự cố...`), và danh sách Tags.
- **Nút "1-Click Đăng Lên YouTube"**: Đăng tải trực tiếp qua YouTube API v3 hoặc mở thư mục `renders/` để lấy video đăng thủ công.

### Bước 5: Cài Đặt Hệ Thống & Cấu Hình Máy Trạm (Tab 5 - Settings)
Nhấp vào tab **"⚙️ 5. Cài Đặt Hệ Thống"** ở thanh sidebar bên trái để quản lý:
1. **9Router Gateway & Đa Provider LLM (Codex, Antigravity, Claude, Gemini)**:
   - **9Router API Base URL**: Điền đường dẫn API của 9Router (mặc định: `http://localhost:20128/v1` hoặc máy chủ từ xa).
   - **9Router Master API Key**: Nhập khóa xác thực của 9Router (hỗ trợ nút ẩn/hiện mật khẩu).
   - **Nút "🔄 Tải Models"**: Tự động kết nối đến `http://localhost:20128/v1/models` để quét toàn bộ danh sách các mô hình thực tế đang mở trên 9Router và nạp thẳng vào menu lựa chọn.
   - **Bộ chọn Mô hình LLM**: Chọn model bạn muốn sử dụng (ví dụ: `antigravity/claude-3-5-sonnet`, `codex/gpt-4o`, `codex/o3-mini`, `gemini-2.0-flash`...).
   - **Nút "Kiểm Tra"**: Xác thực kết nối và phản hồi từ 9Router ngay tức thì.
   - **Gemini API Key Dự phòng**: Ô nhập khóa Gemini trực tiếp khi không dùng 9Router. Nếu để trống cả hai, hệ thống chạy **Mock Offline** an toàn ($0 cost).
2. **Hạ Tầng Cào Footage Douyin & Jitter**:
   - Dán Cookie Douyin (nếu có tài khoản) hoặc để trống vì thuật toán ký số `A_Bogus` thuần Python tự động vượt rào tải video sạch watermark.
   - Tùy chỉnh độ trễ ngẫu nhiên Jitter (2.0s - 5.0s) chống chặn IP.
3. **Quản Lý Đa Nhà Cung Cấp Giọng Đọc (TTS Engine Studio với 4 Trang Con)**:
   - **Trang con 1 (ZeroTTS Offline $0 & Nhân Bản Giọng)**:
     - Nạp chính xác 8 giọng đọc chuẩn của thư viện ZeroTTS CPU: `Mai Chi`, `Bảo Trang`, `Kim Oanh`, `Gia Huy`, `Hữu Đức`, `Quang Minh`, `Tiến Đạt`, `Hà My` cùng nút **"🔄 Quét Lại Giọng"**.
     - Khung **Cài đặt Gói Giọng Clone (Voice Cloning)**: Cho phép chọn và tải lên tệp gói giọng `.zip` (chứa `voice.npz` từ zeroweight.ai hoặc cộng đồng) hoặc file `.npz` trực tiếp vào runtime của ZeroTTS (`~/.zerotts/voices/`). Giọng clone sẽ ngay lập tức xuất hiện trong danh mục chọn với nhãn `👑 Giọng Nhân Bản Cá Nhân`.
     - Tinh chỉnh thời gian nghỉ dấu phẩy (`comma_pause_ms`) và dấu chấm (`period_pause_ms`).
   - **Trang con 2 (Maziao Cloud TTS)**:
     - Nhập Maziao API Key (có nút ẩn/hiện mật khẩu và nút **"Kiểm Tra"** kết nối trực tiếp), API Base URL (mặc định: `https://app.maziao.com`), và Model ID (`lingual_speech_v2` hoặc `vieten_speech`).
     - Nút **"🔄 Tải Giọng Maziao"**: Tự động kết nối tới API của Maziao để quét toàn bộ giọng đọc hệ thống, giọng đọc tiếng Việt và các giọng clone cá nhân (`my-voices`) của bạn, đổ trực tiếp vào menu thả xuống để chọn chỉ với 1 click.
   - **Trang con 3 (Edge-TTS)**:
     - Chọn giọng Microsoft Neural (`vi-VN-HoaiMyNeural` hoặc `vi-VN-NamMinhNeural`) miễn phí không giới hạn.
   - **Trang con 4 (Cấu Hình Chung & Fallback)**:
     - Lựa chọn động cơ chính mặc định (Primary Engine: ZeroTTS, Maziao, hoặc Edge-TTS).
     - Tự động fallback: Tự động kích hoạt ZeroTTS nếu engine mạng gặp sự cố.
     - Tốc độ đọc (0.8x - 1.3x) và chuẩn âm lượng YouTube (-14.0 LUFS).
4. **Quản Lý Bộ Đệm Đĩa Cứng & Dọn Dẹp Cache**:
   - Giới hạn Rolling Buffer (mặc định 5.0 GB) và số luồng render đồng thời.
   - Bảng đo dung lượng cache thời gian thực (Audio, Footage, Scenes) và nút **"🧹 Dọn Dẹp Cache Ngay"** để giải phóng ổ cứng SSD chỉ với 1 click.
5. **Kiểm Tra & Cài Đặt Công Cụ Ngoại Vi (`bin/` & PATH)**:
   - Theo dõi trạng thái trực quan 4 công cụ: `ffmpeg`, `ffprobe`, `yt-dlp`, `BBDown`.
   - Nút **"⬇️ Cài Đặt / Tải Tự Động Binaries"**: Tự động tải hoặc sao chép toàn bộ các file thực thi cần thiết vào thư mục `bin/` chỉ với 1 click.
   - Nút **"🔄 Quét Lại Công Cụ"**: Quét lại phiên bản và trạng thái khả dụng.
6. **Lưu Cấu Hình**:
   - Nhấn **"LƯU CẤU HÌNH HỆ THỐNG"** để lưu tất cả thiết lập vào `config/settings.json`.

---

## 📂 4. Cấu Trúc Thư Mục Kết Quả Xuất Xưởng

Sau khi sản xuất xong, toàn bộ sản phẩm hoàn thiện được lưu trữ tại:
```
BanContentAuto/
├── renders/
│   └── <project_id>/
│       ├── final_video.mp4                  <-- Video Full HD 1080p hoàn chỉnh
│       ├── thumbnail.jpg                    <-- Ảnh bìa Thumbnail 16:9 đối nghịch
│       ├── thumbnail_safe_zone_preview.jpg  <-- Ảnh chẩn đoán vùng an toàn YouTube
│       └── seo.md                           <-- Bộ 3 tiêu đề, mô tả SEO, timestamps, tags
├── cache/                                   <-- Thư mục đệm tự động dọn dẹp
└── logs/                                    <-- Lịch sử hoạt động
```

---

## ❓ 5. Xử Lý Sự Cố Thường Gặp (FAQ / Troubleshooting)

1. **Nếu mất điện hoặc tắt máy giữa chừng khi đang render?**
   - Hệ thống có cơ chế checkpoint tự động (`--resume`). Khi bạn chạy lại `start.bat`, hệ thống sẽ tự động phát hiện các Chapter đã render và tiếp tục từ vị trí dở dang mà không phải làm lại từ đầu.
2. **Làm sao để nạp Cookie Douyin nếu bị Douyin hạn chế IP?**
   - Mở file `config/douyin_cookie.yaml` (hoặc tạo file `cookies.txt`) và dán chuỗi cookie trình duyệt của bạn vào. Module cào sẽ tự động đính kèm cookie và giãn độ trễ Jitter (1.5s–4.0s) để vượt qua tường lửa chống bot.
3. **Muốn chạy trên cổng mạng khác?**
   - Bạn có thể chạy thủ công qua terminal: `python app.py --port 8080 --open-browser`.

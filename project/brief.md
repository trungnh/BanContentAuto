# Project Brief: BanContentAuto (Dual-Mode Video Factory)

## Lifecycle profile

- `greenfield`
- Xây dựng hệ thống tự động hóa sản xuất video YouTube từ stock/footage đa nguồn (Douyin, Bilibili, Stock), hỗ trợ 2 chế độ: Compilation giật gân (MEO-style) và Phim tài liệu (Multi-Vault Engine) hướng tới đạt chuẩn bật kiếm tiền YPP (Transformative Fair Use).

## Intent

Cung cấp một ứng dụng độc lập trên PC Windows (chi phí vận hành $0) có khả năng tự động hóa quy trình:
1. Thu thập & chuẩn hóa video footage không watermark từ nhiều nguồn (Douyin, Bilibili, YouTube, Pexels, Pixabay, Archive.org).
2. Tự động sinh kịch bản & bình luận lôi cuốn qua Multi-Agent LLM Pipeline với phong cách "Bình luận viên sắc bén / Nhà báo điều tra", triệt tiêu hoàn toàn sáo rỗng AI thông qua bộ 35 quy chuẩn làm sạch văn phong (dựa trên Wikipedia AI Cleanup & humanizer).
3. Tích hợp chuyển văn bản thành giọng nói (ZeroTTS offline trên CPU / MaziaoTTS API giọng Việt chất lượng cao).
4. Dựng & biến đổi video (zoom, slo-mo, crop, blur-pad 16:9, chèn SFX) đảm bảo tiêu chuẩn bản quyền YouTube Fair Use và tránh lỗi Reused Content.
5. Quản lý hàng đợi sản xuất hàng loạt (Batch Pipeline) và hỗ trợ tự động đăng tải (YouTube Data API v3).

## Success measures

- **Sản xuất video tự động**: Tạo video compilation 20-30 phút (từ 50-80 clip) hoàn chỉnh có voiceover và hiệu ứng biến đổi với thời gian render tối ưu trên PC cá nhân.
- **Chất lượng kịch bản**: Không dính các mẫu câu sáo rỗng ("AI fingerprint"), đạt hệ số biến thiên nhịp câu (burstiness) tự nhiên, giữ chân người xem cao ở 30 giây đầu.
- **Chi phí & tài nguyên**: Vận hành $0 chi phí API bắt buộc (dùng ZeroTTS / Gemini Flash free / FFmpeg / yt-dlp / BBDown), chạy ổn định trên CPU máy tính Windows.
- **Khả năng thương mại**: Video xuất xưởng vượt qua kiểm duyệt nội dung dùng lại (Reused Content) của YouTube Partner Program (YPP).

## Constraints

- Môi trường chạy: Hệ điều hành Windows, đóng gói Portable hoặc chạy script tự động bằng Python 3.11+.
- Chi phí hạ tầng: $0 (không phụ thuộc cloud/VPS bắt buộc hay GPU đắt đỏ; tận dụng CPU và các API miễn phí/offline).
- Kênh tiên phong: Thị trường Việt Nam (ngôn ngữ Tiếng Việt), ngách đầu tiên là **Compilation (Fails / Dashcam / Khoảnh khắc giật gân suýt thảm họa)**.

## Non-goals

- Không xây dựng nền tảng SaaS web công cộng đa người dùng (multi-tenant) trong giai đoạn MVP.
- Không cố gắng can thiệp can thiệp thủ công từng frame trên timeline như Premiere/After Effects; tập trung tự động hóa theo template cấu trúc kịch bản và luật biến đổi visual.
- Không tải nhạc hoặc clip có dính bản quyền thương mại âm nhạc gắt gao (chỉ dùng âm thanh hiện trường, nhạc nền royalty-free và SFX tạo lập sẵn).

## Known risks and unknowns

- **Rủi ro Reused Content từ YouTube**: Cần liên tục hoàn thiện bộ biến đổi thị giác (zoom-in, slo-mo, blurred padding) và mật độ giọng đọc voiceover liên tục để đảm bảo tính chuyển hóa (Transformative).
- **Độ ổn định của cơ chế cào Douyin/Bilibili**: Phụ thuộc vào cập nhật thuật toán chống bot; cần module hóa downloader (dùng yt-dlp, BBDown, f2) để thay thế nhanh khi có sự cố.
- **Giả định cần xác thực**:
  - [Assumed] ZeroTTS chạy mượt mà trên CPU Windows và đáp ứng được chất lượng giọng đọc tự nhiên cho clip 20-30 phút.
  - [Assumed] Gemini 2.0 Flash hạn mức miễn phí (free tier) đủ để phân tích và sinh commentary cho batch nhiều video/ngày.

# Project Context: BanContentAuto (Dual-Mode Video Factory)

Status: proposed

## Intent summary

BanContentAuto là ứng dụng tự động hóa sản xuất video YouTube từ nguồn tư liệu/footage đa nền tảng (Douyin, Bilibili, Stock video, Public Domain Archives). Mục tiêu cốt lõi là tạo ra các video dài (compilation 20–30 phút hoặc documentary 30–120 phút) hấp dẫn, tự nhiên, tối ưu thời gian xem (Watch Time) và tuân thủ nguyên tắc Biến đổi Hợp pháp (Transformative Fair Use) để kênh đủ điều kiện bật và duy trì kiếm tiền YouTube Partner Program (YPP) mà không bị từ chối với lỗi "Nội dung sử dụng lại" (Reused Content).

Dự án áp dụng mô hình **Dual-Mode Studio**:
1. **Mode 1 (Ưu tiên MVP)**: Compilation Video (Fails, Dashcam, khoảnh khắc giật gân, suýt thảm họa theo phong cách kênh MEO).
2. **Mode 2 (Mở rộng)**: Long-form Documentary (Phim tài liệu chuyên sâu theo kiến trúc Multi-Vault Engine).
3. **Bộ máy Kịch bản & Bình luận (Scriptwriting Brain)**: Sử dụng Multi-Agent LLM Pipeline với persona "Nhà báo điều tra / Bình luận viên sắc bén", tích hợp bộ lọc 35 quy chuẩn Anti-AI (dựa trên Wikipedia AI Cleanup & humanizer) để loại bỏ hoàn toàn các mẫu câu sáo rỗng của chatbot, tạo nhịp câu biến thiên sinh động (burstiness) và viết theo nhịp thở giọng đọc.

## Users and stakeholders

- **Primary User**: Nhà sáng tạo nội dung (Content Creator / Solo Builder) muốn xây dựng và vận hành kênh YouTube tự động hóa trên máy tính cá nhân.
- **Audience**: Khán giả YouTube theo dõi các chủ đề giật gân, giải trí, bài học an toàn giao thông/lao động và phim tài liệu lịch sử/kinh tế/quân sự.
- **Platform Authority**: Thuật toán kiểm duyệt và nguyên tắc cộng đồng của YouTube (chính sách YPP, bản quyền Content ID, chính sách Reused Content).

## Lifecycle evidence

- **Profile**: Greenfield.
- **Hiện trạng kho mã nguồn**: Chưa có mã nguồn ứng dụng đang chạy trước đó; dự án bắt đầu từ các tài liệu đặc tả kiến trúc (`docs/`), ghi chú nghiên cứu ý tưởng (`project/idea-notes.md`), và tài liệu định hướng (`project/brief.md`). Không có hệ thống legacy hay cơ sở dữ liệu production nào ràng buộc thiết kế.

## Constraints and success measures

### Constraints (Ràng buộc bắt buộc)
- **Hạ tầng & Nền tảng**: Chạy độc lập trên máy tính cá nhân hệ điều hành Windows, có thể đóng gói Portable `.exe` hoặc thực thi bằng Python 3.11+.
- **Ngân sách vận hành**: Chi phí $0 cố định (Zero-cost invariant):
  - TTS: Ưu tiên ZeroTTS (chạy offline trên CPU máy tính, tối ưu tiếng Việt) hoặc MaziaoTTS (API giọng đọc tiếng Việt chất lượng cao khi có credits).
  - LLM: Tận dụng Gemini 2.0 Flash (free tier 15 RPM) cho các agent sinh kịch bản và bình luận.
  - Xử lý video/audio: Dùng FFmpeg binary, yt-dlp, BBDown.exe không yêu cầu dịch vụ đám mây trả phí.
- **Ngôn ngữ mục tiêu**: Tiếng Việt chuẩn ngữ điệu, hỗ trợ đọc ngắt nghỉ tự nhiên theo dấu câu.
- **Quy chuẩn bản quyền (YPP Safe)**: Mọi video compilation xuất xưởng phải có:
  - Giọng đọc bình luận/phân tích liên tục tối thiểu 70–80% thời lượng.
  - Biến đổi khung hình (Blurred Margin 9:16 sang 16:9, zoom-in, slow-motion, đồ họa chỉ điểm).
  - Loại bỏ hoàn toàn logo và watermark gốc.

### Success measures (Thước đo thành công)
1. **Mức độ tự động hóa**: Hệ thống có khả năng chạy Full-Auto theo kịch bản: nhận danh sách link/từ khóa $\to$ tải và lọc video sạch $\to$ sinh bình luận và kịch bản $\to$ sinh giọng đọc TTS $\to$ render FFmpeg $\to$ xuất file MP4 hoàn chỉnh 20–30 phút.
2. **Chất lượng kịch bản (Anti-AI Score)**: Kịch bản không chứa bất kỳ từ ngữ nào trong danh sách đen từ vựng AI (35 patterns), có hệ số biến thiên độ dài câu $C_v \ge 0.4$, giữ chân người xem tốt trong 30 giây đầu (Cold Open).
3. **Độ ổn định tài nguyên**: Không gây lỗi tràn bộ nhớ (Out-Of-Memory) hay nghẽn CPU/đĩa cứng trên máy cá nhân nhờ cơ chế chia đoạn cuốn chiếu (Rolling Disk Buffer $\le 3–5\text{ GB}$).
4. **Hiệu suất sản xuất**: Hỗ trợ chế độ Batch Queue tạo từ 3 đến 5 video hoàn chỉnh mỗi ngày mà không cần can thiệp thủ công liên tục.

## Non-goals (Ngoài phạm vi dự án)

- Không phát triển hệ thống SaaS Web nhiều người dùng (multi-tenant) có thanh toán trực tuyến trong giai đoạn MVP.
- Không xây dựng trình biên tập video dạng timeline tương tác đồ họa phức tạp như Adobe Premiere hay DaVinci Resolve.
- Không sử dụng nhạc nền hoặc tư liệu dính bản quyền âm nhạc thương mại của các hãng đĩa; chỉ sử dụng hiệu ứng âm thanh (SFX) thủ tục và âm thanh môi trường nguyên bản đã xử lý.

## Principal risks

1. **Rủi ro kiểm duyệt Reused Content từ YouTube**: Thuật toán YouTube siết chặt các kênh compilation.
   - *Biện pháp giảm thiểu*: Tăng cường chiều sâu phân tích của kịch bản Voiceover, phối hợp đồ họa phân tích tình huống (zoom, slow-motion, vòng tròn đỏ, mũi tên cảnh báo) và biến đổi hình ảnh đa tầng.
2. **Rủi ro gián đoạn cào dữ liệu từ Douyin/Bilibili**: Thay đổi thuật toán chữ ký chống bot (`A_Bogus`, `WBI`).
   - *Biện pháp giảm thiểu*: Trừu tượng hóa Downloader Provider, dùng yt-dlp liên tục cập nhật và tích hợp công cụ chuyên biệt `BBDown.exe`, `f2`.
3. **Rủi ro chất lượng giọng đọc TTS trên CPU**: ZeroTTS có thể gặp khó khăn về âm sắc hoặc ngắt nghỉ trên các câu văn dài.
   - *Biện pháp giảm thiểu*: Áp dụng quy chuẩn ngân sách từ vựng khắt khe (Word Budget 2.5–3.2 từ/giây), ngắt câu ngắn và bổ sung fallback sang MaziaoTTS.

## Assumptions requiring validation

- `[ASSUMPTION-01]` ZeroTTS hoạt động ổn định trên CPU Windows x64 mà không yêu cầu GPU rời đắt đỏ, phát âm danh từ riêng tiếng Việt rõ ràng.
- `[ASSUMPTION-02]` Hạn mức miễn phí của Gemini 2.0 Flash (15 RPM / 1M token/ngày) đủ đáp ứng nhu cầu sản xuất batch 3–5 kịch bản video compilation mỗi ngày.
- `[ASSUMPTION-03]` Tỷ lệ biến đổi hình ảnh và mật độ voiceover đạt chuẩn để kênh vượt qua vòng xét duyệt bật kiếm tiền thủ công của đội ngũ YouTube.

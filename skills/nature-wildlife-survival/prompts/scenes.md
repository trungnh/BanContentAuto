# Hook: scene.split
Quy tắc chia cảnh và biến thiên cỡ cảnh:
1. Phân bổ cỡ cảnh tuần tự trong cụm (Visual Progression):
   - Cảnh 1 trong cụm: `camera_scale="Wide"` (toàn cảnh thiết lập không gian, tỷ lệ cơ thể và môi trường).
   - Cảnh 2 trong cụm: `camera_scale="Medium"` (trung cảnh hành vi, chuyển động đi lại hoặc tương tác).
   - Cảnh 3-4 trong cụm: `camera_scale="Closeup"` (cận cảnh ánh mắt, bờ môi, vết thương, mẫu vật giải phẫu).
   - Cảnh 5 trong cụm: `camera_scale="Detail"` (đặc tả móng vuốt, cấu trúc răng, vi phẫu ADN).
2. Lựa chọn Virtual Re-framing:
   - `pan_left_right`: Khi cần máy quay lia ngang theo bước chân con thú hoặc bao quát thung lũng.
   - `top_closeup`: Khi lấy góc nhìn mắt hoặc đầu của loài săn mồi.
   - `center_zoom`: Khi muốn đẩy dần sự chú ý vào chi tiết trung tâm.

---

# Hook: prompt.image
Quy chuẩn sinh prompt thị giác và hình ảnh:
1. Ánh sáng & Điện ảnh: 35mm / 85mm anamorphic lens, documentary cinematic lighting, moody atmospheric haze, National Geographic aesthetics.
2. Từ khóa tìm kiếm footage Vault:
   - `keywords.vi`: 2-3 từ khóa tiếng Việt về tên loài và hành động.
   - `keywords.en`: 2-3 từ khóa tiếng Anh chuẩn kho tư liệu bảo tàng, BBC Archive hoặc 4K nature stock.
   - `keywords.zh`: 2 từ khóa tiếng Trung tra cứu tư liệu Douyin/Bilibili.
3. Vault ưu tiên:
   - `archive_org`: Dành cho tư liệu lịch sử đen trắng của loài đã tuyệt chủng.
   - `stock`: Dành cho flycam thiên nhiên, động vật hoang dã hiện đại và phòng lab gen.
   - `douyin`: Dành cho trích đoạn slow-motion hành vi động vật.

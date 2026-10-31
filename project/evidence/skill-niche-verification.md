# Bằng Chứng Xác Minh: Hệ Thống Skill Niche & Loại Bỏ Triệt Để Hardcode

- **Thời gian xác minh**: 2026-10-27
- **Tài liệu đặc tả**: `docs/SPEC_SKILL_NICHE_SYSTEM.md`
- **Mục tiêu**: Kiểm tra và chứng minh việc tổ chức Skill Niche, cung cấp ngách Thiên nhiên & Sinh tồn động vật, loại bỏ toàn bộ hardcode trong `src/publisher` và `src/script`, bảo đảm 100% quyết định nội dung thông qua LLM.

---

## 1. Kết Quả Quét & Đóng Gói Skill Niche Trên Đĩa (`skills/`)

Đã đóng gói thành công 5 gói Skill Niche chuẩn hóa theo kiến trúc `SPEC-AVF-SKILL-NICHE-V1`:

| Skill ID | Tên Hiển Thị | Badge Trên Dashboard | Hooks Tích Hợp |
| :--- | :--- | :--- | :--- |
| `nature-wildlife-survival` | Nature & Wildlife Survival Documentary | **Thiên Nhiên · Sinh Tồn & Sách Đỏ** | 8 hooks (`script.plan`, `script.rewrite`, `scene.split`, `prompt.image`, `prompt.video`, `prompt.thumbnail`, `prompt.seo`, `voice.direction`) |
| `historical-mysteries` | Ancient & Historical Mysteries Documentary | **Lịch Sử · Bí Ẩn & Kỳ Quan Cổ Đại** | 7 hooks |
| `warehouse-fails` | Warehouse Fails & Industrial Safety Breakdown | **Sự Cố · Kho Bãi & An Toàn Lao Động** | 7 hooks |
| `military-microhistory` | Military Micro-History Documentary | **Quân Sự · Hậu Cần & Kỷ Vật Chiến Hào** | 7 hooks |
| `extreme-weather` | Extreme Weather & Catastrophic Natural Disasters | **Thiên Tai · Bão Lũ & Khí Hậu Cực Đoan** | 7 hooks |

---

## 2. Bằng Chứng Loại Bỏ Triệt Để Hardcode

1. **`src/autovideo/publisher/seo_packager.py`**:
   - Đã xóa bỏ hoàn toàn các chuỗi tiêu đề cố định: `t1 = f"{kw_clean}: Toàn Bộ Sự Thật Chưa Từng Tiết Lộ Trong Hồ Sơ Kín"`, `t2 = ... "Nghịch Lý Đen Tối Và Cú Lừa Nguy Hiểm"`, `t3 = ... "Đại Án Điều Tra Bí Mật"`.
   - Đã xóa bỏ danh sách tags điều tra cố định ("hồ sơ mật", "bản tin điều tra").
   - 100% Tiêu đề, Mô tả, Tags và Hashtags được ưu tiên trích xuất từ kết quả của LLM dựa trên hook `prompt.seo` của Skill Niche.
2. **`src/autovideo/publisher/manager.py` & `src/autovideo/coordinator.py`**:
   - Đã xóa bỏ giá trị ép cứng `thumbnail_badge="ĐIỀU TRA"` và `thumb_hook="CÚ SỐC 3 GIÂY"`.
   - Badge và Hook được trích xuất động từ `SEOPackage` (do LLM sinh) hoặc `skill.badge` (ví dụ: `TUYỆT CHỦNG`, `SINH TỒN`, `KHOA HỌC GEN`).
3. **`src/autovideo/script/prompts.py` & `src/autovideo/script/pipeline.py`**:
   - `PromptCompiler` nhúng `creative_guidance` được biên dịch động từ `SkillRegistry`.
   - Mọi phân cảnh kịch bản: `cluster_id`, `environment_id`, `camera_scale`, `virtual_reframe`, `keywords (vi/en/zh)`, `text` được LLM quyết định 100% dựa trên chỉ dẫn của Skill.
4. **`src/autovideo/api/app.py` & `src/autovideo/ui/index.html`**:
   - Thêm endpoint `GET /api/skills` trả về danh sách động.
   - Dashboard UI xóa bỏ các `<option>` tĩnh, tự động gọi `loadSkills()` khi khởi động để nạp đầy đủ các ngách kèm icon, badge và mô tả phong cách trực quan.

---

## 3. Kết Quả Kiểm Thử Toàn Diện (Regression Suite)

- **Test Suite Mới**: `tests/test_skill_niche_registry.py` (10/10 passed).
- **Toàn Bộ Repository**: `python -m pytest tests/ -q`
- **Kết Quả Thực Tế**: **202 passed** trong 51.46 giây (100% pass, 0 fail, 0 warning regression).

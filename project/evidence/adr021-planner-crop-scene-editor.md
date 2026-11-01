# Evidence: ADR-021 Global footage plan, crop-zoom fix, confuser guard, Scene Editor (dashboard)

Date: 2026-10-31

## Checks run (actual results)

| Check | Result |
|---|---|
| `pytest tests/test_scene_editor_adr021.py` | 24 passed |
| `pytest tests` (lần chạy cuối, sau mọi thay đổi) | **315 passed** |
| Lỗi crop thật (`universal_gErthNrddFs.mp4`) | Trước: `crop=384:1008:6:8` (giữ 19% khung hình, zoom khoảng 5×). Sau: bị từ chối, có ghi log. Letterbox thật `1920:864:0:108` vẫn được nhận |
| Planner trên dữ liệu thật (proj_cf3b1f52) | 1.5 s cho 37 scene; 36 scene được gán shot, 27 video khác nhau. Confusers do LLM đề xuất: striped hyena, brown hyena, African wild dog, aardwolf, juvenile cheetah (1 lượt gọi, 4.7 s) |
| Viết lại mô tả shot (1 lượt gọi gộp, 4.6 s) | 5 scene yếu: 016 0.286→0.319, 020 không có→0.319, 031 0.268→0.313, 032 0.286→0.313 |
| API live `GET …/SCENE_035/alternatives?k=4` | 4.4 s, 4 ứng viên có ảnh xem trước; project vẫn ở trạng thái `COMPLETE` |
| API live `POST …/SCENE_035/redo` | done, khoảng 25 s; chọn đúng đoạn cũ nhưng cắt lại sau khi đã sửa lỗi crop → khung hình đầy đủ với bầy linh cẩu, judge 8/10; video cuối được ghép lại |
| API live `POST …/scenes/redo-flagged` (lần 1, logic cũ) | 3 scene bị **tệ đi** (011 3→2, 017 3→2, 032 4→3) → bổ sung luật chỉ thay khi tốt hơn (keep-if-better) + viết lại mô tả shot; khôi phục project từ backup rồi chạy lại |
| `redo-flagged` (lần 2, logic đã sửa) | changed=3, kept=9, **không scene nào tệ đi**: 011 3→**9**, 018 3→**6**, 032 được thay; 9 scene giữ footage hiện tại vì kho không có đoạn tốt hơn |

## Lỗi còn lại / rủi ro
- **9 scene vẫn bị gắn cờ**, chủ yếu vì kho thiếu footage phù hợp: cảnh sư tử cái cướp mồi, phân trắng, vết sẹo, hàng rào, gò mối lúc hoàng hôn. Cần thêm video vào kho (YouTube đang chặn) hoặc người dùng tự chọn bằng "Chọn footage khác".
- **Judge `flash-low` chưa ổn định** (035 trước đây). Có thể chọn model mạnh hơn trong Cài đặt → "Mô Hình AI Chấm Footage".
- **Planner tối ưu trên điểm CLIP**, chưa dùng điểm LLM.

## Backups
- `cache/backups/_backup_proj_cf3b1f52_20261031_1803/` (bản render trước ADR-020)
- `cache/backups/_backup_proj_cf3b1f52_before_edit_20261031_2158/` (trước khi chỉnh sửa scene bằng Scene Editor)

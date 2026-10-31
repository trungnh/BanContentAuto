# Idea Notes

Status: exploring

## Starting interests or problem spaces

- Developer muốn xây app tự động tạo video content từ stock footage đa nguồn
- Mục tiêu: xây kênh YouTube bật kiếm tiền (YPP)
- Đã có 3 spec chi tiết: Download Tool, Multi-Vault Documentary Engine, Skill Niche System
- Ràng buộc: $0 cost, PC cá nhân Windows, full auto + batch mode
- TTS: ZeroTTS (offline CPU, Vietnamese) hoặc MaziaoTTS (API, voice clone)

## Constraints and available advantages

**Ràng buộc:**
- Chi phí $0, chạy trên PC cá nhân Windows
- Không có server/cloud
- Cần đạt chuẩn YouTube YPP (Transformative Fair Use)

**Lợi thế sẵn có:**
- 3 spec kiến trúc rất chi tiết (download, multi-vault engine, skill niche)
- ZeroTTS: offline, CPU-only, tối ưu tiếng Việt, zero-shot voice clone
- MaziaoTTS: API credits-based, multi-language, voice clone chất lượng cao
- Gemini 2.0 Flash free tier: 15 RPM, 1M tokens/day
- YouTube Data API v3: 10K quota/day, miễn phí
- Hệ sinh thái Python mạnh cho video/ML

## Candidate ideas

| Idea | User | Problem | Value | Required data/access | MVP size | Dominant risk |
|---|---|---|---|---|---|---|
| A: Content Farm Machine | Creator scale 3-5 kênh | Mất 4-6h/video thủ công | 3-5 video/ngày auto | Douyin/Bilibili scraping, ZeroTTS | Lớn | YouTube Reused Content strike |
| **B: Dual-Mode Studio** | Creator nghiêm túc 1-2 kênh | Muốn cả compilation + documentary | 1 app, 2 workflow, chuyển mode | Douyin/Bilibili + Multi-Vault + TTS | Rất lớn | Complexity, scope creep |
| C: AI Script-First | Creator kênh tài liệu | Viết kịch bản tốn 8-12h | AI viết screenplay → auto dựng | LLM + Archive.org + ZeroTTS | Trung bình | Chất lượng kịch bản AI shallow |
| D: Niche Sniper | Creator 1 niche cụ thể | Cạnh tranh khốc liệt | App pre-configured cho 1 niche | Tùy niche | Nhỏ nhất | Chọn sai niche |
| E: Batch+Curator | Creator 1-2h/ngày | Full auto → chất lượng thấp | Máy sinh 5-10 bản thô, người chọn | Giống A/B + preview gallery | Trung bình | Tỷ lệ bản thô tốt quá thấp |
| F: SaaS Platform | Creator cộng đồng VN | Không có tool end-to-end VN | Bán/thuê tool cho creator khác | Web UI, account, payment | Rất lớn | Phân tán focus |

## Shortlist and comparison criteria

**Đề xuất mạnh nhất: Hướng B (Dual-Mode Studio) + Hướng E (Batch+Curator)**

Lý do:
- Phù hợp 100% yêu cầu developer (2 mode, full auto, batch)
- Tận dụng trọn vẹn 3 spec đã viết
- Compilation ra kết quả nhanh → validate YPP sớm
- Documentary build on top → scale chất lượng + CPM
- Batch mode cho phép "máy sinh, người chọn" → kiểm soát chất lượng

## Rejected ideas and reasons

- **D (Niche Sniper)**: Quá hẹp, không tận dụng hết spec đã viết
- **F (SaaS Platform)**: Vượt scope cá nhân, phân tán focus giữa "xây kênh" và "xây product"

## Assumptions to validate

- A1: ZeroTTS chạy ổn định trên Windows, output đủ tự nhiên cho voiceover 30 phút
- A2: MaziaoTTS API credits đủ dùng cho batch
- A3: YouTube Data API v3 quota đủ upload 3-5 video/ngày
- A4: Pixabay/Pexels free tier không bị rate limit khi 100+ clips/ngày
- A5: Gemini 2.0 Flash free tier đủ viết 5-10 kịch bản/ngày
- A6: Transformation (voiceover + visual) đủ để pass YouTube Reused Content check

## Open questions

1. Niche đầu tiên: Dashcam fails, CCTV moments, wildlife, hay idiots at work?
2. Ngôn ngữ video: Tiếng Việt, tiếng Anh, hay cả 2?
3. Thumbnail: AI generate hay template Pillow?
4. Scheduling: Bao nhiêu video/tuần/kênh?
5. Existing code: Đã có code nào chưa?

## Scriptwriting Pipeline Deep-Dive (Round 2)

### Problem statement
Kịch bản AI bị 12 "dấu vân tay AI" (buzzwords, nhịp đều, thiếu giác quan, trung lập tuyệt đối) → khán giả nhận ra ngay, ảnh hưởng retention và YPP.

### 6 giải pháp đã brainstorm
| Giải pháp | Ưu điểm chính | Nhược điểm chính |
|---|---|---|
| A: Single Mega-Prompt | Đơn giản | Drift về giọng AI ở kịch bản dài |
| B: Hierarchical 2-Pass (Brief hiện tại) | Cấu trúc tốt | Thiếu persona, anti-AI layer |
| **C: Multi-Agent Persona Pipeline** | Mỗi agent chuyên biệt, anti-AI humanizer riêng | Nhiều API calls |
| D: Few-Shot Style Transfer | Copy giọng kênh mẫu | Cần transcript mẫu |
| E: Adversarial Writer-Detector | Tự kiểm AI score | Có thể over-rewrite |
| F: Human-in-the-Loop | Chất lượng cao nhất | Không full auto |

### Đề xuất mạnh nhất
**C + D + elements of E**: Multi-Agent Persona Pipeline (7 agents) với Few-Shot Style Anchor và AI Detection Gate nhẹ.

### 7 agents đề xuất
1. Researcher: Thu thập facts + sensory details
2. Story Architect: Blueprint acts/beats/twists
3. Voice Writer: Viết với persona + forbidden list + burstiness rules
4. Anti-AI Humanizer (Áp dụng 35 patterns chuẩn từ `blader/humanizer` & WikiProject AI Cleanup):
   - **Content level**: Triệt tiêu inflated claims/legacy ("đánh dấu bước ngoặt", "minh chứng sống"), bỏ sales language/từ hoa mỹ ("bức tranh kỳ vĩ", "vô cùng choáng ngợp"), cấm nguồn mơ hồ ("các chuyên gia nhận định").
   - **Language level**: Thay thế verbs dài dòng bằng động từ gốc (tránh "đóng vai trò là", "mang tính chất"), xóa bỏ mẫu "Không chỉ X mà còn Y" và nhóm 3 ép buộc (forced triad).
   - **Style level**: Bỏ fake-candid openings ("Thành thật mà nói?", "Bạn có tin không?"), loại bỏ kết bài hy vọng viển vông ("Tương lai tươi sáng phía trước"), dứt khoát kết thúc ở sự kiện/bằng chứng cuối cùng.
   - **Voice-matching engine**: Hỗ trợ nạp 2-3 đoạn văn bản mẫu (human sample) của người dùng để trích xuất tỷ lệ nhịp điệu và văn phong đối sánh.
5. Scene Splitter: Chia cảnh + word budget + SFX + modality
6. Quality Gate: Sentence variance check + retention hooks + 35-rule lint check + fact check
7. Compilation Commentator: Commentary ngắn cho MEO-style

### Giả định cần validate (scriptwriting)
- A7: Gemini Flash free tier đủ chất lượng cho Voice Writer (agent quan trọng nhất)
- A8: Few-shot style transfer hoạt động tốt khi chỉ cho 3 đoạn mẫu
- A9: Chunk-by-chunk generation (10-15 cảnh/lần) giữ nhất quán giọng văn
- A10: Bộ lọc từ cấm tiếng Việt (40+ patterns) đủ bao phủ
- A11: ZeroTTS phản ứng tốt với punctuation cues (em dash, ellipsis)

## Open questions (updated)

1. Niche đầu tiên?
2. Voiceover tiếng Việt hay tiếng Anh?
3. **Persona mặc định**: Nhà báo điều tra / Giáo sư / Người kể chuyện bên bếp lửa?
4. **Kênh tham chiếu**: Kênh VN/EN nào muốn app học giọng?
5. **Compilation commentary**: Voiceover bao nhiêu % cho mode MEO?
6. **LLM choice**: Gemini Flash cho Voice Writer hay cần model mạnh hơn?
7. Existing code?

## Selected direction

- **Mô hình tổng thể**: Dual-Mode Studio (Compilation MEO-style + Documentary Multi-Vault), ưu tiên khởi động trước với **Compilation Niche (Fails / Dashcam / Khoảnh khắc giật gân)** kết hợp pipeline tự động sinh commentary.
- **Ngôn ngữ mục tiêu**: Tiếng Việt (chạy ZeroTTS / MaziaoTTS giọng Việt, chi phí $0 trên PC Windows).
- **Persona kịch bản / Voiceover**: Nhà báo điều tra / Bình luận viên sắc bén (trực diện, gai góc, châm biếm nhẹ, dứt khoát, chống sáo rỗng AI).
- **Kiến trúc Scriptwriting**: Multi-Agent Persona Pipeline (Researcher, Architect, Voice Writer, Anti-AI Humanizer, Scene Splitter, Quality Gate).
- **Mức độ tự động**: Full-Auto từ quét nguyên liệu -> sinh kịch bản -> TTS -> biên tập video -> upload (hỗ trợ Batch Queue và Human Preview).

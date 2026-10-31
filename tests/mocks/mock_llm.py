"""
Mock LLM Adapter for Unit Tests & Offline Test Harness.
Contains deterministic responses for test suites without external API calls.
"""

from __future__ import annotations

import json
from autovideo.script.pipeline import BaseLLMAdapter


class MockLLMAdapter(BaseLLMAdapter):
    """
    Deterministic mock LLM adapter for offline tests and validation.
    Generates a 100% compliant 15-scene screenplay with:
    - 0 banned AI clichés
    - Cv >= 0.4
    - Cold Open 30s formula
    - 14 to 35 words per scene
    - Ending punctuation on every scene
    - Counterpoint SEO Package
    """

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        # If prompt is for SEO package
        if "LUẬT SONG TẤU ĐỐI NGHỊCH" in prompt or "TIÊU ĐỀ YOUTUBE" in prompt or "CHỦ ĐỀ VIDEO" in prompt:
            prompt_lower = prompt.lower()
            if any(k in prompt_lower for k in ("thiên nhiên", "nature", "wildlife", "động vật", "hổ", "tasmania", "sách đỏ")):
                return json.dumps({
                    "titles": [
                        "Hổ Tasmania: Bản Án Tuyệt Chủng Của Một Tuyệt Tác Tiến Hóa",
                        "Cái Chết Cô Độc Của Con Hổ Cuối Cùng Và Lời Thức Tỉnh Muộn Màng",
                        "Hồi Sinh Loài Tuyệt Chủng: Khoa Học ADN Liệu Có Thể Đảo Ngược Quá Khứ?",
                    ],
                    "description": (
                        "Phóng sự tài liệu chuyên sâu về số phận bi tráng của loài Hổ Tasmania (Thylacine) "
                        "và cá thể cuối cùng chết cóng trong sở thú năm 1936. Cuộc chiến sinh tồn, sai lầm lịch sử "
                        "và hành trình giải mã ADN hồi sinh loài của khoa học hiện đại.\n\n"
                        "#TasmanianTiger #WildlifeExtinction #NatureDocumentary"
                    ),
                    "hashtags": ["#TasmanianTiger", "#Thylacine", "#TuyetChung", "#SachDo", "#ThienNhien"],
                    "timestamps": [
                        "00:00 - Cái chết cô độc tại sở thú Beaumaris",
                        "01:00 - Tuyệt tác tiến hóa 4 triệu năm",
                        "02:30 - Thảm kịch săn tiền thưởng",
                        "03:45 - Giấc mơ hồi sinh từ ADN",
                    ],
                    "thumbnail_badge": "TUYỆT CHỦNG",
                    "thumbnail_hook": "CON THÚ CUỐI CÙNG",
                    "thumbnail_prompt": (
                        "Photorealistic 4K close-up of the last Tasmanian tiger in Beaumaris zoo cage at night, "
                        "striking reflective wild eyes, intense cold blue atmospheric rim lighting, empty bottom right safe zone."
                    ),
                    "counterpoint_notes": "Tiêu đề mang tính khoa học lịch sử trong khi Thumbnail khơi dậy nỗi ám ảnh tâm lý."
                }, ensure_ascii=False)

            return json.dumps({
                "titles": [
                    "Sự Cố Sập Kệ Kho 15 Triệu Đô: Lỗi Kỹ Thuật Hay Lòng Tham Quản Lý?",
                    "Điều Tra Thảm Họa Kệ Hàng Sụp Đổ: Bài Học Đắt Giá Ngành Logistics",
                    "Thảm Họa Nhà Kho Sập Liên Hoàn: 3 Giây Mất Trắng Toàn Bộ Hàng Hóa",
                ],
                "description": (
                    "Phân tích chi tiết nguyên nhân vụ tai nạn sập hệ thống kệ kho công nghiệp "
                    "gây thiệt hại hàng chục triệu USD. Góc nhìn điều tra từ kết cấu chịu tải, "
                    "sai phạm quy chuẩn an toàn và trách nhiệm quản lý vận hành.\n\n"
                    "#WarehouseFail #Logistics #SafetyIncident"
                ),
                "hashtags": ["#WarehouseFail", "#TaiNanLaoDong", "#LogisticsFail", "#AnToanKhoBai", "#DieuTra"],
                "timestamps": [
                    "00:00 - Cú sốc 15 triệu USD trong 3 giây",
                    "00:30 - Khám nghiệm hiện trường và tải trọng",
                    "01:15 - Kết luận điều tra và lỗ hổng giám sát",
                ],
                "thumbnail_badge": "SỰ CỐ KHO",
                "thumbnail_hook": "3 GIÂY MẤT TRẮNG",
                "thumbnail_prompt": (
                    "Photorealistic intense high-contrast dramatic CCTV angle: A massive industrial metal rack "
                    "buckling violently under tons of crushing pallets, sparks flying, forklift driver jumping in shock, "
                    "bold text in top left '3 GIÂY MẤT TRẮNG?', bottom-right 20% completely empty."
                ),
                "counterpoint_notes": (
                    "Tiêu đề cung cấp sự thật khách quan về con số 15 triệu USD và thực thể sự cố, "
                    "trong khi Thumbnail tập trung vào khoảnh khắc sụp đổ thót tim và câu hỏi tâm lý."
                ),
            }, ensure_ascii=False)

        # Default fallback: return structured scenes JSON
        scenes_data = [
            {
                "scene_id": "SCENE_001",
                "chapter_index": 1,
                "text": "Mười lăm triệu đô la hàng hóa tan thành mây khói chỉ sau một tiếng rắc kinh hoàng vang lên giữa ca làm việc đêm.",
                "duration_sec": 5.0,
                "word_count": 24,
                "visual_prompt": "CCTV high-angle shot inside a massive automated warehouse with towering metal racks.",
                "keywords": {"vi": ["sập kho hàng", "cctv kho"], "en": ["warehouse collapse cctv footage", "catastrophic failure"], "zh": ["仓库倒塌监控", "工业事故"]},
                "sfx_cue": "low_impact_thud",
                "camera_angle": "Wide bird-eye CCTV",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_002",
                "chapter_index": 1,
                "text": "Con số thiệt hại đó tương đương toàn bộ ngân sách vận hành của ba nhà máy dệt may cỡ vừa trong suốt năm năm ròng rã.",
                "duration_sec": 7.5,
                "word_count": 25,
                "visual_prompt": "Close-up of a twisted steel rack connector beam showing metal stress fractures.",
                "keywords": {"vi": ["thanh giằng kim loại", "nứt gãy"], "en": ["metal rack beam shear fracture close-up", "material failure"], "zh": ["金属货架断裂", "应力集中"]},
                "sfx_cue": "metal_groan_creak",
                "camera_angle": "Extreme close-up macro",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_003",
                "chapter_index": 1,
                "text": "Nhưng liệu đây là lỗi ngẫu nhiên của tài xế xe nâng, hay là quả bom nổ chậm do ban quản lý cố tình phớt lờ tải trọng cho phép?",
                "duration_sec": 7.5,
                "word_count": 27,
                "visual_prompt": "Slow tracking shot along a dark warehouse aisle showing overloaded pallets bowing precariously.",
                "keywords": {"vi": ["quá tải kệ hàng", "xe nâng va chạm"], "en": ["overloaded warehouse racking system bending danger", "forklift collision"], "zh": ["超载货架弯曲", "叉车碰撞"]},
                "sfx_cue": "heartbeat_suspense_drone",
                "camera_angle": "Low Dutch angle tracking",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_004",
                "chapter_index": 1,
                "text": "Báo cáo giám định kỹ thuật ban đầu lập tức chỉ ra lỗ hổng chết người ở khớp nối chịu lực số bảy.",
                "duration_sec": 5.0,
                "word_count": 20,
                "visual_prompt": "Blueprint technical schematic overlaying forensic photos of sheared anchor bolts on concrete floor.",
                "keywords": {"vi": ["giám định kỹ thuật", "bu lông sàn"], "en": ["structural engineering forensic report sheared anchor bolts", "schematic diagram"], "zh": ["地脚螺栓剪切", "工程鉴定"]},
                "sfx_cue": "subtle_whoosh_transition",
                "camera_angle": "Over-the-shoulder document inspection",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_005",
                "chapter_index": 1,
                "text": "Chiếc bu lông neo sàn mười tám ly đã bị rỉ sét ăn mòn gần một nửa sau sáu năm ẩm mốc.",
                "duration_sec": 5.0,
                "word_count": 20,
                "visual_prompt": "Macro zoom on heavily oxidized, rusted bolt threads with flaky orange rust crumbling away.",
                "keywords": {"vi": ["bu lông rỉ sét", "ăn mòn kim loại"], "en": ["corroded rusted industrial fastener macro", "heavy oxidation damage"], "zh": ["严重锈蚀螺丝", "金属腐蚀"]},
                "sfx_cue": "metal_tick_stress",
                "camera_angle": "Extreme close-up macro",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_006",
                "chapter_index": 1,
                "text": "Kim loại bị xé toạc. Áp lực dồn nén cực hạn lập tức bẻ cong toàn bộ thanh giằng chịu lực chính và giật sập ba nhịp kệ đầu tiên.",
                "duration_sec": 7.5,
                "word_count": 30,
                "visual_prompt": "Wide perspective showing entire warehouse aisle collapsing sequentially.",
                "keywords": {"vi": ["hiệu ứng domino", "sập liên hoàn"], "en": ["warehouse domino collapse cascade", "aerial destruction"], "zh": ["骨牌效应倒塌", "仓储连环倾覆"]},
                "sfx_cue": "distant_rolling_thunder",
                "camera_angle": "Wide bird-eye view",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_007",
                "chapter_index": 1,
                "text": "Hiệu ứng domino bùng nổ khi từng dãy kệ cao mười hai mét liên tiếp ngả nghiêng xuống sàn.",
                "duration_sec": 5.0,
                "word_count": 19,
                "visual_prompt": "Dust clouds enveloping the dark warehouse floor as workers sprint toward emergency exits.",
                "keywords": {"vi": ["bụi mù mịt", "công nhân chạy nạn"], "en": ["dust cloud explosion warehouse workers fleeing", "emergency evacuation"], "zh": ["烟尘弥漫", "工人逃生"]},
                "sfx_cue": "heavy_rubble_impact_alarm",
                "camera_angle": "Tracking dashcam view",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_008",
                "chapter_index": 1,
                "text": "Bụi bốc mù mịt. Sáu công nhân làm ca đêm chỉ có vỏn vẹn bốn giây để lao về phía cửa thoát hiểm trước khi hàng tấn gốm sứ đổ sụp.",
                "duration_sec": 7.5,
                "word_count": 31,
                "visual_prompt": "Flashing red strobe emergency light reflecting off jagged twisted metal beams.",
                "keywords": {"vi": ["còi báo động", "đèn nhấp nháy"], "en": ["flashing red emergency siren rubble", "strobe light warehouse"], "zh": ["警报闪烁", "废墟警笛"]},
                "sfx_cue": "industrial_siren_echo",
                "camera_angle": "Low Dutch tilt",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_009",
                "chapter_index": 1,
                "text": "Tiếng còi báo động réo vang giữa đống đổ nát ngập tràn mảnh vỡ vụn.",
                "duration_sec": 5.0,
                "word_count": 15,
                "visual_prompt": "Rescue workers shining searchlights on the fortified overhead guard of the trapped forklift.",
                "keywords": {"vi": ["cứu hộ nhà kho", "xe nâng kẹt"], "en": ["emergency services searching rubble warehouse forklift overhead guard", "flashlight beam"], "zh": ["搜救废墟", "叉车驾驶舱"]},
                "sfx_cue": "distant_police_siren",
                "camera_angle": "Medium handheld documentary",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_010",
                "chapter_index": 1,
                "text": "Khung bảo vệ thép đã cứu mạng người lái xe một cách thần kỳ. Nhưng bài toán điều tra trách nhiệm pháp lý lúc này mới thực sự bắt đầu.",
                "duration_sec": 7.5,
                "word_count": 28,
                "visual_prompt": "Forensic investigator placing yellow numbered evidence markers next to a cracked forklift mast.",
                "keywords": {"vi": ["điều tra pháp lý", "dấu vết hiện trường"], "en": ["forensic investigator placing evidence markers on warehouse floor", "incident reconstruction"], "zh": ["事故现场调查", "证据标牌"]},
                "sfx_cue": "camera_shutter_click",
                "camera_angle": "Close-up tilted marker",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_011",
                "chapter_index": 2,
                "text": "Hồ sơ kiểm định an toàn ba tháng trước bất ngờ biến mất bí ẩn khỏi máy chủ công ty.",
                "duration_sec": 5.0,
                "word_count": 18,
                "visual_prompt": "Computer screen displaying 'File Not Found 404' error in an empty corporate office at night.",
                "keywords": {"vi": ["mất dữ liệu", "màn hình máy tính"], "en": ["computer monitor displaying error message dark empty office", "corporate coverup"], "zh": ["电脑屏幕错误", "数据丢失"]},
                "sfx_cue": "glitch_digital_hum",
                "camera_angle": "Screen reflection close-up",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_012",
                "chapter_index": 2,
                "text": "Sự thật dần lộ diện khi camera dự phòng ghi lại cảnh quản lý kho chỉ đạo chất vượt tải bốn mươi phần trăm để tiết kiệm tiền thuê bãi.",
                "duration_sec": 7.5,
                "word_count": 29,
                "visual_prompt": "Grainy black-and-white security tape showing warehouse manager arguing with logistics forklift driver.",
                "keywords": {"vi": ["camera an ninh", "tranh cãi quá tải"], "en": ["grainy security footage heated argument warehouse office manager", "tampering evidence"], "zh": ["监控回放争执", "违规超载指令"]},
                "sfx_cue": "tape_rewind_static",
                "camera_angle": "High corner surveillance",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_013",
                "chapter_index": 2,
                "text": "Lợi nhuận ngắn hạn của doanh nghiệp đã bị đánh đổi bằng chính sinh mạng người lao động vô tội.",
                "duration_sec": 5.0,
                "word_count": 20,
                "visual_prompt": "Stacks of printed company financial reports stamped with red 'CONFIDENTIAL' watermark.",
                "keywords": {"vi": ["tài liệu mật", "dấu mộc đỏ"], "en": ["confidential financial audit documents with red stamp", "corporate greed"], "zh": ["机密审计文件", "红色印章"]},
                "sfx_cue": "heavy_stamp_thud",
                "camera_angle": "Flat lay top-down macro",
                "preferred_vault": "stock",
            },
            {
                "scene_id": "SCENE_014",
                "chapter_index": 2,
                "text": "Lệnh trừng phạt thích đáng. Tòa án phong tỏa toàn bộ tài sản doanh nghiệp và truy tố hình sự ba nhà thầu phụ chịu trách nhiệm thẩm định an toàn.",
                "duration_sec": 7.5,
                "word_count": 31,
                "visual_prompt": "Bulldozer scraping crushed luxury goods and wine bottles into scrap containers.",
                "keywords": {"vi": ["tiêu hủy hàng hóa", "xe ủi dọn kho"], "en": ["heavy machinery crushing destroyed luxury cargo into scrap bins", "total loss salvage"], "zh": ["重型机械清理残骸", "报废货物"]},
                "sfx_cue": "heavy_engine_rumble_metal_groan",
                "camera_angle": "Telephoto slow pan",
                "preferred_vault": "douyin",
            },
            {
                "scene_id": "SCENE_015",
                "chapter_index": 2,
                "text": "Lòng tham đã trả giá. Không có tai nạn nào là ngẫu nhiên khi kỷ luật an toàn đã bị rẻ rúng ngay từ những nét vẽ thiết kế đầu tiên.",
                "duration_sec": 7.5,
                "word_count": 31,
                "visual_prompt": "Empty abandoned cleared warehouse floor with yellow hazard caution tape fluttering in wind.",
                "keywords": {"vi": ["bài học kho bãi", "dây cảnh báo màu vàng"], "en": ["yellow caution hazard tape fluttering inside empty giant warehouse", "cinematic ending shot"], "zh": ["空荡仓库警戒线", "终局反思"]},
                "sfx_cue": "somber_drone_fadeout",
                "camera_angle": "Slow cinematic pull back wide",
                "preferred_vault": "douyin",
            },
        ]
        return json.dumps(scenes_data, ensure_ascii=False)

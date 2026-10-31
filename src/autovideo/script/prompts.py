"""
Persona System, Prompt Templates, and Editorial DNA for Scriptwriting Brain (REQ-B1-01, REQ-B1-02).
Defines system instructions and templates for the 7 specialized agents:
1. Researcher
2. Story Architect (30s Cold Open)
3. Voice Writer (Investigative / Sharp Commentary)
4. Anti-AI Humanizer (35 Patterns & Burstiness)
5. Scene Splitter & Word Budgeter (4s-8s atomic scenes, keywords vi/en/zh)
6. Quality Gate
7. Compilation Commentator (15-25s incident breakdown)
Also encapsulates Cold Open 30-Second Formula and Counterpoint Law for Title & Thumbnail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ADR-019: keywords/visual prompts must describe footage that actually exists on YouTube.
FILMABLE_FOOTAGE_RULE = (
    "- QUY TẮC FOOTAGE THỰC (ADR-019): MỌI từ khóa 'keywords.en' BẮT BUỘC chứa tên chủ thể tiếng Anh đầy đủ "
    "và mô tả cảnh QUAY THỰC TẾ có thể tìm thấy trên YouTube (chủ thể đang làm gì, ở đâu). "
    "TUYỆT ĐỐI KHÔNG yêu cầu cảnh không thể quay: ảnh chụp MRI/X-quang, mô hình 3D/CGI, màn hình máy tính, "
    "phòng thí nghiệm, kính hiển vi, sơ đồ, biểu đồ, hoạt hình. Nếu lời thoại nói về khái niệm trừu tượng "
    "(giải phẫu, não bộ, số liệu, nghiên cứu), hãy chọn cảnh quay thực tế minh hoạ hệ quả của nó "
    "(vd: 'spotted hyena chewing bone' thay cho 'hyena skull scan'; 'spotted hyena clan greeting' thay cho "
    "'hyena brain mri'). 'visual_prompt' cũng phải tuân thủ quy tắc này.\n"
)

COLD_OPEN_RULES = """
=== CÔNG THỨC 30 GIÂY MỞ ĐẦU (COLD OPEN RETENTION FORMULA) ===
1. Nhịp 1 (0–5 giây): CÚ SỐC SỐ LIỆU & TRẢ LỜI THUMBNAIL
   - Đi thẳng vào một con số chấn động, thị giác bất ngờ hoặc nghịch lý trung tâm của chủ đề.
   - Lập tức kết nối hoặc giải đáp lời hứa hiển thị trên ảnh bìa Thumbnail.
   - CẤM chào hỏi, cấm triết lý chung chung ("Trong dòng chảy lịch sử...", "Từ xa xưa...").
2. Nhịp 2 (5–15 giây): ĐẬP TAN NGỘ NHẬN & QUY ĐỔI SỨC MUA
   - Phá vỡ góc nhìn sách vở, phổ thông hay cách hiểu sai lầm thường thấy về chủ đề.
   - Quy đổi ngay thiệt hại, chi phí, quy mô hoặc con số sang mức sống hoặc hình ảnh thực tế quen thuộc.
3. Nhịp 3 (15–30 giây): LUẬN ĐỀ ĐIỀU TRA & MÓC CÂU MỞ (OPEN LOOP)
   - Nêu lên câu hỏi bản chất, vấn đề cốt lõi hoặc mâu thuẫn trung tâm dẫn dắt toàn bộ nội dung.
   - Kết thúc nhịp mở đầu bằng một câu hỏi bỏ ngỏ hoặc tình thế khẩn cấp để kéo người xem sang Hồi 1.
* Lưu ý: Phong cách thể hiện cụ thể (điều tra, khoa học, lịch sử, đời sống...) do Skill Niche đang kích hoạt dẫn dắt.
"""

COUNTERPOINT_RULES = """
=== LUẬT SONG TẤU ĐỐI NGHỊCH (COUNTERPOINT LAW: TITLE & THUMBNAIL) ===
1. TIÊU ĐỀ YOUTUBE (LÝ TÍNH & THÔNG TIN):
   - Độ dài: 50 – 70 ký tự.
   - Dồn từ khóa quan trọng và thực thể chính vào 35 ký tự đầu tiên để không bị che khuất trên điện thoại.
   - Trả lời rõ ràng câu hỏi: "Cái gì? Ai? Khi nào? Tại sao?" dưới góc nhìn điều tra hoặc phân tích chuyên sâu.
2. THUMBNAIL (CẢM XÚC & NGHỊCH LÝ GAY GẮT):
   - Tập trung 100% vào sự đối lập, căng thẳng cực điểm hoặc câu hỏi nhức nhối kích hoạt tò mò cao độ.
   - Chừa trống góc dưới bên phải (15% – 20% khung hình) để nhãn thời lượng video của YouTube không đè lên chữ.
3. QUY TẮC BẤT DI BẤT DỊCH:
   - Tiêu đề và Thumbnail KHÔNG BAO GIỜ lặp lại từ của nhau.
   - Tiêu đề nói "Sự thật khách quan", Thumbnail kích hoạt "Tò mò tâm lý".
"""

DOCUMENTARY_RULES = """
=== CÔNG THỨC PHIM TÀI LIỆU LỊCH SỬ & KỲ BÍ CỔ ĐẠI ===
(Khung tham chiếu mẫu - Quy tắc chi tiết của từng ngách được nạp động từ skills/<skill_id>/skill.yaml)
1. CẤU TRÚC 5 HỒI ĐIỆN ẢNH:
   - Hồi 1 (0–45s) - Cold Open Nghịch Lý: Đặt tương phản cực đại để kéo người xem vào câu chuyện.
   - Hồi 2 (45s–3m) - Khởi Nguyên: Bối cảnh, bi kịch hoặc biến cố thúc đẩy bước ngoặt.
   - Hồi 3 (3m–15m) - Thăng Trầm: Diễn biến then chốt, cơ chế vận hành, xung đột đỉnh điểm.
   - Hồi 4 (15m–25m) - Bước Ngoặt & Giải Mã: Nghịch lý nhân tính hoặc góc khuất chưa được khám phá.
   - Hồi 5 (Kết) - Đúc Kết Triết Học & Móc Câu Mở: Bài học cho hậu thế, câu hỏi chưa có lời đáp.
2. PACING HÌNH ẢNH:
   - Thời lượng mỗi cảnh: 3.0s – 6.0s (tối đa 7.0s), cắt nhịp nhàng theo danh từ trong lời thoại.
3. NGUYÊN TẮC LIỀN MẠCH THỊ GIÁC (VISUAL CONTINUITY & SPATIAL CLUSTERING):
   - Nhóm 3-5 cảnh liên tiếp (15s-30s) vào cùng 1 Cụm Bối Cảnh (environment_id).
   - Tránh nhảy địa điểm đột ngột giữa các cảnh ngắn 3-5s.
   - Biến thiên cỡ cảnh: Wide (Toàn) -> Medium (Trung) -> Closeup (Cận) -> Detail (Đặc tả).
   - Duy trì dải âm thanh môi trường (Ambient Audio Bridge) xuyên suốt toàn bộ cụm.
"""



@dataclass
class AgentPersona:
    """Definition of an individual agent's role and system instructions."""

    agent_id: str
    name: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 2048


class PersonaRegistry:
    """Registry containing specialized agent personas for scriptwriting with dynamic registration."""

    _custom_personas: Dict[str, AgentPersona] = {}

    @classmethod
    def register_persona(cls, persona: AgentPersona) -> None:
        """Register or override a custom persona dynamically."""
        cls._custom_personas[persona.agent_id] = persona

    @classmethod
    def get_persona(cls, agent_id: str) -> Optional[AgentPersona]:
        """Retrieve a persona by ID, checking custom registrations first."""
        if agent_id in cls._custom_personas:
            return cls._custom_personas[agent_id]
        return cls.get_all_personas().get(agent_id)

    @classmethod
    def clear_custom_personas(cls) -> None:
        """Clear custom registered personas."""
        cls._custom_personas.clear()

    @staticmethod
    def get_researcher() -> AgentPersona:
        return AgentPersona(
            agent_id="researcher",
            name="Data & Incident Researcher",
            system_prompt=(
                "Bạn là Nhà Nghiên cứu Dữ liệu & Sự kiện Phóng sự Điều tra.\n"
                "Nhiệm vụ của bạn là đào sâu các chi tiết kỹ thuật, số liệu chấn động, "
                "mốc thời gian, cơ chế vật lý/kinh tế và danh tính thực tế.\n"
                "Quy tắc:\n"
                "- Cung cấp sự thật trần trụi, có số liệu đối chiếu.\n"
                "- Gọi đúng tên thật, địa danh cụ thể (không nói chung chung 'một công ty nọ').\n"
                "- Quy đổi các con số trừu tượng thành thước đo đời sống hàng ngày.\n"
                "- CẤM bịa đặt nguồn tin hoặc dùng từ sáo rỗng."
            ),
            temperature=0.3,
        )

    @staticmethod
    def get_architect() -> AgentPersona:
        return AgentPersona(
            agent_id="architect",
            name="Story & Act Architect",
            system_prompt=(
                "Bạn là Kiến trúc sư Cấu trúc Phóng sự (Story Architect).\n"
                "Nhiệm vụ của bạn là thiết kế dàn ý tổng thể chia theo các Hồi (Acts).\n"
                "Quy tắc cốt lõi:\n"
                "- Mỗi Hồi chứa TỐI ĐA 15 phân cảnh.\n"
                "- Áp dụng chuẩn xác Công thức 30 Giây Cold Open ở Hồi mở đầu:\n"
                "  + 0-5s: Cú sốc số liệu / phản hồi Thumbnail\n"
                "  + 5-15s: Phá tan ngộ nhận / quy đổi sức mua\n"
                "  + 15-30s: Luận đề điều tra / Open Loop\n"
                "- Duy trì Mạch nối cuốn chiếu: cuối mỗi Hồi phải có câu móc dẫn chuyển tiếp mượt sang Hồi sau."
            ),
            temperature=0.5,
        )

    @staticmethod
    def get_voice_writer() -> AgentPersona:
        return AgentPersona(
            agent_id="voice_writer",
            name="Investigative Voice Writer",
            system_prompt=(
                "Bạn là Biên kịch Thuyết minh mang Persona 'Nhà báo điều tra / Bình luận viên sắc bén'.\n"
                "Phong cách: Trực diện, hơi gai góc, đanh thép, không khoan nhượng, giàu nhịp điệu.\n"
                "Quy tắc viết:\n"
                "- Viết câu ngắn gọn, dứt khoát xen kẽ câu dài phân tích sâu.\n"
                "- Cấu trúc mỗi cảnh 6-8s: Câu 1 nêu trực diện diễn biến/cơ chế; Câu 2 rút ra hệ quả/móc câu.\n"
                "- CẤM tuyệt đối mọi từ chào hỏi, dẫn nhập rỗng tuếch, hoặc giọng điệu trợ lý AI thảo mai."
            ),
            temperature=0.7,
        )

    @staticmethod
    def get_humanizer() -> AgentPersona:
        return AgentPersona(
            agent_id="humanizer",
            name="Anti-AI Humanizer & Rhythm Polisher",
            system_prompt=(
                "Bạn là Chuyên gia Khử giọng AI & Tinh chỉnh Nhịp thở (Anti-AI Humanizer).\n"
                "Nhiệm vụ của bạn là quét toàn bộ bản thảo và thực thi 2 việc:\n"
                "1. TRIỆT TIÊU 100% 35 pattern sáo rỗng AI (Wikipedia AI Cleanup):\n"
                "   'bức tranh toàn cảnh', 'minh chứng hùng hồn', 'trong dòng chảy lịch sử', 'hơn nữa', "
                "   'không chỉ X mà còn Y', 'tóm lại', 'nhìn chung', 'đóng vai trò quan trọng', 'vô hình trung'...\n"
                "2. TẠO ĐỘ BIẾN THIÊN ĐỘ DÀI CÂU (BURSTINESS Cv >= 0.4):\n"
                "   Xen kẽ các câu cực ngắn (3-5 từ) gây chú ý với các câu dài (20-30 từ) giàu thông tin.\n"
                "   KHÔNG BAO GIỜ để 3 câu liên tiếp có cùng độ dài (chênh lệch <= 3 từ)."
            ),
            temperature=0.4,
        )

    @staticmethod
    def get_scene_splitter() -> AgentPersona:
        return AgentPersona(
            agent_id="scene_splitter",
            name="Scene Splitter & Word Budgeter",
            system_prompt=(
                "Bạn là Đạo diễn Phân cảnh & Cân đối Ngân sách Từ vựng (Scene Splitter).\n"
                "Nhiệm vụ:\n"
                "- Bẻ nhỏ kịch bản thành các Atomic Scenes thời lượng 4s đến 8s.\n"
                "- Áp dụng Word Budget nghiêm ngặt theo tốc độ đọc 2.5 - 3.2 từ/s:\n"
                "  + Cảnh 4s-5s: 14 - 24 từ (1 câu dứt khoát).\n"
                "  + Cảnh 6s-8s: 25 - 35 từ (2 câu hoàn chỉnh).\n"
                "- Mỗi cảnh PHẢI kết thúc bằng dấu chấm (., !, ?, …) hoàn chỉnh ngữ pháp.\n"
                "- Trích xuất 3 bộ từ khóa tìm kiếm Footage: tiếng Việt (vi), tiếng Anh (en cho stock), tiếng Trung (zh cho Douyin/Bilibili).\n"
                "- Gán SFX cue (tiếng đổ vỡ, báo động, tiếng tim đập, swoosh) và góc quay camera (Close-up, Wide, Pan, Aerial)."
            ),
            temperature=0.3,
        )

    @staticmethod
    def get_quality_gate() -> AgentPersona:
        return AgentPersona(
            agent_id="quality_gate",
            name="Quality Gate Auditor",
            system_prompt=(
                "Bạn là Kiểm toán viên Chất lượng Kịch bản độc lập (Quality Gate).\n"
                "Nhiệm vụ:\n"
                "- Thẩm định toàn bộ kịch bản trước khi chuyển giao sang Bước 2 (Lồng tiếng & Dựng).\n"
                "- Kiểm tra: Danh sách đen 35 từ cấm, hệ số Cv >= 0.4, ngân sách từ 14-35 từ/cảnh, "
                "dấu câu kết thúc, cấu trúc Cold Open 30s và tính xác thực của tên riêng/số liệu.\n"
                "- Phê duyệt (PASS) hoặc trả lời lỗi chi tiết kèm hướng sửa (REVISE)."
            ),
            temperature=0.1,
        )

    @staticmethod
    def get_commentator() -> AgentPersona:
        return AgentPersona(
            agent_id="commentator",
            name="Incident & Event Commentator",
            system_prompt=(
                "Bạn là Bình luận viên Tình huống Video (Compilation / Event Commentator).\n"
                "Chuyên trách phân tích các tình huống, biến cố, sự cố thực tế với nhịp điệu dồn dập.\n"
                "Độ dài mỗi đoạn: 15-25 giây (tương đương 3-4 cảnh ngắn gộp lại).\n"
                "Cấu trúc bình luận:\n"
                "1. Điểm khởi phát sai sót hoặc hành động bước ngoặt (0-5s);\n"
                "2. Cơ chế dây chuyền dẫn đến kết quả (5-15s);\n"
                "3. Bài học đắt giá hoặc nhận xét đanh thép, sâu cay (15-25s)."
            ),
            temperature=0.6,
        )

    @staticmethod
    def get_historical_storyteller() -> AgentPersona:
        return AgentPersona(
            agent_id="historical_storyteller",
            name="Documentary & Historical Storyteller",
            system_prompt=(
                "Bạn là Đạo diễn & Biên kịch Phim tài liệu Lịch sử & Văn hóa chuyên sâu.\n"
                "Phong cách: Tự sự trầm mặc, hào hùng, bi tráng, giàu tính điện ảnh và gợi mở triết học.\n"
                "Quy tắc kịch bản:\n"
                "- Bắt đầu bằng nghịch lý tương phản dữ dội ở 30 giây đầu.\n"
                "- Chia cảnh nhịp nhàng 3.0s đến 6.0s (12-25 từ/cảnh), kết thúc bằng dấu chấm hoàn chỉnh.\n"
                "- Visual Prompt mô tả chi tiết bối cảnh, góc máy điện ảnh, không khí và ánh sáng.\n"
                "- Cung cấp bộ 3 từ khóa tìm kiếm: vi (tiếng Việt), zh (tiếng Trung cho kho tư liệu Á Đông), en (tiếng Anh cho kho tư liệu quốc tế).\n"
                "- Gán SFX cue sống động phù hợp bối cảnh lịch sử."
            ),
            temperature=0.6,
        )

    @staticmethod
    def get_nature_storyteller() -> AgentPersona:
        return AgentPersona(
            agent_id="nature_storyteller",
            name="Wildlife & Nature Documentary Storyteller",
            system_prompt=(
                "Bạn là Đạo diễn Phóng sự Thiên nhiên, Động vật Hoang dã & Sinh thái.\n"
                "Phong cách: Tự sự trần trụi, bi tráng, tôn trọng sự khắc nghiệt của tự nhiên, có chiều sâu triết học.\n"
                "Quy tắc biên kịch:\n"
                "- Tổ chức kịch bản theo các Cụm Bối Cảnh (Scene Clusters) kéo dài 15s-30s với cùng 1 environment_id.\n"
                "- Tuân thủ chuỗi thang cỡ cảnh Toàn - Trung - Cận - Đặc tả (Wide -> Medium -> Closeup -> Detail) để chống rời rạc.\n"
                "- Khởi đầu bằng nghịch lý hoặc cú sốc sinh học ở 30 giây đầu.\n"
                "- Sinh từ khóa tìm kiếm: vi, en (kho stock quốc tế), zh (kho tư liệu b-roll).\n"
                "- Gán SFX môi trường và âm thanh sinh vật chân thực."
            ),
            temperature=0.6,
        )

    @classmethod
    def get_all_personas(cls) -> Dict[str, AgentPersona]:
        personas = {
            "researcher": cls.get_researcher(),
            "architect": cls.get_architect(),
            "voice_writer": cls.get_voice_writer(),
            "humanizer": cls.get_humanizer(),
            "scene_splitter": cls.get_scene_splitter(),
            "quality_gate": cls.get_quality_gate(),
            "commentator": cls.get_commentator(),
            "historical_storyteller": cls.get_historical_storyteller(),
            "nature_storyteller": cls.get_nature_storyteller(),
        }
        personas.update(cls._custom_personas)
        return personas


class PromptCompiler:
    """
    Compiles complete prompts injecting topic, niche skill context,
    Cold Open formulas, and editorial constraints.
    """

    def __init__(self, registry: Optional[PersonaRegistry] = None) -> None:
        self.registry = registry or PersonaRegistry()

    def build_architect_prompt(
        self,
        topic: str,
        skill_name: str = "Tài liệu chuyên đề",
        target_duration_min: float = 3.0,
        target_scenes: int = 15,
        chapter_index: int = 1,
        total_chapters: int = 1,
        creative_guidance: Optional[str] = None,
    ) -> str:
        """Constructs prompt for the Story Architect to build the act blueprint in JSON."""
        header_context = (
            f"CHỦ ĐỀ: {topic}\n"
            f"NGÁCH NỘI DUNG (SKILL): {skill_name}\n"
            f"THỜI LƯỢNG MỤC TIÊU CỦA HỒI NÀY: {target_duration_min} phút (~{target_scenes} phân cảnh)\n"
            f"HỒI: {chapter_index}/{total_chapters}\n\n"
        )
        if creative_guidance:
            header_context += (
                f"=== CHỈ DẪN BIÊN TẬP & ĐẶC TẢ SKILL NICHE (ACTIVE SKILL GUIDANCE) ===\n"
                f"{creative_guidance.strip()}\n\n"
            )

        if chapter_index == 1:
            rules_section = (
                f"{COLD_OPEN_RULES}\n\n"
                "QUY TẮC VIẾT LỜI THUYẾT MINH (VOICE-OVER):\n"
                "- Bám sát 100% phong cách dẫn chuyện, trường từ vựng và triết lý trong Chỉ Dẫn Skill Niche phía trên.\n"
                "- Mỗi cảnh kéo dài 4s - 8s.\n"
                "- Cảnh 4s-5s: 1 câu dứt khoát (14-24 từ).\n"
                "- Cảnh 6s-8s: 2 câu hoàn chỉnh (25-35 từ).\n"
                "- Cảnh 1 đến 3 bắt buộc tuân thủ chuẩn 3 nhịp Cold Open (Nhịp 1: Cú sốc / Cận cảnh mở; Nhịp 2: Đập tan ngộ nhận; Nhịp 3: Câu hỏi mở).\n"
                "- BẮT BUỘC cung cấp từ khóa tiếng Anh ('keywords.en'): Mỗi phân cảnh phải có từ khóa tiếng Anh từ 3 đến 6 từ, được viết CHUẨN XÁC cho công cụ tìm kiếm video tư liệu (YouTube / Stock B-roll). Định dạng chuẩn: [Tên chủ thể tiếng Anh] + [Hành động hoặc thực thể thị giác cụ thể]. Ví dụ đúng: 'spotted hyena crushing bone close up', 'spotted hyena pack hunting savanna', 'spotted hyena feeding on carcass'. Tuyệt đối KHÔNG viết từ khóa mơ hồ, chung chung hay quá ngắn.\n"
                f"{FILMABLE_FOOTAGE_RULE}"
                "- BẮT BUỘC cung cấp từ khóa tiếng Trung ('zh') tương ứng.\n"
                "- Cung cấp bối cảnh không gian ('environment_id' và 'cluster_id') để đảm bảo tính liền mạch thị giác.\n\n"
            )
        else:
            rules_section = (
                f"ĐÂY LÀ HỒI THỨ {chapter_index} TIẾP THEO CỦA CÂU CHUYỆN (KHÔNG PHẢI MỞ ĐẦU VIDEO):\n"
                "- TUYỆT ĐỐI KHÔNG viết lại Cold Open mở đầu hay nhắc lại câu giật gân ở đầu video.\n"
                "- Bám sát 100% phong cách dẫn chuyện, trường từ vựng và triết lý trong Chỉ Dẫn Skill Niche phía trên.\n"
                "- Đi sâu vào diễn biến chi tiết, phân tích nguyên nhân, hậu quả và bài học / góc nhìn khoa học theo đúng ngách.\n"
                "- Mỗi cảnh kéo dài 4s - 8s (20-35 từ).\n"
                "- BẮT BUỘC cung cấp từ khóa tiếng Anh ('keywords.en'): Mỗi phân cảnh có từ khóa 3-6 từ chuẩn tìm kiếm video B-roll ([Chủ thể] + [Hành động / Thực thể thị giác cụ thể], ví dụ: 'spotted hyena mother cubs den', 'spotted hyena vs lion fight').\n"
                f"{FILMABLE_FOOTAGE_RULE}"
                "- Cung cấp bối cảnh không gian ('environment_id' và 'cluster_id') để đảm bảo tính liền mạch thị giác.\n\n"
            )

        return (
            f"{header_context}"
            f"{rules_section}"
            "YÊU CẦU ĐẦU RA BẮT BUỘC:\n"
            "Chỉ trả về DUY NHẤT một mảng JSON các phân cảnh (trong khối ```json ... ``` hoặc định dạng JSON thuần túy).\n"
            "TUYỆT ĐỐI KHÔNG viết thêm bất kỳ lời chào, tiêu đề hay giải thích nào bên ngoài mảng JSON.\n\n"
            "CẤU TRÚC JSON MẪU:\n"
            "[\n"
            "  {\n"
            '    "scene_id": "SCENE_001",\n'
            '    "chapter_index": 1,\n'
            '    "cluster_id": "cluster_01",\n'
            '    "environment_id": "rainforest_night",\n'
            '    "text": "Lời thuyết minh tiếng Việt cho cảnh 1 (14-35 từ)...",\n'
            '    "duration_sec": 5.0,\n'
            '    "word_count": 18,\n'
            '    "visual_prompt": "Mô tả chi tiết hình ảnh video cần tìm...",\n'
            '    "camera_scale": "Wide",\n'
            '    "virtual_reframe": null,\n'
            '    "keywords": {\n'
            '      "vi": ["từ khóa tiếng việt 1", "từ khóa 2"],\n'
            '      "en": ["english search keyword 1", "keyword 2"],\n'
            '      "zh": ["中文关键词"]\n'
            "    },\n"
            '    "sfx_cue": "ambient_wind",\n'
            '    "camera_angle": "Wide 35mm",\n'
            '    "preferred_vault": "stock"\n'
            "  }\n"
            "]"
        )

    def build_voice_writer_prompt(
        self,
        act_outline: str,
        topic: str,
        research_notes: str = "",
        rolling_context: str = "",
    ) -> str:
        """Constructs prompt for the Voice Writer to draft narration scenes."""
        prompt = (
            f"CHỦ ĐỀ: {topic}\n\n"
            f"DÀN Ý HỒI CẦN VIẾT:\n{act_outline}\n\n"
        )
        if research_notes:
            prompt += f"DỮ LIỆU ĐIỀU TRA / SỰ KIỆN:\n{research_notes}\n\n"
        if rolling_context:
            prompt += f"MẠCH NỐI TỪ HỒI TRƯỚC (GỐI ĐẦU CUỐN CHIẾU):\n{rolling_context}\n\n"
        prompt += (
            "HÃY VIẾT LỜI THUYẾT MINH:\n"
            "- Giọng văn đanh thép, trực diện, không sáo rỗng.\n"
            "- Mỗi cảnh chuẩn bị cho thời lượng 4s-8s.\n"
            "- Cảnh 4s-5s: 1 câu dứt khoát (14-24 từ).\n"
            "- Cảnh 6s-8s: 2 câu hoàn chỉnh (25-35 từ).\n"
            "- Mỗi câu kết thúc bằng dấu chấm rõ ràng."
        )
        return prompt

    def build_seo_prompt(
        self,
        topic: str,
        screenplay_summary: str,
        creative_guidance: Optional[str] = None,
    ) -> str:
        """Constructs prompt for Counterpoint Title and Thumbnail generation using active skill rules."""
        guidance_section = ""
        if creative_guidance:
            guidance_section = (
                f"=== CHỈ DẪN SEO & THUMBNAIL TỪ SKILL NICHE ===\n"
                f"{creative_guidance.strip()}\n\n"
            )

        return (
            f"CHỦ ĐỀ VIDEO: {topic}\n"
            f"TÓM TẮT NỘI DUNG PHIM: {screenplay_summary}\n\n"
            f"{guidance_section}"
            f"{COUNTERPOINT_RULES}\n\n"
            "YÊU CẦU ĐẦU RA BẮT BUỘC:\n"
            "Chỉ trả về DUY NHẤT một JSON object (trong khối ```json ... ``` hoặc định dạng JSON thuần túy).\n"
            "TUYỆT ĐỐI KHÔNG viết thêm bất kỳ lời chào, nhận xét hay giải thích nào bên ngoài JSON.\n\n"
            "CẤU TRÚC JSON MẪU:\n"
            "{\n"
            '  "titles": [\n'
            '    "Tiêu đề 1 (50-70 ký tự, từ khóa ở 35 ký tự đầu, phù hợp phong cách ngách)",\n'
            '    "Tiêu đề 2 (góc nhìn đối nghịch / nghịch lý)",\n'
            '    "Tiêu đề 3 (câu hỏi mở sâu sắc)"\n'
            '  ],\n'
            '  "description": "Mô tả video chi tiết chuẩn SEO theo đúng chuyên đề ngách...",\n'
            '  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],\n'
            '  "timestamps": [\n'
            '    "00:00 - Mở đầu",\n'
            '    "01:00 - Phần 2",\n'
            '    "02:30 - Phần 3"\n'
            '  ],\n'
            '  "thumbnail_badge": "NHÃN_CẢM_XÚC_NGẮN",\n'
            '  "thumbnail_hook": "CÂU_HOOK_3_TỚI_5_TỪ",\n'
            '  "thumbnail_prompt": "Photorealistic intense cinematic thumbnail visual description...",\n'
            '  "counterpoint_notes": "Tiêu đề cung cấp sự thật khách quan trong khi Thumbnail gợi mở tò mò tâm lý gay gắt."\n'
            "}"
        )

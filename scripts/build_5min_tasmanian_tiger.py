"""
Full 5-Minute Documentary Production Pipeline:
'Hổ Tasmania: Bản Án Tuyệt Chủng Của Một Tuyệt Tác Tiến Hóa'
Executes 5 spatial clusters across 5 minutes with authentic footage,
Vietnamese voiceover (vi-VN-NamMinhNeural), 3-layer audio, and burned subtitles.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from autovideo.core.binary_manager import BinaryManager
from autovideo.production.documentary_assembler import (
    DocumentaryAssembler,
    DocumentaryAssemblerConfig,
    DocumentarySceneItem,
)
from autovideo.production.transformer import probe_video
from autovideo.voiceover.edge_adapter import EdgeTTSAdapter, EdgeTTSConfig

# --- FULL 5-MINUTE SCRIPT (40 SCENES / 5 CLUSTERS) ---
FULL_SCRIPT = [
    # === HỒI 1: CÁI CHẾT CÔ ĐỘC TẠI SỞ THÚ BEAUMARIS (00:00 - 01:00) ===
    # Bối cảnh: Chuồng sắt sở thú Beaumaris (Footage: real_tasmanian_tiger.mp4)
    {
        "scene_id": "H1_01",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 1.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Đêm ngày 7 tháng 9 năm 1936, một sự kiện bi thương và vĩnh viễn không thể đảo ngược đã diễn ra tại đảo Tasmania.",
    },
    {
        "scene_id": "H1_02",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 8.0,
        "scale": "Medium",
        "reframe": "pan_left_right",
        "text": "Tại sở thú Beaumaris, người trông coi vô tâm đã khóa trái cửa chuồng ngoài trời, bỏ mặc một sinh vật đơn độc giữa đêm đông buốt giá.",
    },
    {
        "scene_id": "H1_03",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 15.0,
        "scale": "Closeup",
        "reframe": "top_closeup",
        "text": "Sinh vật đó có tên là Benjamin. Nó chính là cá thể hổ Tasmania cuối cùng còn sót lại trên toàn bộ hành tinh.",
    },
    {
        "scene_id": "H1_04",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 20.0,
        "scale": "Closeup",
        "reframe": None,
        "text": "Nhiệt độ đêm đó tụt dốc thê thảm. Gió lạnh từ Nam Cực thổi rít qua từng khe rào sắt, cứa vào da thịt con thú già cỗi.",
    },
    {
        "scene_id": "H1_05",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 30.0,
        "scale": "Detail",
        "reframe": "center_zoom",
        "text": "Benjamin lê từng bước chân mệt mỏi trong tuyệt vọng, cào móng vào cánh cửa gỗ đóng kín trước khi gục ngã hoàn toàn.",
    },
    {
        "scene_id": "H1_06",
        "cluster_id": "C1_ZOO",
        "environment": "zoo_cage_night",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 64.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Đến sáng hôm sau, khi người ta phát hiện ra xác của Benjamin, một triều đại sinh học kéo dài bốn triệu năm đã chính thức khép lại.",
    },

    # === HỒI 2: TUYỆT TÁC TIẾN HÓA CỦA THIÊN NHIÊN (01:00 - 02:00) ===
    # Bối cảnh: Rừng mưa nguyên sinh Tasmania & Tư liệu lịch sử loài Thylacine
    {
        "scene_id": "H2_01",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "tasmania_rainforest_drone.mp4",
        "offset": 15.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Để hiểu được nỗi mất mát to lớn này, chúng ta phải ngược dòng thời gian về những cánh rừng mưa nguyên sinh của đảo Tasmania.",
    },
    {
        "scene_id": "H2_02",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "thylacine_museum_specimen.mp4",
        "offset": 22.0,
        "scale": "Medium",
        "reframe": "pan_left_right",
        "text": "Hổ Tasmania, hay chó sói túi Thylacine, là sinh vật kỳ lạ bậc nhất mà quá trình tiến hóa từng tạo ra trên Trái Đất.",
    },
    {
        "scene_id": "H2_03",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "thylacine_rare_archive.mp4",
        "offset": 3.0,
        "scale": "Closeup",
        "reframe": "top_closeup",
        "text": "Chúng mang chiếc đầu và dáng dấp của loài chó sói, nhưng phần hông lại mang những sọc vằn đen đặc trưng như loài hổ.",
    },
    {
        "scene_id": "H2_04",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "thylacine_rare_archive.mp4",
        "offset": 12.0,
        "scale": "Closeup",
        "reframe": "top_closeup",
        "text": "Đặc biệt nhất chính là bộ hàm có khớp nối phi thường, có thể há rộng đến tám mươi độ, tựa như một chiếc bẫy thép săn mồi.",
    },
    {
        "scene_id": "H2_05",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "thylacine_museum_specimen.mp4",
        "offset": 55.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Thế nhưng, chúng không phải là họ hàng của chó sói hay mèo rừng. Chúng là loài thú có túi ăn thịt, mang con non trong bụng giống Kangaroo.",
    },
    {
        "scene_id": "H2_06",
        "cluster_id": "C2_WILD",
        "environment": "rainforest_mist",
        "footage": "tasmania_rainforest_drone.mp4",
        "offset": 65.0,
        "scale": "Medium",
        "reframe": None,
        "text": "Chúng là kẻ săn mồi đỉnh bảng trên đảo Tasmania. Không chạy nước rút điên cuồng, chúng săn đuổi con mồi bằng sức bền bỉ phi thường xuyên màn đêm.",
    },

    # === HỒI 3: LỜI VU OAN & CUỘC ĐẠI DIỆT CHỦNG CÓ THƯỞNG (02:00 - 03:00) ===
    # Bối cảnh: Đồi cỏ chăn cừu & Thợ săn thời thuộc địa (Footage: sheep_farm.mp4 & thylacine_museum_specimen.mp4)
    {
        "scene_id": "H3_01",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "sheep_farm.mp4",
        "offset": 5.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Thảm kịch bắt đầu vào đầu thế kỷ mười chín, khi người định cư châu Âu mang theo hàng triệu con cừu tràn ngập hòn đảo.",
    },
    {
        "scene_id": "H3_02",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "sheep_farm.mp4",
        "offset": 18.0,
        "scale": "Medium",
        "reframe": "pan_left_right",
        "text": "Để bảo vệ nguồn lợi tài chính béo bở, các chủ trang trại đã biến hổ Tasmania thành vật tế thần cho mọi con cừu bị chết.",
    },
    {
        "scene_id": "H3_03",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "thylacine_rare_archive.mp4",
        "offset": 20.0,
        "scale": "Closeup",
        "reframe": None,
        "text": "Họ dựng lên những tin đồn ác ý, gán cho loài thú hiền lành này biệt danh 'quái vật hút máu cừu' tàn nhẫn.",
    },
    {
        "scene_id": "H3_04",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "thylacine_museum_specimen.mp4",
        "offset": 92.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Và rồi, năm 1888, chính quyền Tasmania đã đưa ra một quyết định tàn khốc: ban hành đạo luật tiền thưởng diệt trừ Thylacine.",
    },
    {
        "scene_id": "H3_05",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "thylacine_museum_specimen.mp4",
        "offset": 125.0,
        "scale": "Medium",
        "reframe": "pan_left_right",
        "text": "Mỗi một cái xác hổ Tasmania người lớn được trả một bảng Anh, xác con non được mười shilling. Khoản tiền khổng lồ lúc bấy giờ.",
    },
    {
        "scene_id": "H3_06",
        "cluster_id": "C3_BOUNTY",
        "environment": "sheep_pasture",
        "footage": "sheep_farm.mp4",
        "offset": 40.0,
        "scale": "Detail",
        "reframe": "center_zoom",
        "text": "Một làn sóng săn lùng điên cuồng nổ ra. Súng săn, bẫy sắt và mồi độc phủ kín khắp các thung lũng, đẩy chúng đến bờ vực hủy diệt.",
    },

    # === HỒI 4: SỰ THỨC TỈNH MUỘN MÀNG (03:00 - 04:00) ===
    # Bối cảnh: Sự im lặng trong sở thú & Tư liệu giải phẫu Thylacine
    {
        "scene_id": "H4_01",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 48.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Chỉ trong vòng hai mươi năm, hơn hai nghìn hai trăm cá thể hổ Tasmania đã bị giết hại để lĩnh thưởng.",
    },
    {
        "scene_id": "H4_02",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "tasmania_rainforest_drone.mp4",
        "offset": 95.0,
        "scale": "Medium",
        "reframe": None,
        "text": "Những cánh rừng bạt ngàn của Tasmania bỗng chốc rơi vào sự tĩnh lặng rợn người. Không còn ai nghe thấy tiếng gầm của chúng nữa.",
    },
    {
        "scene_id": "H4_03",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "thylacine_museum_specimen.mp4",
        "offset": 153.0,
        "scale": "Closeup",
        "reframe": "top_closeup",
        "text": "Các nhà khoa học khi ấy mới bàng hoàng nhận ra sai lầm. Cấu trúc hàm của Thylacine thực chất quá yếu để có thể cắn cổ cừu trưởng thành.",
    },
    {
        "scene_id": "H4_04",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 56.0,
        "scale": "Closeup",
        "reframe": None,
        "text": "Thủ phạm thực sự giết hại cừu là chó hoang và dịch bệnh, nhưng hổ Tasmania đã phải trả giá bằng cả giống loài của mình.",
    },
    {
        "scene_id": "H4_05",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 60.0,
        "scale": "Detail",
        "reframe": "center_zoom",
        "text": "Sự thức tỉnh đến quá muộn. Chỉ đúng năm mươi chín ngày trước khi Benjamin chết, đạo luật bảo vệ hổ Tasmania mới được thông qua.",
    },
    {
        "scene_id": "H4_06",
        "cluster_id": "C4_SILENCE",
        "environment": "zoo_enclosure",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 68.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Văn bản bảo vệ ký xong khi số lượng cá thể trong tự nhiên đã bằng không. Con người vừa tự tay xóa bỏ một tuyệt tác của tạo hóa.",
    },

    # === HỒI 5: BÓNG MA RỪNG SÂU & GIẤC MƠ HỒI SINH (04:00 - 05:00) ===
    # Bối cảnh: Rừng sương mù hiện đại & Phòng thí nghiệm ADN cổ sinh (Footage: ancient_dna_lab.mp4)
    {
        "scene_id": "H5_01",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "tasmania_rainforest_drone.mp4",
        "offset": 140.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Sau năm 1936, bóng ma của hổ Tasmania vẫn chưa bao giờ nguôi ngoai trong tâm thức của những người yêu thiên nhiên.",
    },
    {
        "scene_id": "H5_02",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "tasmania_rainforest_drone.mp4",
        "offset": 170.0,
        "scale": "Medium",
        "reframe": "pan_left_right",
        "text": "Đã có hàng trăm báo cáo nhìn thấy bóng dáng vằn đen thoắt ẩn thoắt hiện trong những cánh rừng rậm rạp phía tây Tasmania.",
    },
    {
        "scene_id": "H5_03",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "ancient_dna_lab.mp4",
        "offset": 25.0,
        "scale": "Medium",
        "reframe": None,
        "text": "Và ngày nay, trong các phòng thí nghiệm di truyền học tiên tiến nhất thế giới, một dự án đầy tham vọng đang được triển khai.",
    },
    {
        "scene_id": "H5_04",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "ancient_dna_lab.mp4",
        "offset": 58.0,
        "scale": "Closeup",
        "reframe": "top_closeup",
        "text": "Các nhà khoa học đang giải mã bộ gen từ mẫu ướp của Benjamin, nỗ lực dùng công nghệ CRISPR để hồi sinh loài thú đã tuyệt chủng.",
    },
    {
        "scene_id": "H5_05",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "ancient_dna_lab.mp4",
        "offset": 115.0,
        "scale": "Wide",
        "reframe": None,
        "text": "Nhưng liệu việc tạo ra một sinh vật nhân tạo trong lồng kính có bao giờ gột rửa được tội lỗi diệt chủng của con người trong quá khứ?",
    },
    {
        "scene_id": "H5_06",
        "cluster_id": "C5_FUTURE",
        "environment": "future_forest",
        "footage": "real_tasmanian_tiger.mp4",
        "offset": 6.0,
        "scale": "Detail",
        "reframe": "center_zoom",
        "text": "Câu chuyện về Benjamin sẽ mãi là lời nhắc nhở đắt giá nhất: có những điều khi đã mất đi, vĩnh viễn không bao giờ lấy lại được.",
    },
]


def generate_all_voiceovers(work_dir: Path, bm: BinaryManager) -> tuple[list[Path], list[float]]:
    """Synthesizes all 30 scenes with EdgeTTS and returns paths + durations."""
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    adapter = EdgeTTSAdapter(EdgeTTSConfig(voice_id="vi-VN-NamMinhNeural", speed=0.94))
    paths = []
    durations = []

    print(f"Tổng số phân cảnh cần lồng tiếng: {len(FULL_SCRIPT)}")
    for idx, sc in enumerate(FULL_SCRIPT, 1):
        scene_id = sc["scene_id"]
        out_p = audio_dir / f"{scene_id}.mp3"

        if not out_p.exists() or out_p.stat().st_size == 0:
            adapter.synthesize(sc["text"], out_p)
            time.sleep(0.3)  # Gentle spacing to avoid rate limits

        # Probe exact audio duration
        cmd = [
            str(bm.get_binary_path("ffprobe")),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(out_p),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur = float(res.stdout.strip())
        paths.append(out_p)
        durations.append(dur)
        print(f"  [{idx:02d}/{len(FULL_SCRIPT)}] {scene_id} ({dur:.2f}s): {sc['text'][:40]}...")

    return paths, durations


def create_epic_5min_bgm(output_path: Path, total_dur: float, bm: BinaryManager):
    """Synthesizes a 5-minute continuous cinematic ambient BGM."""
    ffmpeg = bm.get_binary_path("ffmpeg")
    cmd = [
        str(ffmpeg),
        "-y",
        "-f", "lavfi",
        "-i", f"anoisesrc=d={total_dur}:c=pink:r=48000:a=0.06",
        "-f", "lavfi",
        "-i", f"sine=frequency=62:duration={total_dur}",
        "-f", "lavfi",
        "-i", f"sine=frequency=124:duration={total_dur}",
        "-filter_complex",
        "[0:a]bandpass=f=350:w=250,volume=0.25[wind];[1:a]lowpass=f=100,volume=0.3[bass];[2:a]lowpass=f=200,volume=0.15[mid];[wind][bass][mid]amix=inputs=3[out]",
        "-map", "[out]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def generate_subtitles(output_path: Path, scenes: list[dict], durations: list[float]):
    """Generates ASS subtitles with yellow styling and dark outline."""
    header = """[Script Info]
Title: Ho Tasmania 5 Phut
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,22,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.8,1,2,35,35,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    current_time = 0.0

    def format_time(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        cs = int((s - int(s)) * 100)
        return f"{h:d}:{m:02d}:{int(s):02d}.{cs:02d}"

    for sc, dur in zip(scenes, durations):
        start_str = format_time(current_time)
        end_str = format_time(current_time + dur)
        text = sc["text"]
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\c&H00E5FF&}}{text}")
        current_time += dur

    output_path.write_text(header + "\n".join(events), encoding="utf-8")


def main():
    start_time = time.time()
    work_dir = Path("cache/tasmanian_5min")
    work_dir.mkdir(parents=True, exist_ok=True)
    bm = BinaryManager()

    print("==================================================================")
    print("KHỞI ĐỘNG DỰ ÁN VIDEO 5 PHÚT: HỔ TASMANIA - BẢN ÁN TUYỆT CHỦNG")
    print("==================================================================")

    # 1. Voiceovers
    print("\n--- BƯỚC 1: SINH TOÀN BỘ GIỌNG ĐỌC THUYẾT MINH TIẾNG VIỆT ---")
    audio_paths, durations = generate_all_voiceovers(work_dir, bm)
    total_audio_sec = sum(durations)
    print(f"-> Hoàn tất lồng tiếng! Tổng thời lượng: {total_audio_sec:.1f}s ({total_audio_sec/60:.2f} phút)")

    # 2. Extract & Prep raw footage shots
    print("\n--- BƯỚC 2: CẮT LÁT FOOTAGE THEO TỪNG CỤM BỐI CẢNH (CLUSTERS) ---")
    raw_shots_dir = work_dir / "raw_shots"
    raw_shots_dir.mkdir(parents=True, exist_ok=True)

    scene_items: list[DocumentarySceneItem] = []
    for idx, (sc, dur) in enumerate(zip(FULL_SCRIPT, durations)):
        scene_id = sc["scene_id"]
        source_p = Path("downloads") / sc["footage"]
        shot_out = raw_shots_dir / f"{scene_id}_raw.mp4"
        offset = sc["offset"]

        if not shot_out.exists() or shot_out.stat().st_size == 0:
            cmd = [
                str(bm.get_binary_path("ffmpeg")),
                "-y",
                "-ss", f"{offset:.2f}",
                "-i", str(source_p),
                "-t", f"{dur + 0.5:.2f}",
                "-an",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                str(shot_out),
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        scene_items.append(
            DocumentarySceneItem(
                scene_id=scene_id,
                video_path=shot_out,
                audio_path=audio_paths[idx],
                text=sc["text"],
                duration_sec=dur,
                cluster_id=sc["cluster_id"],
                environment_id=sc["environment"],
                camera_scale=sc["scale"],
                virtual_reframe=sc["reframe"],
            )
        )

    # 3. Assemble and Transform with Virtual Camera & Fair Use
    print("\n--- BƯỚC 3: DỰNG PHÂN CẢNH VỚI MÁY QUAY ẢO & MÀU CINEMATIC ---")
    config = DocumentaryAssemblerConfig(
        target_width=1920,
        target_height=1080,
        contrast=1.12,
        brightness=-0.02,
        saturation=1.15,
        apply_vignette=True,
    )
    assembler = DocumentaryAssembler(config=config, binary_manager=bm)

    rendered_scenes = []
    muxed_dir = work_dir / "muxed_scenes"
    for idx, item in enumerate(scene_items, 1):
        out_scene = muxed_dir / f"{item.scene_id}_muxed.mp4"
        if not out_scene.exists() or out_scene.stat().st_size == 0:
            print(f"  [{idx:02d}/{len(scene_items)}] Dựng {item.scene_id} ({item.duration_sec:.1f}s) [{item.camera_scale}]...")
            assembler.assemble_scene_clip(item, out_scene)
        rendered_scenes.append(out_scene)

    # 4. Continuous Ambient BGM & Subtitles
    print("\n--- BƯỚC 4: TẠO CẦU NỐI ÂM THANH 5 PHÚT & PHỤ ĐỀ ĐỒNG BỘ ---")
    bgm_path = work_dir / "continuous_ambient_5min.aac"
    if not bgm_path.exists() or bgm_path.stat().st_size == 0:
        create_epic_5min_bgm(bgm_path, total_audio_sec + 2.0, bm)

    sub_path = work_dir / "subtitles_5min.ass"
    generate_subtitles(sub_path, FULL_SCRIPT, durations)

    # 5. Final Concat & Output
    print("\n--- BƯỚC 5: HÒA TRỘN & XUẤT PHIM HOÀN CHỈNH 1080P ---")
    final_output = Path("renders/ho_tasmania_5phut_fullhd.mp4")
    assembler.concatenate_scenes(
        scene_files=rendered_scenes,
        output_path=final_output,
        bgm_path=bgm_path,
        subtitle_ass_path=sub_path,
    )

    probe = probe_video(final_output, bm)
    elapsed = time.time() - start_time
    print("==================================================================")
    print("XUẤT BẢN THÀNH CÔNG PHIM TÀI LIỆU 5 PHÚT!")
    print(f"File đích: {final_output.resolve()}")
    print(f"Độ phân giải: {probe.width}x{probe.height} Full HD @ {probe.fps}fps")
    print(f"Thời lượng thực tế: {probe.duration_sec:.2f} giây ({probe.duration_sec/60:.2f} phút)")
    print(f"Dung lượng video: {final_output.stat().st_size / (1024*1024):.2f} MB")
    print(f"Tổng thời gian sản xuất tự động: {elapsed:.1f} giây")
    print("==================================================================")


if __name__ == "__main__":
    main()

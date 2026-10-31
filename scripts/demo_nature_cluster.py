"""
End-to-End Demo: Nature & Wildlife Visual Continuity Engine.
Demonstrates Scene Clustering, Shot Scale Progression (Wide -> Medium -> Closeup -> Detail),
Virtual Camera Re-framing, and Continuous Audio Bridge on the Benjamin / Tasmanian Tiger story.
"""

from __future__ import annotations

import os
import subprocess
import sys
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

BENJAMIN_CLUSTER = {
    "cluster_id": "CLUSTER_ZOO_DEATH",
    "environment": "zoo_cage_night",
    "ambient_type": "cold_wind_winter",
    "scenes": [
        {
            "scene_id": "BENJ_001",
            "camera_scale": "Wide",
            "virtual_reframe": None,
            "text": "Đêm ngày 7 tháng 9 năm 1936, tại sở thú Beaumaris, một cánh cửa lịch sử đã vĩnh viễn khép lại.",
            "cut_offset": 36.0,
        },
        {
            "scene_id": "BENJ_002",
            "camera_scale": "Medium",
            "virtual_reframe": "pan_left_right",
            "text": "Benjamin, con hổ Tasmania cuối cùng, lê bước trong vô vọng khi đợt không khí lạnh cắt da ùa về.",
            "cut_offset": 44.0,
        },
        {
            "scene_id": "BENJ_003",
            "camera_scale": "Closeup",
            "virtual_reframe": "top_closeup",
            "text": "Ánh mắt mệt mỏi và bộ hàm há rộng 80 độ đã không còn đủ sức chống chọi lại sự thờ ơ của con người.",
            "cut_offset": 8.5,
        },
        {
            "scene_id": "BENJ_004",
            "camera_scale": "Detail",
            "virtual_reframe": "center_zoom",
            "text": "Cánh cửa sắt khép lại trong đêm tuyết giá, chấm dứt hàng triệu năm tồn tại của một tuyệt tác tiến hóa.",
            "cut_offset": 20.0,
        },
    ],
}


def generate_cluster_voiceovers(work_dir: Path) -> tuple[list[Path], list[float]]:
    """Generates voiceover audio files using EdgeTTS vi-VN-NamMinhNeural."""
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    adapter = EdgeTTSAdapter(EdgeTTSConfig(voice_id="vi-VN-NamMinhNeural", speed=0.93))
    audio_paths = []
    durations = []

    for item in BENJAMIN_CLUSTER["scenes"]:
        scene_id = item["scene_id"]
        out_path = audio_dir / f"{scene_id}.mp3"
        res = adapter.synthesize(item["text"], out_path)
        audio_paths.append(out_path)
        durations.append(res.duration_sec)
        print(f"Generated TTS for {scene_id} ({res.duration_sec:.2f}s): {out_path.name}")

    return audio_paths, durations


def create_continuous_ambient_bridge(output_path: Path, duration_sec: float, bm: BinaryManager):
    """
    Creates a continuous cold-wind and dark-cello audio bridge.
    This continuous ambient layer plays seamlessly across all scenes in the cluster.
    """
    ffmpeg = bm.get_binary_path("ffmpeg")
    # Low frequency rumble + wind noise filter
    cmd = [
        str(ffmpeg),
        "-y",
        "-f", "lavfi",
        "-i", f"anoisesrc=d={duration_sec}:c=pink:r=48000:a=0.08",
        "-f", "lavfi",
        "-i", f"sine=frequency=65:duration={duration_sec}",
        "-filter_complex",
        "[0:a]bandpass=f=400:w=300,volume=0.3[wind];[1:a]lowpass=f=120,volume=0.2[drone];[wind][drone]amix=inputs=2[out]",
        "-map", "[out]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=False)


def generate_subtitles_ass(output_path: Path, scenes: list[dict], durations: list[float]):
    """Generates ASS subtitles with crisp black border and yellow accents."""
    header = """[Script Info]
Title: Benjamin Tasmanian Tiger
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,21,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.8,1,2,30,30,45,1

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
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\c&H00D4FF&}}{text}")
        current_time += dur

    output_path.write_text(header + "\n".join(events), encoding="utf-8")


def main():
    work_dir = Path("cache/demo_nature_cluster")
    work_dir.mkdir(parents=True, exist_ok=True)
    bm = BinaryManager()

    print("=== BƯỚC 1: SINH GIỌNG ĐỌC CHO TOÀN BỘ CỤM BỐI CẢNH (SCENE CLUSTER) ===")
    audio_paths, audio_durations = generate_cluster_voiceovers(work_dir)
    total_audio_sec = sum(audio_durations)
    print(f"Tổng thời lượng cụm bối cảnh: {total_audio_sec:.1f}s")

    print("=== BƯỚC 2: KHAI THÁC MÁY QUAY ẢO (VIRTUAL MULTI-CAM RE-FRAMING) ===")
    source_footage = Path("downloads/real_tasmanian_tiger.mp4")
    if not source_footage.exists():
        print(f"Lỗi: Không tìm thấy {source_footage}")
        return

    raw_shots_dir = work_dir / "raw_shots"
    raw_shots_dir.mkdir(parents=True, exist_ok=True)

    scene_items: list[DocumentarySceneItem] = []
    scenes = BENJAMIN_CLUSTER["scenes"]
    for idx, (sc, dur) in enumerate(zip(scenes, audio_durations)):
        scene_id = sc["scene_id"]
        shot_out = raw_shots_dir / f"{scene_id}_footage.mp4"
        offset = sc["cut_offset"]

        # Cut exactly dur seconds from offset with stripped audio
        cmd = [
            str(bm.get_binary_path("ffmpeg")),
            "-y",
            "-ss", f"{offset:.2f}",
            "-i", str(source_footage),
            "-t", f"{dur:.2f}",
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
                cluster_id=BENJAMIN_CLUSTER["cluster_id"],
                environment_id=BENJAMIN_CLUSTER["environment"],
                camera_scale=sc["camera_scale"],
                virtual_reframe=sc["virtual_reframe"],
            )
        )

    print("=== BƯỚC 3: DỰNG PHÂN CẢNH VỚI THANG CỠ CẢNH (WIDE -> MEDIUM -> CLOSEUP -> DETAIL) ===")
    config = DocumentaryAssemblerConfig(
        target_width=1920,
        target_height=1080,
        contrast=1.14,
        brightness=-0.03,
        saturation=1.12,
        apply_vignette=True,
    )
    assembler = DocumentaryAssembler(config=config, binary_manager=bm)

    rendered_scenes = []
    scenes_dir = work_dir / "muxed_scenes"
    for item in scene_items:
        out_scene = scenes_dir / f"{item.scene_id}_final.mp4"
        print(f"Dựng cảnh {item.scene_id} [Scale: {item.camera_scale} | Reframe: {item.virtual_reframe}] ({item.duration_sec:.1f}s)...")
        assembler.assemble_scene_clip(item, out_scene)
        rendered_scenes.append(out_scene)

    print("=== BƯỚC 4: THIẾT LẬP CẦU NỐI ÂM THANH LIÊN TỤC (CONTINUOUS AUDIO BRIDGE) & PHỤ ĐỀ ===")
    ambient_bridge_path = work_dir / "cold_wind_ambient_bridge.aac"
    create_continuous_ambient_bridge(ambient_bridge_path, total_audio_sec + 2.0, bm)

    sub_path = work_dir / "subtitles.ass"
    generate_subtitles_ass(sub_path, scenes, audio_durations)

    renders_dir = Path("renders")
    renders_dir.mkdir(parents=True, exist_ok=True)
    final_output = renders_dir / "demo_tasmanian_tiger.mp4"

    print("=== BƯỚC 5: XUẤT VIDEO LIỀN MẠCH THÀNH PHẨM 1080P ===")
    assembler.concatenate_scenes(
        scene_files=rendered_scenes,
        output_path=final_output,
        bgm_path=ambient_bridge_path,
        subtitle_ass_path=sub_path,
    )

    probe = probe_video(final_output, bm)
    print("==================================================")
    print(f"XUẤT VIDEO THÀNH CÔNG: {final_output.resolve()}")
    print(f"Độ phân giải: {probe.width}x{probe.height} @ {probe.fps}fps")
    print(f"Thời lượng: {probe.duration_sec:.2f} giây")
    print(f"Dung lượng: {final_output.stat().st_size / (1024*1024):.2f} MB")
    print("==================================================")


if __name__ == "__main__":
    main()

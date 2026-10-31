"""
End-to-End Demo: Generates a 25-second documentary teaser (Chu Nguyen Chuong)
following the exact CD Media / Vũ Trụ Nguyên Thủy production formula.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding='utf-8')

from autovideo.core.binary_manager import BinaryManager
from autovideo.production.documentary_assembler import (
    DocumentaryAssembler,
    DocumentaryAssemblerConfig,
    DocumentarySceneItem,
)
from autovideo.production.transformer import probe_video
from autovideo.sourcing.scene_splitter import SceneSplitter
from autovideo.voiceover.edge_adapter import EdgeTTSAdapter, EdgeTTSConfig

DEMO_SCRIPT = [
    {
        "scene_id": "SCENE_001",
        "text": "Chu Nguyên Chương, vị hoàng đế đi lên từ đáy vực xã hội.",
        "start_sec": 0.0,
        "end_sec": 4.8,
        "cut_offset": 8.0,  # portrait shot in sample_sRiSO
    },
    {
        "scene_id": "SCENE_002",
        "text": "Từ một kẻ phải xin ăn để sống qua ngày, thành người xoay chuyển bánh xe lịch sử.",
        "start_sec": 4.8,
        "end_sec": 10.5,
        "cut_offset": 12.0,  # begging / walking shot
    },
    {
        "scene_id": "SCENE_003",
        "text": "Hậu thế nhớ đến ông bởi chiến tích quét sạch vó ngựa Mông Cổ, lập nên triều Minh rực rỡ.",
        "start_sec": 10.5,
        "end_sec": 16.5,
        "cut_offset": 20.0,  # Mongol horse cavalry / palace march
    },
    {
        "scene_id": "SCENE_004",
        "text": "Nhưng tại sao đế chế ấy lại được xây đắp bằng chính xương máu của những huynh đệ đồng cam cộng khổ?",
        "start_sec": 16.5,
        "end_sec": 23.5,
        "cut_offset": 36.0,  # Red throne / banquet
    },
]


def generate_voiceovers(work_dir: Path) -> tuple[list[Path], list[float]]:
    """Generates voiceover audio files using vi-VN-NamMinhNeural via EdgeTTSAdapter."""
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    adapter = EdgeTTSAdapter(EdgeTTSConfig(voice_id="vi-VN-NamMinhNeural", speed=0.95))
    audio_paths = []
    durations = []

    for item in DEMO_SCRIPT:
        scene_id = item["scene_id"]
        out_path = audio_dir / f"{scene_id}.mp3"
        res = adapter.synthesize(item["text"], out_path)
        audio_paths.append(out_path)
        durations.append(res.duration_sec)
        print(f"Generated TTS for {scene_id} ({res.duration_sec:.2f}s): {out_path.name}")

    return audio_paths, durations


def create_ambient_bgm(output_path: Path, duration_sec: float, binary_manager: BinaryManager):
    """Synthesizes a dark, dramatic ambient cinematic tone with FFmpeg."""
    ffmpeg = binary_manager.get_binary_path("ffmpeg")
    # Generate low drone chord (55Hz + 110Hz + 165Hz) with gentle amplitude modulation
    cmd = [
        str(ffmpeg),
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=55:duration={duration_sec}",
        "-f", "lavfi",
        "-i", f"sine=frequency=110:duration={duration_sec}",
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2,lowpass=f=250,volume=0.25[out]",
        "-map", "[out]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=False)


def generate_subtitles_ass(output_path: Path, items: list[dict], audio_durations: list[float]):
    """Generates styled ASS subtitles with white text, yellow accents and black border."""
    header = """[Script Info]
Title: Chu Nguyen Chuong Demo
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,30,30,45,1

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

    for item, dur in zip(items, audio_durations):
        start_str = format_time(current_time)
        end_str = format_time(current_time + dur)
        # Highlight key words in yellow
        text = item["text"]
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\c&H00E5FF&}}{text}")
        current_time += dur

    output_path.write_text(header + "\n".join(events), encoding="utf-8")


def main():
    work_dir = Path("cache/demo_documentary")
    work_dir.mkdir(parents=True, exist_ok=True)
    bm = BinaryManager()

    print("=== Bước 1: Sinh giọng đọc chuẩn CD Media (NamMinhNeural) ===")
    audio_paths, audio_durations = generate_voiceovers(work_dir)
    total_audio_sec = sum(audio_durations)
    print(f"Tổng thời lượng thoại: {total_audio_sec:.1f}s")

    print("=== Bước 2: Cắt lát Footage khớp với từng câu kịch bản ===")
    source_footage = Path("sample_sRiSO.mp4")
    if not source_footage.exists():
        print(f"Lỗi: Không tìm thấy {source_footage}")
        return

    raw_shots_dir = work_dir / "raw_shots"
    raw_shots_dir.mkdir(parents=True, exist_ok=True)

    scene_items: list[DocumentarySceneItem] = []
    for idx, (item, dur) in enumerate(zip(DEMO_SCRIPT, audio_durations)):
        scene_id = item["scene_id"]
        shot_out = raw_shots_dir / f"{scene_id}_footage.mp4"
        offset = item["cut_offset"]

        # Cut exactly dur seconds from offset
        cmd = [
            str(bm.get_binary_path("ffmpeg")),
            "-y",
            "-ss", f"{offset:.2f}",
            "-i", str(source_footage),
            "-t", f"{dur:.2f}",
            "-an",  # Strip original audio completely
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
                text=item["text"],
                duration_sec=dur,
            )
        )

    print("=== Bước 3: Áp dụng hiệu ứng Transformative (Màu Cinematic + Ken Burns + Khung 16:9) ===")
    config = DocumentaryAssemblerConfig(
        target_width=1920,
        target_height=1080,
        contrast=1.12,
        brightness=-0.02,
        saturation=1.18,
        apply_vignette=True,
    )
    assembler = DocumentaryAssembler(config=config, binary_manager=bm)

    rendered_scenes = []
    scenes_dir = work_dir / "muxed_scenes"
    for item in scene_items:
        out_scene = scenes_dir / f"{item.scene_id}_final.mp4"
        print(f"Dựng cảnh {item.scene_id} ({item.duration_sec:.1f}s)...")
        assembler.assemble_scene_clip(item, out_scene)
        rendered_scenes.append(out_scene)

    print("=== Bước 4: Hòa âm BGM & Phụ đề ===")
    bgm_path = work_dir / "cinematic_drone.aac"
    create_ambient_bgm(bgm_path, total_audio_sec + 2.0, bm)

    sub_path = work_dir / "subtitles.ass"
    generate_subtitles_ass(sub_path, DEMO_SCRIPT, audio_durations)

    renders_dir = Path("renders")
    renders_dir.mkdir(parents=True, exist_ok=True)
    final_output = renders_dir / "demo_chu_nguyen_chuong.mp4"

    print("=== Bước 5: Xuất video thành phẩm 1080p ===")
    assembler.concatenate_scenes(
        scene_files=rendered_scenes,
        output_path=final_output,
        bgm_path=bgm_path,
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

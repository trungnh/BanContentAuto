import asyncio
import os
import sys
from pathlib import Path

# Add src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autovideo.coordinator import MasterPipelineCoordinator, PipelineStage
from autovideo.core.config import get_config
from autovideo.production.transformer import probe_video
from autovideo.voiceover.timing_probe import TimingProbe

async def main():
    print("[*] Khoi tao MasterPipelineCoordinator...")
    cfg = get_config()
    coord = MasterPipelineCoordinator(config=cfg)
    
    project_id = "test_real_pipe"
    p = coord.get_or_create_project(
        topic="Sập kệ kho công nghiệp",
        skill_id="warehouse-fails",
        target_duration_min=1,
        project_id=project_id,
    )
    
    # We will test 1 scene synthesis
    from autovideo.script.pipeline import Scene, SceneKeyword
    scene = Scene(
        scene_id="SCENE_001",
        chapter_index=1,
        text="Cú va chạm cực mạnh khiến toàn bộ hệ thống kệ kho liên hoàn sụp đổ.",
        visual_prompt="Warehouse rack collapse cctv fail",
        duration_sec=4.0,
        word_count=13,
        keywords=SceneKeyword(
            vi=["sập kệ kho"],
            en=["warehouse rack collapse cctv fail"],
            zh=["仓库货架倒塌"]
        ),
        preferred_vault="universal"
    )
    
    print("[*] 1. Test tong hop giong doc thuc te (ZeroTTS)...")
    res_vo = coord.voiceover_manager.synthesize_scene(scene, scene_index=1, project_id=project_id)
    print(f"  + Voiceover: {res_vo.audio_path} ({res_vo.duration_sec}s, sample_rate={res_vo.sample_rate}, engine={res_vo.engine})")
    
    print("[*] 2. Test tim kiem & tai footage thuc te (UniversalDownloader)...")
    sourced = coord.sourcing_engine.source_scene_asset(
        scene_id=scene.scene_id,
        query="warehouse rack collapse cctv fail",
        preferred_vault="universal",
        enforce_duration=False,
    )
    print(f"  + Footage: {sourced.file_path} ({sourced.duration_sec}s, {sourced.width}x{sourced.height})")
    
    print("[*] 3. Test dung Atomic Scene thuc te...")
    out_scene = cfg.paths.cache_temp_scenes_dir / project_id / "scene_001.mp4"
    mux_res = coord.scene_muxer.assemble_scene(
        project_id=project_id,
        scene_idx=1,
        media_path=sourced.file_path,
        voiceover_audio_path=res_vo.audio_path,
        target_duration_sec=res_vo.duration_sec,
        output_path=out_scene,
    )
    print(f"  + Muxed scene: {mux_res.output_path} ({mux_res.duration_sec}s)")
    
    probe = probe_video(mux_res.output_path)
    print(f"[XAC NHAN] Video clip hop le: {probe.width}x{probe.height}, duration={probe.duration_sec}s, has_audio={probe.has_audio}, fps={probe.fps}")

if __name__ == "__main__":
    asyncio.run(main())

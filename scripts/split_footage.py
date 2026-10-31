"""
CLI Utility to split downloaded footage into atomic shots for the vault.
Usage:
    python scripts/split_footage.py <video_file> [--output-dir vaults/bilibili] [--threshold 0.35]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autovideo.sourcing.scene_splitter import SceneSplitter


def main():
    parser = argparse.ArgumentParser(description="Split long footage into atomic 3-6s shots.")
    parser.add_argument("video_path", type=str, help="Path to input video file")
    parser.add_argument("--output-dir", type=str, default="vaults/shots", help="Output directory")
    parser.add_argument("--threshold", type=float, default=0.35, help="Scene detection threshold (0.2 - 0.5)")
    parser.add_argument("--min-dur", type=float, default=2.5, help="Min shot duration")
    parser.add_argument("--max-dur", type=float, default=6.5, help="Max shot duration")
    parser.add_argument("--max-scan", type=float, default=None, help="Max seconds to scan from beginning")

    args = parser.parse_args()
    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"Error: {video_path} does not exist.")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    splitter = SceneSplitter()
    print(f"Processing {video_path}...")
    shots = splitter.split_video(
        video_path=video_path,
        output_dir=output_dir,
        min_duration=args.min_dur,
        max_duration=args.max_dur,
        scene_threshold=args.threshold,
        max_scan_sec=args.max_scan,
    )
    print(f"Done! Successfully generated {len(shots)} shots in {output_dir}")


if __name__ == "__main__":
    main()

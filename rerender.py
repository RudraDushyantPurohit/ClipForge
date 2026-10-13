"""Re-render the video from existing outputs with (new) manual images or cards.

Skips research/script/narration — reuses script.json and narration.mp3
from the specified run directory or output/.

Run:
    python rerender.py --run pep-q3-2026
    python rerender.py --images-dir "assets/pep-q3-2026"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from pipeline import _load_manual_images
import video.creator as _vc
from video.creator import create_video


def main():
    ap = argparse.ArgumentParser(description="Re-render video with manual images or section cards")
    ap.add_argument("--run", default="",
                    help="Run tag to re-render, e.g. 'pep-q3-2026' (looks in output/<run> and assets/<run>)")
    ap.add_argument("--images-dir", default="",
                    help="Folder of per-section images (1.png, 2.png, ...)")
    ap.add_argument("--script", default="",
                    help="Path to script.json override")
    ap.add_argument("--audio", default="",
                    help="Path to narration.mp3 override")
    args = ap.parse_args()
    _vc._PROGRESS_EVERY = 5  # progress print every 5s of video

    # Determine paths
    if args.run:
        run_output = os.path.join(config.OUTPUT_DIR, args.run)
        script_path = args.script or os.path.join(run_output, "script.json")
        audio_path  = args.audio  or os.path.join(run_output, "narration.mp3")
        images_dir  = args.images_dir or os.path.join("assets", args.run)
        target_out  = run_output
    else:
        script_path = args.script or os.path.join(config.OUTPUT_DIR, "script.json")
        audio_path  = args.audio  or os.path.join(config.OUTPUT_DIR, "narration.mp3")
        images_dir  = args.images_dir
        target_out  = config.OUTPUT_DIR

    if not os.path.isfile(script_path):
        sys.exit(f"script not found: {script_path} — run pipeline.py first")
    if not os.path.isfile(audio_path):
        sys.exit(f"audio not found: {audio_path} — run pipeline.py first")
    if not images_dir or not os.path.isdir(images_dir):
        sys.exit(f"images dir not found: {images_dir}")

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    image_map = _load_manual_images(script, images_dir)
    out = create_video(script, audio_path, target_out, image_map)
    print(f"\n  [OK] Re-rendered: {os.path.abspath(out)}")


if __name__ == "__main__":
    main()

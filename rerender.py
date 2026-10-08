"""Re-render the video from existing outputs with (new) manual images.

Skips research/script/narration — reuses output/script.json and
output/narration.mp3 from the last pipeline run. Useful when you only
changed the images.

Run:  python rerender.py --images-dir "path/to/images"
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
    ap = argparse.ArgumentParser(description="Re-render video with manual images")
    ap.add_argument("--images-dir", required=True,
                    help="Folder of per-section images (1.png, 2.png, ...)")
    ap.add_argument("--script", default=os.path.join(config.OUTPUT_DIR, "script.json"))
    ap.add_argument("--audio", default=os.path.join(config.OUTPUT_DIR, "narration.mp3"))
    args = ap.parse_args()
    _vc._PROGRESS_EVERY = 5  # progress print every 5s of video

    if not os.path.isfile(args.script):
        sys.exit(f"script not found: {args.script} — run pipeline.py first")
    if not os.path.isfile(args.audio):
        sys.exit(f"audio not found: {args.audio} — run pipeline.py first")
    if not os.path.isdir(args.images_dir):
        sys.exit(f"images dir not found: {args.images_dir}")

    with open(args.script, encoding="utf-8") as f:
        script = json.load(f)

    image_map = _load_manual_images(script, args.images_dir)
    out = create_video(script, args.audio, config.OUTPUT_DIR, image_map)
    print(f"\n  ✅ Re-rendered: {os.path.abspath(out)}")


if __name__ == "__main__":
    main()

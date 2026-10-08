#!/usr/bin/env python3
"""
YouTube AI Agent — Main Pipeline (Free Edition)
Uses: Gemini 2.5 Flash · Edge TTS · Pexels · MoviePy · Flask · YouTube Data API

Run:  python pipeline.py
"""
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import config
from agents.researcher   import research_topic
from agents.scriptwriter import write_script
from video.narrator      import generate_narration
from video.stock         import download_images
from video.creator       import create_video
from review.app          import start_review_server
from uploader.youtube    import upload_to_youtube


def banner(text: str):
    print("\n" + "─" * 62)
    print(f"  {text}")
    print("─" * 62)


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description="Beat or Miss video pipeline")
    ap.add_argument("--topic", default="",
                    help="Exact topic override, e.g. 'NVDA Q3 FY2026 earnings: revenue $35.1B (+6%% vs est), EPS $0.81'")
    ap.add_argument("--shorts", action="store_true",
                    help="Render a 60-90s vertical Short instead of the default 6-8 min video")
    ap.add_argument("--images-dir", default="",
                    help="Folder of per-section images named <section_id>.png/jpg (e.g. 1.png, 2.png). Skips Pexels.")
    return ap.parse_args()


def _load_manual_images(script: dict, images_dir: str) -> dict:
    """Map user-supplied images to script sections.

    Tries the section id first (e.g. hook_q1_reaction.png), then falls back
    to 1-based position (1.png, 2.png, ...) since the scriptwriter sometimes
    emits string ids. 1-based position: section 1 -> 1.png, etc.
    """
    image_map = {}
    sections = script.get("sections", [])
    for pos, s in enumerate(sections, start=1):
        sid = s["id"]
        paths = []
        for ext in ("png", "jpg", "jpeg", "webp"):
            for cand in (f"{sid}.{ext}", f"{pos}.{ext}", f"section_{pos:02d}.{ext}"):
                p = os.path.join(images_dir, cand)
                if os.path.isfile(p):
                    paths.append(p)
        image_map[sid] = sorted(set(paths))
    found = sum(1 for v in image_map.values() if v)
    print(f"   → manual images: {found}/{len(image_map)} sections covered")
    return image_map


def run():
    Path(config.OUTPUT_DIR).mkdir(exist_ok=True)
    Path(config.IMAGES_DIR).mkdir(exist_ok=True)

    print("\n🎬  YouTube AI Agent Studio  ·  Video Pipeline\n")

    # ── 1. Research ───────────────────────────────────────────
    banner("1 / 6  ·  Researching trending topic  [Gemini]")
    args = _parse_args()
    research = research_topic(config.CHANNEL_DESCRIPTION, topic_override=args.topic)
    print(f"\n  ✅  Topic : {research['topic']}")
    print(f"      Title : {research['video_title']}")
    print(f"      Hook  : {research.get('hook_question', '')[:90]}")
    with open(f"{config.OUTPUT_DIR}/research.json", "w") as f:
        json.dump(research, f, indent=2)

    # ── 2. Script ─────────────────────────────────────────────
    banner("2 / 6  ·  Writing script  [Gemini]")
    script = write_script(research, video_type="shorts" if args.shorts else "normal")
    print(f"\n  ✅  {len(script['sections'])} sections written")
    for s in script["sections"]:
        words = len(s.get("narration", "").split())
        # Safely grab the title, or default to "Untitled" if the AI forgot it
        title = s.get("title", "Untitled") 
        print(f"      [{s.get('id', 9):02d}] {title:<42} {words:3d} words")
    with open(f"{config.OUTPUT_DIR}/script.json", "w") as f:
        json.dump(script, f, indent=2)

    # ── 3. Stock Images ───────────────────────────────────────
    if args.images_dir and os.path.isdir(args.images_dir):
        banner("3 / 6  ·  Loading manual images  [--images-dir]")
        image_map = _load_manual_images(script, args.images_dir)
    elif args.images_dir:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        print(f"   ⚠ --images-dir not found: {args.images_dir} — falling back to Pexels")
        image_map = download_images(script, config.OUTPUT_DIR)
    else:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        image_map = download_images(script, config.OUTPUT_DIR)
    found = sum(1 for v in image_map.values() if v)
    print(f"\n  ✅  {found}/{len(image_map)} images downloaded")

    # ── 4. Narration ──────────────────────────────────────────
    banner("4 / 6  ·  Generating voiceover  [Edge TTS — free]")
    audio_path = generate_narration(script, config.OUTPUT_DIR)
    print(f"\n  ✅  Audio: {audio_path}")

    # ── 5. Video ──────────────────────────────────────────────
    banner("5 / 6  ·  Building cinematic video  [MoviePy]")
    video_path = create_video(script, audio_path, config.OUTPUT_DIR, image_map)
    video_path = os.path.abspath(video_path)  # review server misresolves relative paths

    # ── 6. Review ─────────────────────────────────────────────
    banner("6 / 6  ·  Human review  [Flask dashboard]")
    print("\n  → Opening review dashboard in your browser…")
    review_data = {
        "research":   research,
        "script":     script,
        "video_path": video_path,
    }
    with open(f"{config.OUTPUT_DIR}/review_data.json", "w") as f:
        json.dump({k: v for k, v in review_data.items() if k != "video_path"},
                  f, indent=2)

    approved = start_review_server(review_data)

    # ── Upload or stop ────────────────────────────────────────
    if approved:
        banner("🚀  Uploading to YouTube")
        url = upload_to_youtube(script, video_path)
        print(f"\n  🎉  Video live: {url}\n")
    else:
        print("\n  ❌  Rejected — pipeline stopped.")
        print("      Tip: edit output/script.json and re-run just the video step.\n")


if __name__ == "__main__":
    run()

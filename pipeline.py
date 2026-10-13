#!/usr/bin/env python3
"""
YouTube AI Agent — Main Pipeline
Uses: Antigravity CLI (agy) / Gemini API · Edge TTS · Pexels · MoviePy · Flask · YouTube Data API

Run:  python pipeline.py --shorts --topic "PEP Q3 2026"
"""
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
from agents.researcher   import research_topic, extract_earnings_tags
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
                    help="Topic or earnings query, e.g. 'PEP Q3 2026' or 'NVDA Q3 FY2026'")
    ap.add_argument("--ticker", default="",
                    help="Stock ticker override, e.g. 'PEP'")
    ap.add_argument("--quarter", default="",
                    help="Quarter override, e.g. 'Q3'")
    ap.add_argument("--fy", default="",
                    help="Fiscal year override, e.g. '2026' or 'FY26'")
    ap.add_argument("--shorts", action="store_true",
                    help="Render a 60-90s vertical Short instead of the default 6-8 min video")
    ap.add_argument("--images-dir", default="",
                    help="Folder of per-section images (e.g. 1.png, 2.png). Skips card generation & Pexels.")
    ap.add_argument("--skip-ai", action="store_true",
                    help="Reuse existing research.json and script.json from the run directory")
    ap.add_argument("--resume", action="store_true",
                    help="Resume pipeline from existing artifacts without re-running earlier steps")
    ap.add_argument("--from-step", default="",
                    choices=["research", "script", "visuals", "narration", "video", "review", "1", "2", "3", "4", "5", "6"],
                    help="Resume pipeline directly from step: 1 (research), 2 (script), 3 (visuals), 4 (narration), 5 (video), 6 (review)")
    ap.add_argument("--no-review", action="store_true",
                    help="Skip browser review dashboard and stop immediately after video render")
    return ap.parse_args()


def _resolve_run_tag(topic: str, args) -> str:
    """Resolve standard run tag e.g. 'pep-q3-2026' for directory segregation."""
    if args.ticker and args.quarter:
        fy = args.fy or "2026"
        return f"{args.ticker.lower()}-{args.quarter.lower()}-{fy.lower()}"
    
    tags = extract_earnings_tags(topic)
    if tags:
        ticker, quarter, fy = tags
        return f"{ticker.lower()}-{quarter.lower()}-{fy.lower()}"
    
    return ""


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
    args = _parse_args()
    
    # ── Resolve segregation directories ───────────────────────
    topic_text = args.topic or (f"{args.ticker} {args.quarter} {args.fy}" if args.ticker else "")
    run_tag = _resolve_run_tag(topic_text, args)

    if run_tag:
        run_output_dir = os.path.join(config.OUTPUT_DIR, run_tag)
        run_assets_dir = os.path.join("assets", run_tag)
    else:
        run_output_dir = config.OUTPUT_DIR
        run_assets_dir = config.IMAGES_DIR

    Path(config.OUTPUT_DIR).mkdir(exist_ok=True)
    Path(run_output_dir).mkdir(parents=True, exist_ok=True)
    Path(run_assets_dir).mkdir(parents=True, exist_ok=True)

    backend_label = getattr(config, "LLM_BACKEND", "agy").upper()
    step_order = {
        "research": 1, "1": 1,
        "script": 2, "2": 2,
        "visuals": 3, "3": 3,
        "narration": 4, "4": 4,
        "video": 5, "5": 5,
        "review": 6, "6": 6,
    }
    from_step_num = step_order.get(str(args.from_step).lower(), 1) if args.from_step else 1

    print("\n🎬  YouTube AI Agent Studio  ·  Video Pipeline")
    if run_tag:
        print(f"    Target: {run_tag.upper()}  |  Output: {run_output_dir}")
    else:
        print(f"    Output: {run_output_dir}")
    if args.resume or from_step_num > 1:
        print(f"    Mode  : Resume from step {from_step_num}\n")
    else:
        print()

    # ── 1. Research ───────────────────────────────────────────
    banner(f"1 / 6  ·  Researching topic  [{backend_label}]")
    research_file = os.path.join(run_output_dir, "research.json")
    skip_research = (args.skip_ai or args.resume or from_step_num > 1) and os.path.isfile(research_file)
    if skip_research:
        print(f"   → [RESUME] Loading existing {research_file}")
        with open(research_file, encoding="utf-8") as f:
            research = json.load(f)
    else:
        research = research_topic(config.CHANNEL_DESCRIPTION, topic_override=topic_text)
        print(f"\n  [OK] Topic : {research['topic']}")
        print(f"       Title : {research['video_title']}")
        print(f"       Hook  : {research.get('hook_question', '')[:90]}")
        with open(research_file, "w", encoding="utf-8") as f:
            json.dump(research, f, indent=2)
        # Root copy for convenience
        with open(os.path.join(config.OUTPUT_DIR, "research.json"), "w", encoding="utf-8") as f:
            json.dump(research, f, indent=2)

    # ── 2. Script ─────────────────────────────────────────────
    banner(f"2 / 6  ·  Writing script  [{backend_label}]")
    script_file = os.path.join(run_output_dir, "script.json")
    skip_script = (args.skip_ai or args.resume or from_step_num > 2) and os.path.isfile(script_file)
    if skip_script:
        print(f"   → [RESUME] Loading existing {script_file}")
        with open(script_file, encoding="utf-8") as f:
            script = json.load(f)
    else:
        script = write_script(research, video_type="shorts" if args.shorts else "normal")
        print(f"\n  [OK] {len(script['sections'])} sections written")
        for s in script["sections"]:
            words = len(s.get("narration", "").split())
            title = s.get("title", "Untitled") 
            print(f"       [{s.get('id', 9):02d}] {title:<42} {words:3d} words")
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script, f, indent=2)
        # Root copy for convenience
        with open(os.path.join(config.OUTPUT_DIR, "script.json"), "w", encoding="utf-8") as f:
            json.dump(script, f, indent=2)

    # ── 3. Visuals / Images ───────────────────────────────────
    if args.images_dir and os.path.isdir(args.images_dir):
        banner("3 / 6  ·  Loading manual images  [--images-dir]")
        image_map = _load_manual_images(script, args.images_dir)
    elif args.shorts or run_tag:
        banner("3 / 6  ·  Beat or Miss section cards  [1.png, 2.png, 3.png]")
        needed_cards = [os.path.join(run_assets_dir, f"{i}.png") for i in (1, 2, 3)]
        all_exist = all(os.path.isfile(p) for p in needed_cards)

        if not all_exist:
            print(f"   → Generating verified section cards in {run_assets_dir}…")
            from video.cards import generate_section_cards
            generate_section_cards(research, run_assets_dir)
        else:
            print(f"   → Reusing existing section cards from {run_assets_dir}")

        image_map = _load_manual_images(script, run_assets_dir)
    elif args.images_dir:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        print(f"   ⚠ --images-dir not found: {args.images_dir} — falling back to Pexels")
        image_map = download_images(script, run_output_dir)
    else:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        image_map = download_images(script, run_output_dir)

    found = sum(1 for v in image_map.values() if v)
    print(f"\n  [OK] {found}/{len(image_map)} section visual paths configured")

    # ── 4. Narration ──────────────────────────────────────────
    banner("4 / 6  ·  Generating voiceover  [Edge TTS — free]")
    audio_path = os.path.join(run_output_dir, "narration.mp3")
    srt_path = os.path.join(run_output_dir, "narration.srt")
    skip_audio = (args.resume or from_step_num > 4) and \
                 os.path.isfile(audio_path) and os.path.getsize(audio_path) > 0 and \
                 os.path.isfile(srt_path) and os.path.getsize(srt_path) > 0

    if skip_audio:
        print(f"   → [RESUME] Reusing existing voiceover: {audio_path}")
    else:
        audio_path = generate_narration(script, run_output_dir)
    print(f"\n  [OK] Audio: {audio_path}")

    # ── 5. Video ──────────────────────────────────────────────
    banner("5 / 6  ·  Building video  [MoviePy]")
    video_path = os.path.join(run_output_dir, "final_video.mp4")
    skip_video = from_step_num > 5 and os.path.isfile(video_path) and os.path.getsize(video_path) > 0
    if skip_video:
        print(f"   → [RESUME] Reusing existing video: {video_path}")
    else:
        video_path = create_video(script, audio_path, run_output_dir, image_map)
    video_path = os.path.abspath(video_path)

    # ── 6. Review ─────────────────────────────────────────────
    banner("6 / 6  ·  Human review  [Flask dashboard]")
    if args.no_review:
        print(f"\n  [OK] Final video generated at: {video_path}")
        print("  → Skipping review dashboard (--no-review set). Pipeline complete!\n")
        return

    print("\n  → Opening review dashboard in your browser…")
    review_data = {
        "research":   research,
        "script":     script,
        "video_path": video_path,
    }
    with open(f"{run_output_dir}/review_data.json", "w", encoding="utf-8") as f:
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
        print(f"      Tip: edit {script_file} and re-run just the video step.\n")


if __name__ == "__main__":
    run()

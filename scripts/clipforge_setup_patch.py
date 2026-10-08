#!/usr/bin/env python3
"""
ClipForge setup patch — run once inside your fork of youtube-agentic-ai-studio:
    python3 clipforge_setup_patch.py
Applies: env-var keys, Beat or Miss channel identity, gemma-4-31b-it default,
and the creator.py channel-watermark fix. Idempotent.
"""
import re, shutil
from pathlib import Path

root = Path(__file__).parent
# If the script lives in a subfolder (e.g. scripts/), walk up to the repo root
if not (root / "config.py").exists():
    for parent in Path(__file__).resolve().parents:
        if (parent / "config.py").exists():
            root = parent
            break

def patch(path, fn, desc):
    p = root / path
    src = p.read_text(encoding="utf-8")
    new = fn(src)
    if new != src:
        shutil.copy(p, str(p) + ".orig.bak")
        p.write_text(new, encoding="utf-8")
        print(f"  OK  {desc}")
    else:
        print(f"  --  {desc} (already applied)")

# 1. config.py — keys from env
def keys(src):
    src, _ = re.subn(r'^GEMINI_API_KEY\s*=.*$', 'GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")', src, flags=re.M)
    src, _ = re.subn(r'^PEXELS_API_KEY\s*=.*$', 'PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")', src, flags=re.M)
    src, _ = re.subn(r'^ELEVENLABS_API_KEY\s*=.*$', 'ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")  # optional', src, flags=re.M)
    return src
patch("config.py", keys, "config.py: API keys read from env")

# 1b. config.py — load .env via python-dotenv (no-op if the package isn't installed)
def dotenv_loader(src):
    if "load_dotenv" in src:
        return src
    anchor = "import os"
    loader = anchor + "\ntry:\n    from dotenv import load_dotenv\n    load_dotenv()\nexcept ImportError:\n    pass\n"
    return src.replace(anchor, loader, 1)
patch("config.py", dotenv_loader, "config.py: load .env via python-dotenv")

# 1c. requirements.txt — python-dotenv must be installed for the .env loader
def dotenv_req(src):
    if "python-dotenv" in src:
        return src
    if not src.endswith("\n"):
        src += "\n"
    return src + "python-dotenv>=1.0.0\n"
patch("requirements.txt", dotenv_req, "requirements.txt: add python-dotenv")

# 2. config.py — channel identity
def channel(src):
    src = src.replace('CHANNEL_NAME = "My AI Channel"',
                      'CHANNEL_NAME = "Beat or Miss"   # shown on-screen and in upload metadata')
    return src
patch("config.py", channel, "config.py: CHANNEL_NAME = Beat or Miss")

def channel_desc(src):
    old_start = src.find('CHANNEL_DESCRIPTION = """')
    if old_start == -1:
        return src
    old_end = src.find('"""', old_start + len('CHANNEL_DESCRIPTION = """')) + 3
    new_block = '''CHANNEL_DESCRIPTION = """
A finance channel that turns earnings season into plain-English insight.
Each video breaks down a company's quarterly earnings report and earnings call — revenue, EPS vs expectations,
margins, guidance, and the 2-3 takeaways that actually matter — as 60-90 second Shorts and deeper 6-8 minute analyses.
No hype, no stock picks, no price targets: just what the company reported and what it means, verified against the numbers.
Target audience: retail investors and curious professionals who want the signal from earnings without reading the 10-Q.
"""'''
    return src[:old_start] + new_block + src[old_end:]
patch("config.py", channel_desc, "config.py: CHANNEL_DESCRIPTION -> earnings")

# 3b. agents/gemini_client.py — refresh the model fallback chain (repo predates Gemini 3.x)
def model_chain(src):
    if "gemini-3.8-flash" in src:
        return src
    src = src.replace(
        '_ALL_MODELS = [\n    "gemini-2.5-flash",',
        '_ALL_MODELS = [\n    "gemini-3.8-flash",\n    "gemini-3.7-flash",\n    "gemini-2.5-flash",',
        1)
    return src
patch("agents/gemini_client.py", model_chain, "gemini_client.py: add Gemini 3.8/3.7 Flash to fallback chain")

# 3c. config.py — default model -> gemini-3.8-flash (newest free tier; the
#      fallback chain auto-moves on if a model 404s, so this is safe)
def model_default(src):
    if 'GEMINI_MODEL = "gemini-3.8-flash"' in src:
        return src
    import re as _re
    return _re.sub(r'^GEMINI_MODEL\s*=.*$', 'GEMINI_MODEL = "gemini-3.8-flash"', src, flags=_re.M)
patch("config.py", model_default, 'config.py: default model -> gemini-3.8-flash')

# 4. video/creator.py — watermark used the author's hardcoded channel name
def brand(src):
    return src.replace('"▶ FRACTURED TIMELINES"', '"▶ " + config.CHANNEL_NAME.upper()')
patch("video/creator.py", brand, "creator.py: watermark uses config.CHANNEL_NAME")

# 5. pipeline.py — CLI flags: --topic, --shorts, --images-dir
def pipeline_helpers(src):
    if "_parse_args" in src:
        return src
    anchor = 'def run():'
    helpers = '''def _parse_args():
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
    """Map user-supplied images to script sections by filename: 1.png, 2.jpg, ..."""
    image_map = {}
    for s in script.get("sections", []):
        sid = s["id"]
        paths = []
        for ext in ("png", "jpg", "jpeg", "webp"):
            for cand in (f"{sid}.{ext}", f"section_{sid:02d}.{ext}"):
                p = os.path.join(images_dir, cand)
                if os.path.isfile(p):
                    paths.append(p)
        image_map[sid] = sorted(set(paths))
    found = sum(1 for v in image_map.values() if v)
    print(f"   → manual images: {found}/{len(image_map)} sections covered")
    return image_map


'''
    return src.replace(anchor, helpers + anchor, 1)
patch("pipeline.py", pipeline_helpers, "pipeline.py: add _parse_args/_load_manual_images helpers")

def pipeline_wiring(src):
    if "args.images_dir" in src:
        return src
    src = src.replace(
        "    research = research_topic(config.CHANNEL_DESCRIPTION)",
        "    args = _parse_args()\n    research = research_topic(config.CHANNEL_DESCRIPTION, topic_override=args.topic)",
        1)
    # guard: only add args = _parse_args() once (replace above already includes it)
    src = src.replace(
        '    script = write_script(research)',
        '    script = write_script(research, video_type="shorts" if args.shorts else "normal")',
        1)
    src = src.replace(
        "    image_map = download_images(script, config.OUTPUT_DIR)",
        "    if args.images_dir and os.path.isdir(args.images_dir):\n"
        "        image_map = _load_manual_images(script, args.images_dir)\n"
        "    else:\n"
        "        image_map = download_images(script, config.OUTPUT_DIR)",
        1)
    return src
patch("pipeline.py", pipeline_wiring, "pipeline.py: wire --topic/--shorts/--images-dir into run()")

# 5b. pipeline.py — _load_manual_images: the scriptwriter sometimes emits string
#      section ids (e.g. "hook_q1_reaction"), so also match by 1-based position.
def manual_images_v2(src):
    if "1-based position" in src:
        return src
    old_fn = '''def _load_manual_images(script: dict, images_dir: str) -> dict:
    """Map user-supplied images to script sections by filename: 1.png, 2.jpg, ..."""
    image_map = {}
    for s in script.get("sections", []):
        sid = s["id"]
        paths = []
        for ext in ("png", "jpg", "jpeg", "webp"):
            for cand in (f"{sid}.{ext}", f"section_{sid:02d}.{ext}"):
                p = os.path.join(images_dir, cand)
                if os.path.isfile(p):
                    paths.append(p)
        image_map[sid] = sorted(set(paths))
    found = sum(1 for v in image_map.values() if v)
    print(f"   → manual images: {found}/{len(image_map)} sections covered")
    return image_map'''
    new_fn = '''def _load_manual_images(script: dict, images_dir: str) -> dict:
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
    return image_map'''
    return src.replace(old_fn, new_fn, 1)
patch("pipeline.py", manual_images_v2, "pipeline.py: _load_manual_images matches by position too")

# 5c. pipeline.py — step-3 banner reflects the image source; warn if --images-dir is missing
def images_banner(src):
    if "Loading manual images" in src:
        return src
    old = '''    banner("3 / 6  ·  Downloading stock images  [Pexels]")
    if args.images_dir and os.path.isdir(args.images_dir):
        image_map = _load_manual_images(script, args.images_dir)
    else:
        image_map = download_images(script, config.OUTPUT_DIR)'''
    new = '''    if args.images_dir and os.path.isdir(args.images_dir):
        banner("3 / 6  ·  Loading manual images  [--images-dir]")
        image_map = _load_manual_images(script, args.images_dir)
    elif args.images_dir:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        print(f"   ⚠ --images-dir not found: {args.images_dir} — falling back to Pexels")
        image_map = download_images(script, config.OUTPUT_DIR)
    else:
        banner("3 / 6  ·  Downloading stock images  [Pexels]")
        image_map = download_images(script, config.OUTPUT_DIR)'''
    return src.replace(old, new, 1)
patch("pipeline.py", images_banner, "pipeline.py: step-3 banner shows image source + missing-dir warning")

# 5d. pipeline.py — absolute video path: Flask's send_file resolves relative paths
#      against the review app's own directory (review/output/... -> 500 error)
def video_abspath(src):
    if "os.path.abspath(video_path)" in src:
        return src
    return src.replace(
        "    video_path = create_video(script, audio_path, config.OUTPUT_DIR, image_map)",
        "    video_path = create_video(script, audio_path, config.OUTPUT_DIR, image_map)\n"
        "    video_path = os.path.abspath(video_path)  # review server misresolves relative paths",
        1)
patch("pipeline.py", video_abspath, "pipeline.py: absolute video path for review server")

# 7. video/creator.py — section-aware Shorts: each section's image(s) stay on
#    screen while that section is narrated (timing from word counts), shown
#    clearly with only a light dim, instead of a 2.5s rotation loop at 45% dim.
def shorts_section_aware(src):
    if "Section-aware Shorts builder" in src:
        return src
    import re as _re
    new_fn = '''def _build_shorts_clip(section_shots: list, sections: list, total_duration: float,
                       captions: list) -> VideoClip:
    """
    Section-aware Shorts builder.

    Each section's image(s) stay on screen for the whole time that section
    is narrated — timing estimated from word counts, scaled to the true
    audio duration — instead of a fixed 2.5 s rotation looping all images.
    Visuals are shown clearly with only a light dim so charts stay readable;
    a short crossfade eases the handoff between sections.
    """
    # ── Section time windows: proportional to narration word counts ──
    words   = [max(1, len(s.get("narration", "").split())) for s in sections]
    total_w = sum(words)
    bounds  = [0.0]
    for w in words:
        bounds.append(bounds[-1] + total_duration * w / total_w)

    XFADE = 0.6   # crossfade seconds at each section boundary
    DIM   = 0.15  # light dim — keeps charts/text clearly readable

    def _section_at(t):
        for i in range(len(sections)):
            if t < bounds[i + 1]:
                return i
        return len(sections) - 1

    def _render_shot(shots, t_local, idx):
        img = shots[int(t_local / 4.0) % len(shots)] if len(shots) > 1 else shots[0]
        frame = _zoom_pulse(img, t_local, idx)
        frame = _apply_overlay(frame, opacity=DIM)
        return _apply_vignette(frame)

    def make_frame(t):
        i = _section_at(t)
        t0    = bounds[i]
        shots = section_shots[i] if i < len(section_shots) else []
        if shots:
            frame_np = _render_shot(shots, t - t0, i)
            # ease in from the previous section's visual at the boundary
            if t - t0 < XFADE and i > 0:
                prev = section_shots[i - 1]
                if prev:
                    prev_dur = t0 - bounds[i - 1]
                    a = (t - t0) / XFADE
                    a = a * a * (3.0 - 2.0 * a)  # smoothstep
                    pf = _render_shot(prev, prev_dur, i - 1)
                    frame_np = (frame_np.astype(np.float32) * a +
                                pf.astype(np.float32) * (1.0 - a)).astype(np.uint8)
        else:
            frame_np = _gradient_bg(t)

        frame = Image.fromarray(frame_np)

        # ── Captions ─────────────────────────────────────────
        cap_text = _get_caption_at(captions, t)
        frame    = _draw_shorts_caption(frame, cap_text)

        # ── Top brand strip ──────────────────────────────────
        draw       = ImageDraw.Draw(frame)
        font_brand = _load_font("bold", 30)
        brand      = "▶ " + config.CHANNEL_NAME.upper()
        bbox       = draw.textbbox((0, 0), brand, font=font_brand)
        bw         = bbox[2] - bbox[0]
        draw.text(((W - bw) // 2, 50), brand, font=font_brand,
                  fill=(255, 255, 255, 160))

        return np.array(frame)

    return VideoClip(make_frame, duration=total_duration)
'''
    pattern = r"def _build_shorts_clip\(all_images.*?\n    return VideoClip\(make_frame, duration=total_duration\)\n"
    src2, n = _re.subn(pattern, new_fn, src, flags=_re.DOTALL)
    if n != 1:
        print("  !! shorts_section_aware: expected 1 match, got", n)
        return src
    # call-site: keep per-section lists instead of flattening
    old_flat = '''        # Flatten all section image lists into one ordered list
        all_images = []
        for section in script["sections"]:
            sid   = section["id"]
            paths = (image_map or {}).get(sid, [])
            if isinstance(paths, str):
                paths = [paths]   # handle single-path fallback
            for p in paths:
                arr = _load_bg_image(p)
                if arr is not None:
                    all_images.append(arr)

        if not all_images:
            print("   ⚠ No images loaded — using animated gradient")'''
    new_flat = '''        # Per-section image lists — kept section-aware so each visual shows
        # while its own section is narrated (not a blind rotation loop)
        section_shots = []
        for section in script["sections"]:
            sid   = section["id"]
            paths = (image_map or {}).get(sid, [])
            if isinstance(paths, str):
                paths = [paths]   # handle single-path fallback
            shots = []
            for p in paths:
                arr = _load_bg_image(p)
                if arr is not None:
                    shots.append(arr)
            section_shots.append(shots)

        n_loaded = sum(len(s) for s in section_shots)
        if n_loaded == 0:
            print("   ⚠ No images loaded — using animated gradient")'''
    if old_flat not in src2:
        print("  !! shorts_section_aware: call-site block not found")
        return src
    src2 = src2.replace(old_flat, new_flat, 1)
    src2 = src2.replace(
        '''        print(f"   → {len(all_images)} images → "
              f"~{len(all_images) * SHORTS_IMG_DURATION:.0f}s slideshow material")''',
        '''        for s, shots in zip(script["sections"], section_shots):
            print(f"   → section {s['id']}: {len(shots)} image(s)")''',
        1)
    src2 = src2.replace(
        "        final = _build_shorts_clip(all_images, total_dur, captions)",
        "        final = _build_shorts_clip(section_shots, script[\"sections\"], total_dur, captions)",
        1)
    return src2
patch("video/creator.py", shorts_section_aware, "creator.py: section-aware Shorts (image per narrated section, light dim)")

# 6. rerender.py — NEW FILE. Re-runs only the image + video steps from existing
#    outputs (output/script.json + output/narration.mp3). No extra Gemini/TTS calls.
#    Run: python rerender.py --images-dir <folder>
_RERENDER = '''"""Re-render the video from existing outputs with (new) manual images.

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
from video.creator import create_video


def main():
    ap = argparse.ArgumentParser(description="Re-render video with manual images")
    ap.add_argument("--images-dir", required=True,
                    help="Folder of per-section images (1.png, 2.png, ...)")
    ap.add_argument("--script", default=os.path.join(config.OUTPUT_DIR, "script.json"))
    ap.add_argument("--audio", default=os.path.join(config.OUTPUT_DIR, "narration.mp3"))
    args = ap.parse_args()

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
    print(f"\\n  ✅ Re-rendered: {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
'''
def _write_rerender():
    p = root / "rerender.py"
    if p.exists():
        print("  --  rerender.py (already exists)")
        return
    p.write_text(_RERENDER, encoding="utf-8")
    print("  OK  rerender.py: re-render from existing outputs (new file)")
_write_rerender()

# 8. Progress logging for renders: creator.py gains a _PROGRESS_EVERY hook,
#    rerender.py enables it (the render is otherwise completely silent).
def render_progress(src):
    if "_PROGRESS_EVERY" in src:
        return src
    anchor = "def _build_shorts_clip(section_shots: list, sections: list, total_duration: float,"
    helper = "_PROGRESS_EVERY = 0  # seconds of video between progress prints; 0 = silent\n\n\n"
    if anchor not in src:
        print("  !! render_progress: section-aware builder not found — run patch 7 first")
        return src
    src = src.replace(anchor, helper + anchor, 1)
    old = """    def make_frame(t):
        i = _section_at(t)
        t0    = bounds[i]"""
    new = """    def make_frame(t):
        i = _section_at(t)
        if _PROGRESS_EVERY:
            tick = int(t) // _PROGRESS_EVERY
            if tick != make_frame._last_tick:
                make_frame._last_tick = tick
                print(f"   … render t={t:.0f}s / {total_duration:.0f}s", flush=True)
        t0    = bounds[i]"""
    if old not in src:
        print("  !! render_progress: make_frame anchor not found")
        return src
    src = src.replace(old, new, 1)
    src = src.replace(
        "        return np.array(frame)\n\n    return VideoClip(make_frame, duration=total_duration)",
        "        return np.array(frame)\n\n    make_frame._last_tick = -1\n    return VideoClip(make_frame, duration=total_duration)",
        1)
    return src
patch("video/creator.py", render_progress, "creator.py: _PROGRESS_EVERY render progress hook")

def rerender_progress(src):
    if "_PROGRESS_EVERY" in src:
        return src
    if "from video.creator import create_video" not in src:
        return src
    src = src.replace(
        "from video.creator import create_video",
        "import video.creator as _vc\nfrom video.creator import create_video",
        1)
    src = src.replace(
        "    args = ap.parse_args()\n",
        "    args = ap.parse_args()\n    _vc._PROGRESS_EVERY = 5  # progress print every 5s of video\n",
        1)
    return src
patch("rerender.py", rerender_progress, "rerender.py: enable render progress logging")

# 9. .gitignore — never commit patch backups (the first .orig.bak may contain
#    the original config.py with a pasted-in API key) or local .env
def gitignore_bak(src):
    changed = False
    for line in ("*.orig.bak", ".env"):
        if line not in src.splitlines():
            if src and not src.endswith("\n"):
                src += "\n"
            src += line + "\n"
            changed = True
    if changed:
        print("  OK  .gitignore: ignore *.orig.bak and .env")
    else:
        print("  --  .gitignore (already covers *.orig.bak and .env)")
    return src

def _gitignore():
    p = root / ".gitignore"
    src = p.read_text(encoding="utf-8") if p.exists() else ""
    new = gitignore_bak(src)
    if new != src:
        p.write_text(new, encoding="utf-8")
_gitignore()

print("Done. Next: cp .env.example .env, fill in your keys, then: python3 -m venv venv && venv/bin/pip install -r requirements.txt && python pipeline.py")

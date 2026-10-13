"""
Research Agent — uses shared Gemini client with model fallback chain.
Banned topics are read from banned_topics.txt (one topic per line) in the
project root. Edit that file — or use the GUI textarea — instead of changing
Python code.
"""
import json
import os
import re
import random
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
from agents.gemini_client import generate

# Path to the banned-topics file (sits next to this package's parent directory)
_BANNED_TOPICS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "banned_topics.txt",
)

_BUILTIN_BANNED = [
    "The Boltzmann Brain",
    "Simulation Theory",
    "Quantum Immortality",
]

# All available focus angles — used by researcher AND exposed to the GUI
FOCUS_ANGLES = [
    "Theoretical Physics & Time Travel",
    "The Dark Forest Theory & Aliens",
    "Existential Human Psychology & Illusions",
    "Frightening AI Futures & Simulation Theory",
    "Mind-bending Mathematical Paradoxes",
    "The limits of Human Biology & Immortality",
    "Quantum Mechanics & Alternate Realities",
    "Cosmic scale, Black Holes, and the end of the Universe",
    "Neuroscience & the Mystery of Consciousness",
    "Ancient Civilisations & Lost History",
    "Cutting-edge Biotechnology & Genetic Engineering",
    "The Future of Space Colonisation",
]


def load_banned_topics() -> list:
    """
    Return the combined list of banned topics.
    Built-in list is always included; file entries are appended.
    Returns an empty-safe list — never raises.
    """
    topics = list(_BUILTIN_BANNED)
    try:
        if os.path.exists(_BANNED_TOPICS_FILE):
            with open(_BANNED_TOPICS_FILE, encoding="utf-8") as f:
                for line in f:
                    t = line.strip()
                    if t and not t.startswith("#") and t not in topics:
                        topics.append(t)
    except Exception as e:
        print(f"   ⚠ Could not read banned_topics.txt: {e}")
    return topics


def save_banned_topics(topics: list) -> None:
    """
    Write the user-managed portion of the banned list to banned_topics.txt.
    Built-in topics are excluded from the file (they're always applied anyway).
    """
    user_topics = [t for t in topics if t not in _BUILTIN_BANNED and t.strip()]
    with open(_BANNED_TOPICS_FILE, "w", encoding="utf-8") as f:
        f.write("# One banned topic per line. Lines starting with # are comments.\n")
        f.write("# Built-in banned: The Boltzmann Brain, Simulation Theory, Quantum Immortality\n")
        f.write("# Add topics here after you make a video about them.\n\n")
        for t in user_topics:
            f.write(t + "\n")


def extract_earnings_tags(text: str) -> tuple[str, str, str] | None:
    """Extract (ticker, quarter, fy) from topic string if present."""
    if not text:
        return None
    m = re.search(r'\b([A-Za-z]{1,5})\b.*?\b(Q[1-4])\b.*?\b(FY\d{2,4}|20\d{2})\b', text, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).upper(), m.group(3).upper()
    m2 = re.search(r'([A-Za-z]{1,5})-q([1-4])-(\w+)', text, re.IGNORECASE)
    if m2:
        return m2.group(1).upper(), f"Q{m2.group(2)}", m2.group(3).upper()
    return None


def research_topic(channel_description: str,
                   topic_override: str = "",
                   focus_angle: str = "") -> dict:
    """
    Research a video topic for the channel.
    """
    banned     = load_banned_topics()
    banned_str = ", ".join(f'"{t}"' for t in banned)

    # ── MODE 1: USER-SPECIFIED EXACT TOPIC ───────────────────────────────────
    if topic_override.strip():
        exact_topic = topic_override.strip()
        print(f"   → Exact topic override: \"{exact_topic}\"")

        earnings_info = extract_earnings_tags(exact_topic)
        if earnings_info:
            ticker, quarter, fy = earnings_info
            print(f"   → Detected Earnings Subject: {ticker} {quarter} {fy}")
            prompt = f"""You are a top Wall Street financial analyst and content strategist for '{config.CHANNEL_NAME}'.
Channel description:
{channel_description}

MANDATORY INSTRUCTION: Conduct research on this quarterly earnings report:
>>> {exact_topic} <<<

CRITICAL INSTRUCTIONS:
1. Provide the VERIFIED earnings actuals for {ticker} for {quarter} {fy} (Revenue, Adj EPS, Beat vs Miss, Guidance, Operating Highlights).
2. Never substitute estimates for verified actuals.
3. Structure the output with accurate financial metrics for the 3 'Beat or Miss' section cards:
   - "price_trend": subtitle, metrics (YTD, 3M, 1M, 1W, Day, Reaction with positive true/false), day_levels (list of strings), reaction_box (title, subtitle, positive)
   - "scorecard": subtitle, revenue (label, est, actual, verdict, yoy), eps (label, est, actual, verdict), operating_numbers (list of {{"title": "...", "subtitle": "..."}})
   - "takeaway": subtitle, verdict_banner, guidance (verdict, points with {{"title": "...", "subtitle": "..."}}), capital_return (title, details, subtitle), sentiment_drivers (list of strings)
4. Include gripping YouTube title, SEO description, hook question, 5 key points, and tags.

Respond with ONLY a valid JSON object. No markdown fences, no explanation:
{{
  "ticker": "{ticker}",
  "quarter": "{quarter}",
  "fy": "{fy}",
  "topic": "{exact_topic}",
  "why_now": "Why this earnings report matters right now",
  "video_title": "{ticker} {quarter} {fy} Earnings: Beat or Miss?",
  "description": "2-sentence YouTube description optimized for SEO and curiosity",
  "hook_question": "The single most critical question this quarterly earnings report answers",
  "key_points": [
    "Revenue actual vs consensus estimate",
    "EPS performance and margin trends",
    "Key operating metrics and segment highlights",
    "Guidance verdict and forward targets",
    "Primary takeaway and stock reaction"
  ],
  "target_audience": "Retail investors and market watchers",
  "tags": ["{ticker}", "Stocks", "Earnings", "{quarter}", "{fy}", "Investing", "Finance"],
  "thumbnail_concept": "{ticker} stock chart with BEAT or MISS verdict badge",
  "estimated_virality": "high",
  "price_trend": {{
    "subtitle": "Price action & trend into the print",
    "metrics": [
      {{"label": "YTD", "value": "+12.5%", "positive": true}},
      {{"label": "3M", "value": "+4.2%", "positive": true}},
      {{"label": "1M", "value": "-1.5%", "positive": false}},
      {{"label": "1W", "value": "-0.8%", "positive": false}},
      {{"label": "Day", "value": "-1.2%", "positive": false}},
      {{"label": "Reaction", "value": "+2.8%", "positive": true}}
    ],
    "day_levels": [
      "Prior close to reaction move",
      "Distance from 52-week high",
      "Key moving average levels"
    ],
    "reaction_box": {{
      "title": "Earnings Reaction: +2.8%",
      "subtitle": "Reaction on verified numbers",
      "positive": true
    }}
  }},
  "scorecard": {{
    "subtitle": "Actual vs analyst expectations",
    "revenue": {{
      "label": "Revenue ($B)",
      "est": "10.0",
      "actual": "10.2",
      "verdict": "BEAT",
      "yoy": "+5% YoY"
    }},
    "eps": {{
      "label": "Adj. EPS",
      "est": "1.20",
      "actual": "1.25",
      "verdict": "BEAT"
    }},
    "operating_numbers": [
      {{"title": "Core revenue expansion", "subtitle": "Volume and pricing growth"}},
      {{"title": "Operating margin progression", "subtitle": "Operational leverage"}},
      {{"title": "Segment growth", "subtitle": "Key division performance"}}
    ]
  }},
  "takeaway": {{
    "subtitle": "The Verdict & Outlook",
    "verdict_banner": "PRINT: BEAT  -  GUIDANCE: RAISED",
    "guidance": {{
      "verdict": "RAISED",
      "points": [
        {{"title": "FY revenue guidance updated", "subtitle": "Reflecting strong momentum"}},
        {{"title": "Full-year EPS outlook raised", "subtitle": "Margin strength continuing"}}
      ]
    }},
    "capital_return": {{
      "title": "Dividend & Share Repurchases",
      "details": "Consistent shareholder returns",
      "subtitle": "Capital returns active"
    }},
    "sentiment_drivers": [
      "Management commentary on demand trends",
      "Wall Street analyst reactions and price targets",
      "Key catalysts for the upcoming quarter"
    ]
  }}
}}"""
        else:
            prompt = f"""You are a top YouTube content strategist for a viral science/tech channel.

Channel description:
{channel_description}

MANDATORY INSTRUCTION: You MUST make a video about this EXACT topic:
>>> {exact_topic} <<<

Do NOT substitute a different topic, do NOT pick a related angle — write specifically
about "{exact_topic}". The user has explicitly requested this topic.

BANNED TOPICS: Do NOT include any of these in the output: {banned_str}
If the requested topic conflicts with a banned one, still write about it (user override).

Your mission: Research and plan a compelling 6-8 minute YouTube video about "{exact_topic}".

Respond with ONLY a valid JSON object. No markdown fences, no explanation:

{{
  "topic": "{exact_topic}",
  "why_now": "Why this topic resonates with audiences right now",
  "video_title": "MIND-BLOWING YouTube title under 70 characters about {exact_topic}",
  "description": "2-sentence YouTube description optimised for SEO and curiosity",
  "hook_question": "The single most mind-blowing question this video answers",
  "key_points": [
    "First key concept or revelation about {exact_topic}",
    "Second key concept — the twist or surprise",
    "Third key concept — deeper implication",
    "Fourth key concept — real-world consequence",
    "Fifth key concept — the philosophical angle"
  ],
  "target_audience": "Exactly who will watch and share this",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],
  "thumbnail_concept": "Describe the perfect YouTube thumbnail for this topic",
  "estimated_virality": "high"
}}"""


        raw = generate(prompt)
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$",          "", raw).strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError(f"Researcher returned no JSON.\nRaw:\n{raw[:600]}")
        data = json.loads(match.group())
        for field in ["topic", "video_title", "key_points", "tags"]:
            if field not in data:
                raise ValueError(f"Research JSON missing field: '{field}'")
        return data

    # ── MODE 2: AI PICKS THE TOPIC ───────────────────────────────────────────
    # Use focus_angle if supplied by the GUI dropdown; otherwise pick randomly.
    if focus_angle.strip():
        chosen_angle = focus_angle.strip()
        print(f"   → Focus angle (GUI selected): {chosen_angle}")
    else:
        chosen_angle = random.choice(FOCUS_ANGLES)
        print(f"   → Focus angle (random): {chosen_angle}")

    print(f"   → Asking Gemini for topic ideas within: {chosen_angle}")

    prompt = f"""You are a top YouTube content strategist for a viral science/tech channel.

Channel description:
{channel_description}

CRITICAL INSTRUCTIONS FOR THIS RUN:
1. Focus entirely on this specific theme: >>> {chosen_angle} <<<
2. BANNED TOPICS: Do NOT suggest any of the following — we already made videos about them: {banned_str}. You must give me a brand new, highly original concept.
3. Cache Bust ID: {time.time()} (Ensure completely unique output).

Your mission:
1. Think of 3-4 highly compelling video topic ideas within that specific theme.
2. Select the single BEST topic that is genuinely mind-blowing, timely, and explainable in 6-8 minutes.

Respond with ONLY a valid JSON object. No markdown fences, no explanation:

{{
  "topic": "The specific video topic",
  "why_now": "Why this topic is hitting the zeitgeist right now",
  "video_title": "MIND-BLOWING YouTube title under 70 characters",
  "description": "2-sentence YouTube description optimised for SEO and curiosity",
  "hook_question": "The single most mind-blowing question this video answers",
  "key_points": [
    "First key concept or revelation",
    "Second key concept — the twist or surprise",
    "Third key concept — deeper implication",
    "Fourth key concept — real-world consequence",
    "Fifth key concept — the philosophical angle"
  ],
  "target_audience": "Exactly who will watch and share this",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],
  "thumbnail_concept": "Describe the perfect YouTube thumbnail",
  "estimated_virality": "high"
}}"""

    raw = generate(prompt)
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$",          "", raw).strip()

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"Researcher returned no JSON.\nRaw:\n{raw[:600]}")

    data = json.loads(match.group())
    for field in ["topic", "video_title", "key_points", "tags"]:
        if field not in data:
            raise ValueError(f"Research JSON missing field: '{field}'")
    return data

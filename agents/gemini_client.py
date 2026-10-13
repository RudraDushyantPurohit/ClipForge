"""
Gemini / Gemma Client — shared across all agents.
Tries models in order starting from config.GEMINI_MODEL, then falls back
through the rest of the chain until one works.
Free-tier daily limits (approximate):
  gemini-2.5-flash      → 500 req/day
  gemini-2.0-flash      → 1,500 req/day
  gemini-2.0-flash-lite → 1,500 req/day
  gemma-4-31b-it        → 500 req/day
  gemini-1.5-flash-001  → 1,500 req/day
If ALL are exhausted, wait until midnight Pacific and try again.
"""
import os
import shutil
import subprocess
import time
import config

# Full list of supported models in preference order for the API fallback chain.
_ALL_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-4-31b-it",        # Gemma 4 31B dense — strong reasoning, free tier
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemma-3-27b-it",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro-001",
]


def _find_agy_executable() -> str:
    """Find agy executable in PATH or standard installation paths."""
    found = shutil.which("agy") or shutil.which("agy.exe")
    if found:
        return found
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"),
        os.path.expanduser(r"~/.gemini/antigravity-cli/bin/agy.exe"),
        r"C:\Users\siddh\AppData\Local\agy\bin\agy.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "agy"


def _generate_via_agy(prompt: str, model: str | None = None, enable_tools: bool = False) -> str:
    """Execute prompt non-interactively via Antigravity CLI (agy)."""
    agy_cmd = _find_agy_executable()
    selected_model = model or getattr(config, "AGY_MODEL", "gemini-3.8-flash-high")

    cmd = [
        agy_cmd,
        "--input-format", "text",
        "--output-format", "text",
        "--disable-slash-commands",
    ]
    if enable_tools:
        cmd.append("--dangerously-skip-permissions")
    if selected_model:
        cmd.extend(["--model", selected_model])

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    stdout, stderr = proc.communicate(input=prompt)

    if proc.returncode != 0:
        err_msg = stderr.strip() or stdout.strip()
        raise RuntimeError(f"agy CLI execution failed (code {proc.returncode}):\n{err_msg}")

    return stdout.strip()


def build_chain(starting_model: str | None = None) -> list:
    """
    Return MODEL_CHAIN rotated so `starting_model` is first.
    If starting_model is not in the list (typo / unknown), falls back to
    the default order so generation always has a working chain.
    """
    preferred = (starting_model or "").strip()
    if preferred and preferred in _ALL_MODELS:
        idx = _ALL_MODELS.index(preferred)
        return _ALL_MODELS[idx:] + _ALL_MODELS[:idx]
    return list(_ALL_MODELS)

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _should_switch_model(err: Exception) -> bool:
    """Return True for any error code that means we should try the next model."""
    msg = str(err)
    return any(k in msg for k in [
        "429", "RESOURCE_EXHAUSTED", "quota", "rate limit",  # 429 – quota
        "503", "UNAVAILABLE", "overloaded", "high demand",   # 503 – overloaded
        "500", "INTERNAL",                                    # 500 – transient
        "404", "NOT_FOUND", "not found",                     # 404 – model gone
    ])


def _generate_via_gemini_api(prompt: str, starting_model: str | None = None) -> str:
    from google.genai import types
    client = _get_client()
    chain  = build_chain(starting_model or getattr(config, "GEMINI_MODEL", None))

    for model in chain:
        for attempt in range(3):   # up to 3 attempts per model before moving on
            try:
                print(f"   → Using {model}…")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.9),
                )
                return response.text.strip()

            except Exception as e:
                if _should_switch_model(e):
                    if attempt < 2:
                        wait = 15 * (attempt + 1)   # 15s then 30s
                        print(f"   ⚠ {model} error (attempt {attempt+1}/3) — waiting {wait}s…")
                        time.sleep(wait)
                    else:
                        print(f"   ⚠ {model} failed 3 times — trying next model…")
                else:
                    raise   # auth error or bug — surface immediately

    raise RuntimeError(
        "\n\n❌  All Gemini models failed.\n"
        "    • 503/500 = temporary — wait a few minutes and retry\n"
        "    • 429 = quota — wait until midnight Pacific or add billing\n"
        "      https://aistudio.google.com/apikey\n"
    )


def generate(prompt: str, starting_model: str | None = None, enable_tools: bool = False) -> str:
    """
    Generate text using configured LLM_BACKEND ("agy" or "gemini_api").
    Defaults to Antigravity CLI ('agy') in headless mode.
    """
    backend = getattr(config, "LLM_BACKEND", "agy").lower()
    if backend == "agy":
        return _generate_via_agy(prompt, model=starting_model, enable_tools=enable_tools)
    return _generate_via_gemini_api(prompt, starting_model=starting_model)
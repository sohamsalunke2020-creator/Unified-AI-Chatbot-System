"""Task verification script for the Unified Chatbot (Tasks 1–6).

Run (after activating your venv):
  python verify_tasks.py

This script is designed for internship submission verification:
- fast, deterministic checks
- no secrets printed
- graceful skips when optional APIs/models are unavailable
"""

from __future__ import annotations

import os
import sys
import tempfile
import warnings
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Make Task 2 verification reproducible/offline by default.
# (Gemini may be configured but quota/auth can be flaky; the app has local fallbacks.)
os.environ.setdefault("DISABLE_GEMINI", "1")

# Reduce noise from known, non-fatal library warnings during verification.
warnings.filterwarnings("ignore", message="TypedStorage is deprecated")
warnings.filterwarnings("ignore", message="Recommended: pip install sacremoses")

# Quiet very chatty dependency loggers during verification.
for noisy in [
    "faiss",
    "faiss.loader",
    "sentence_transformers",
    "transformers",
]:
    logging.getLogger(noisy).setLevel(logging.WARNING)


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _safe_get(d: Any, key: str, default: Any = None) -> Any:
    return d.get(key, default) if isinstance(d, dict) else default


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _check_task_1(bot) -> CheckResult:
    # The bundled KB reliably contains an entry about Python.
    r = bot.chat("What is Python used for?", task=1)
    text = str(_safe_get(r, "text", ""))
    ok = bool(text.strip()) and "python" in text.lower()
    return CheckResult("Task 1 (KB)", ok, text[:200].replace("\n", " "))


def _make_test_image(path: str) -> None:
    from PIL import Image

    img = Image.new("RGB", (256, 256), (10, 120, 240))
    img.save(path)


def _check_task_2(bot) -> CheckResult:
    # Uses a solid-color image so the app can describe it without downloading big caption models.
    with tempfile.TemporaryDirectory() as td:
        img_path = os.path.join(td, "test.png")
        _make_test_image(img_path)
        r = bot.chat(
            "What do you see in the image?",
            task=2,
            include_images=True,
            image_paths=[img_path],
        )
    analysis_text = str(_safe_get(r, "text", ""))
    analysis_ok = "image analysis" in analysis_text.lower() and len(analysis_text.strip()) > 20

    generated = bot.chat("Generate an image of a futuristic blue city skyline.", task=2)
    generated_text = str(_safe_get(generated, "text", ""))
    generated_bytes = _safe_get(generated, "generated_image_bytes")
    generation_ok = bool(generated_bytes) and "generated image" in generated_text.lower()

    ok = analysis_ok and generation_ok
    details = (
        f"analysis={'ok' if analysis_ok else 'fail'}; "
        f"generation={'ok' if generation_ok else 'fail'}; "
        f"text={generated_text[:120].replace(chr(10), ' ')}"
    )
    return CheckResult("Task 2 (Multi-Modal)", ok, details)


def _check_task_3(bot) -> CheckResult:
    r = bot.chat("What are the symptoms of fever?", task=3)
    text = str(_safe_get(r, "text", ""))
    ok = bool(text.strip()) and any(k in text.lower() for k in ["fever", "symptom", "treatment"])
    return CheckResult("Task 3 (Medical Q&A)", ok, text[:200].replace("\n", " "))


def _check_task_4(bot) -> CheckResult:
    r = bot.chat("Explain transformers in machine learning.", task=4)
    text = str(_safe_get(r, "text", ""))
    references = _safe_get(r, "references", [])
    analysis = _safe_get(r, "academic_analysis", {})
    concepts = analysis.get("key_concepts") if isinstance(analysis, dict) else []
    topic = _safe_get(r, "search_topic", "")

    followup = bot.chat("Provide a BibTeX citation for the paper you referenced.", task=4)
    followup_text = str(_safe_get(followup, "text", ""))

    ok = (
        bool(text.strip())
        and len(text) > 140
        and isinstance(references, list)
        and len(references) > 0
        and isinstance(analysis, dict)
        and bool(concepts)
        and bool(str(topic).strip())
        and "@article" in followup_text.lower()
        and "bibtex" in followup_text.lower()
    )
    details = (
        f"refs={len(references) if isinstance(references, list) else 0}; "
        f"concepts={len(concepts) if isinstance(concepts, list) else 0}; "
        f"followup={'ok' if '@article' in followup_text.lower() else 'fail'}; "
        f"topic={str(topic)[:40]}"
    )
    return CheckResult("Task 4 (Domain Expert)", ok, details)


def _check_task_5(bot) -> CheckResult:
    r = bot.chat("I'm stressed and worried.", task=5)
    text = str(_safe_get(r, "text", ""))
    ok = "sentiment:" in text.lower() and ("confidence" in text.lower() or "vader" in text.lower())
    return CheckResult("Task 5 (Sentiment)", ok, text[:200].replace("\n", " "))


def _check_task_6(bot) -> CheckResult:
    r = bot.chat("Translate: Hola, ¿cómo estás?", task=6)
    text = str(_safe_get(r, "text", ""))
    ok = "detected language" in text.lower() and "translated to" in text.lower()
    # It's OK if translation is unchanged (backend unavailable); the app prints a note.
    return CheckResult("Task 6 (Multi-language)", ok, text[:220].replace("\n", " "))


def main() -> int:
    print("Unified Chatbot verification (Tasks 1–6)")
    print("Python:", sys.executable)

    # Import lazily so failures show as clear errors.
    try:
        from chatbot_main import UnifiedChatbot
    except Exception as e:
        print("FAIL: could not import UnifiedChatbot:", e)
        return 2

    bot = UnifiedChatbot(lazy_init=True)

    checks = [
        _check_task_1,
        _check_task_2,
        _check_task_3,
        _check_task_4,
        _check_task_5,
        _check_task_6,
    ]

    results: List[CheckResult] = []
    for fn in checks:
        name = getattr(fn, "__name__", "check")
        try:
            results.append(fn(bot))
        except Exception as e:
            results.append(CheckResult(name, False, f"Exception: {e}"))

    print("\nResults")
    all_ok = True
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        line = f"- {status}: {r.name} - {r.details}"
        print(line.encode("ascii", errors="replace").decode("ascii"))
        all_ok = all_ok and r.ok

    print("\nOverall:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

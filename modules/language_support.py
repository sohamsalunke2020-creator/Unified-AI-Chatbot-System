"""
Task 6: Multi-Language Support

Supports multiple languages with auto-detection, lightweight translation,
and cultural adaptation.

Designed to stay lightweight for Streamlit usage.
"""

import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional

from langdetect import detect, detect_langs, LangDetectException

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


# -------------------------------------------------------------------
# OFFLINE PHRASEBOOK
# -------------------------------------------------------------------

_PHRASEBOOK: Dict[tuple, Dict[str, str]] = {
    ("en", "es"): {
        "hello": "hola",
        "how are you": "cómo estás",
        "thank you": "gracias",
        "please": "por favor",
        "fever": "fiebre",
        "headache": "dolor de cabeza",
        "cough": "tos",
        "pain": "dolor",
        "how": "cómo",
        "are": "estás",
        "you": "tú",
    },
    ("es", "en"): {
        "hola": "hello",
        "cómo estás": "how are you",
        "como estas": "how are you",
        "gracias": "thank you",
        "por favor": "please",
        "fiebre": "fever",
        "dolor de cabeza": "headache",
        "tos": "cough",
        "dolor": "pain",
        "como": "how",
        "estas": "are you",
    },
    ("en", "fr"): {
        "hello": "bonjour",
        "thank you": "merci",
        "please": "s'il vous plaît",
        "fever": "fièvre",
        "headache": "mal de tête",
        "cough": "toux",
    },
    ("fr", "en"): {
        "bonjour": "hello",
        "merci": "thank you",
        "fièvre": "fever",
        "toux": "cough",
    },
    ("en", "hi"): {
        "hello": "namaste",
        "how are you": "aap kaise ho",
        "thank you": "dhanyavaad",
        "please": "kripya",
        "good morning": "shubh prabhaat",
        "goodbye": "alvida",
        "yes": "haan",
        "no": "nai",
    },
    ("hi", "en"): {
        "namaste": "hello",
        "kaise ho": "how are you",
        "aap kaise ho": "how are you",
        "kaise": "how",
        "ho": "are",
        "aap": "you",
        "dhanyavaad": "thank you",
        "kripya": "please",
        "shubh prabhaat": "good morning",
        "alvida": "goodbye",
        "haan": "yes",
        "nai": "no",
    },
    ("en", "ja"): {
        "hello": "こんにちは",
        "good morning": "おはよう",
        "how are you": "お元気ですか",
        "thank you": "ありがとう",
        "please": "お願いします",
        "goodbye": "さようなら",
        "yes": "はい",
        "no": "いいえ",
    },
    ("ja", "en"): {
        "こんにちは": "hello",
        "konnichiwa": "hello",
        "おはよう": "good morning",
        "お元気ですか": "how are you",
        "ogenki desu ka": "how are you",
        "genki desu ka": "how are you",
        "ありがとう": "thank you",
        "arigatou": "thank you",
        "お願いします": "please",
        "さようなら": "goodbye",
        "sayounara": "goodbye",
        "はい": "yes",
        "いいえ": "no",
    },
    ("en", "it"): {
        "hello": "ciao",
        "how are you": "come stai",
        "thank you": "grazie",
        "please": "per favore",
        "good morning": "buongiorno",
        "goodbye": "arrivederci",
        "yes": "sì",
        "no": "no",
    },
    ("it", "en"): {
        "ciao": "hello",
        "come stai": "how are you",
        "come stai?": "how are you",
        "grazie": "thank you",
        "per favore": "please",
        "buongiorno": "good morning",
        "arrivederci": "goodbye",
        "sì": "yes",
        "no": "no",
    },
}


# -------------------------------------------------------------------
# LANGUAGE PROCESSOR
# -------------------------------------------------------------------


class LanguageProcessor:

    def __init__(self, config):

        self.config = config

        # -------------------------------------------------
        # FIX: Handle both string and list configs
        # -------------------------------------------------

        langs = getattr(config, "SUPPORTED_LANGUAGES", "en")

        if isinstance(langs, str):
            self.supported_languages = [l.strip() for l in langs.split(",")]
        elif isinstance(langs, list):
            self.supported_languages = langs
        else:
            self.supported_languages = ["en"]

        self.default_language = getattr(config, "DEFAULT_LANGUAGE", "en")

        self.enable_translation = _bool_env("ENABLE_TRANSLATION", True)
        self.enable_online_translation = _bool_env("ENABLE_ONLINE_TRANSLATION", True)

        self.language_codes = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "sw": "Swahili",
            "ja": "Japanese",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
        }

        merged_languages: List[str] = []
        for code in list(self.supported_languages) + list(self.language_codes.keys()):
            normalized = self._normalize_language_code(code)
            if normalized and normalized not in merged_languages:
                merged_languages.append(normalized)
        self.supported_languages = merged_languages

        self.cultural_guidelines = self._load_cultural_guidelines()

        logger.info(f"LanguageProcessor initialized: {self.supported_languages}")

    # -------------------------------------------------------------------
    # CULTURAL GUIDELINES
    # -------------------------------------------------------------------

    def _load_cultural_guidelines(self):

        return {
            "en": {"greeting": "Hello", "closing": "Best regards"},
            "es": {"greeting": "Hola", "closing": "Saludos"},
            "fr": {"greeting": "Bonjour", "closing": "Cordialement"},
            "de": {"greeting": "Hallo", "closing": "Viele Grüße"},
            "sw": {"greeting": "Habari", "closing": "Kwa heri"},
            "ja": {"greeting": "こんにちは", "closing": "よろしくお願いします"},
            "zh": {"greeting": "你好", "closing": "谢谢"},
            "ar": {"greeting": "السلام عليكم", "closing": "مع التحية"},
            "hi": {"greeting": "नमस्ते", "closing": "धन्यवाद"},
            "it": {"greeting": "Ciao", "closing": "Arrivederci"},
        }

    # -------------------------------------------------------------------
    # TEXT NORMALIZATION
    # -------------------------------------------------------------------

    def normalize_text(self, text: str) -> str:

        if not text:
            return ""

        text = unicodedata.normalize("NFKC", str(text))
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _normalize_language_code(self, code: str) -> str:

        value = (code or "").strip().lower().replace("_", "-")
        if not value:
            return self.default_language

        aliases = {
            "zh-cn": "zh",
            "zh-tw": "zh",
            "zh-hans": "zh",
            "zh-hant": "zh",
            "pt-br": "pt",
            "pt-pt": "pt",
        }
        return aliases.get(value, value)

    # -------------------------------------------------------------------
    # LANGUAGE DETECTION
    # -------------------------------------------------------------------

    def detect_language(self, text: str) -> str:

        try:

            text = self.normalize_text(text)

            # Heuristic fallback for short queries and punctuation-rich language triggers
            lowered = (text or "").lower()
            if "¿" in lowered or "¡" in lowered or " qué " in lowered or " como " in lowered or " gracias " in lowered:
                return "es"
            if any(x in lowered for x in ["السلام", "مع التحية", "ما هو", "شكرا"]):
                return "ar"
            if any(x in lowered for x in ["你好", "谢谢", "什么", "上海"]):
                return "zh"
            if any(x in lowered for x in ["bonjour", "merci", "s'il vous plaît", "qu'est-ce"]):
                return "fr"
            # Hindi: use word boundaries to avoid false positives like "how" matching "ho"
            if any(x in lowered for x in [" namaste", "namaste ", " kaise ", " aap ", " dhanyavaad"]):
                return "hi"
            if any(x in lowered for x in ["konnichiwa", "ogenki", "arigatou", "ohisashiburi", "ですか", "です"]):
                return "ja"
            if any(x in lowered for x in [" ciao", "ciao ", " come ", " stai", " grazie", " prego"]):
                return "it"

            detected = self._normalize_language_code(detect(text))

            if detected in self.supported_languages or detected in self.language_codes:
                return detected

            langs = detect_langs(text)

            for lang in langs:
                normalized = self._normalize_language_code(lang.lang)
                if normalized in self.supported_languages or normalized in self.language_codes:
                    return normalized

            return self.default_language

        except LangDetectException:

            return self.default_language

    def resolve_language_code(self, value: str) -> Optional[str]:

        normalized = self._normalize_language_code(value)
        if normalized in self.language_codes or normalized in self.supported_languages:
            return normalized

        compact = re.sub(r"\s+", " ", str(value or "").strip().lower())
        for code, name in self.language_codes.items():
            if compact == name.lower():
                return code

        return None

    # -------------------------------------------------------------------
    # TRANSLATION
    # -------------------------------------------------------------------

    def translate_to_default(self, text: str, source_language: str) -> str:

        source_language = self._normalize_language_code(source_language)

        if source_language == self.default_language:
            return text

        return self._translate(text, source_language, self.default_language)

    def translate_from_default(self, text: str, target_language: str) -> str:

        target_language = self._normalize_language_code(target_language)

        if target_language == self.default_language:
            return text

        return self._translate(text, self.default_language, target_language)

    # -------------------------------------------------------------------

    def _translate(self, text: str, source_lang: str, target_lang: str) -> str:

        text = self.normalize_text(text)

        if not self.enable_translation:
            return text

        source_lang = self._normalize_language_code(source_lang)
        target_lang = self._normalize_language_code(target_lang)

        if source_lang == target_lang:
            return text

        # Prefer full-sentence online translation when enabled.
        if self.enable_online_translation:
            result = self._translate_with_deep_translator(text, source_lang, target_lang)
            if result and result.strip() and result.strip() != text.strip():
                return result

        # Fallback: phrasebook word-level substitution.
        return self._translate_with_phrasebook(text, source_lang, target_lang)

    # -------------------------------------------------------------------

    def _translate_with_phrasebook(self, text: str, source_lang: str, target_lang: str):

        mapping = _PHRASEBOOK.get((source_lang, target_lang))

        if not mapping:
            return text

        result = text.lower()  # Work with lowercase for matching

        # Sort by length descending to match longer phrases first
        for src, tgt in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
            src_lower = src.lower()
            if src_lower in result:
                result = result.replace(src_lower, tgt)

        return result

    # -------------------------------------------------------------------

    def _translate_with_deep_translator(self, text, source_lang, target_lang):

        try:

            from deep_translator import GoogleTranslator

            src = source_lang if source_lang else "auto"

            # deep-translator expects some language variants explicitly.
            if src == "zh":
                src = "zh-CN"
            if target_lang == "zh":
                target_lang = "zh-CN"

            translated = GoogleTranslator(
                source=src,
                target=target_lang
            ).translate(text)

            return translated or text

        except Exception as e:

            logger.warning(f"Online translation failed: {e}")

            return text

    # -------------------------------------------------------------------
    # CULTURAL ADAPTATION
    # -------------------------------------------------------------------

    def apply_cultural_adaptation(self, text: str, language: str):

        guide = self.cultural_guidelines.get(language)

        if not guide:
            return text

        greeting = guide.get("greeting")
        closing = guide.get("closing")

        if greeting:
            text = f"{greeting}! {text}"

        if closing:
            text = f"{text}\n\n{closing}"

        return text

    # -------------------------------------------------------------------
    # RESPONSE FORMAT
    # -------------------------------------------------------------------

    def format_multilingual_response(self, content: str, language: str, include_translation=False):

        response = {
            "language": language,
            "content": content,
            "language_name": self.language_codes.get(language, "Unknown"),
        }

        if include_translation:

            translated = self.translate_from_default(content, language)

            response["translations"] = {
                "en": content,
                language: translated
            }

        return response

    # -------------------------------------------------------------------

    def detect_language_with_confidence(self, text: str):

        try:

            langs = detect_langs(text)

            return [(self._normalize_language_code(l.lang), l.prob) for l in langs]

        except Exception:

            return [(self.default_language, 1.0)]

    # -------------------------------------------------------------------

    def analyze_language_patterns(self, texts: List[str]):

        counts = {}

        for t in texts:

            lang = self.detect_language(t)

            counts[lang] = counts.get(lang, 0) + 1

        return {
            "distribution": counts,
            "total": len(texts),
            "most_common": max(counts, key=counts.get) if counts else None,
        }

    def detect_script(self, text: str) -> str:
        for ch in text or "":
            code = ord(ch)
            if 0x0600 <= code <= 0x06FF:
                return "arabic"
            if 0x4E00 <= code <= 0x9FFF:
                return "han"
            if ch.isalpha():
                return "latin"
        return "unknown"

    def is_rtl_language(self, language: str) -> bool:
        return self._normalize_language_code(language) in {"ar", "he", "fa", "ur"}

    def get_cultural_guidelines(self, language: str) -> Dict[str, str]:
        lang = self._normalize_language_code(language)
        base = self.cultural_guidelines.get(lang, {})
        return {
            "formality": "neutral",
            "tone": "professional",
            "greeting": base.get("greeting", ""),
            "closing": base.get("closing", ""),
        }
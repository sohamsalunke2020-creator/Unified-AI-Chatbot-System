"""
Unified Chatbot System
Main engine combining all 6 tasks into a single coherent system
"""

import os
import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import json

from utils.config import load_config
from utils.logger import setup_logger

# Setup logging
logger = setup_logger(__name__)


class UnifiedChatbot:
    """
    Main chatbot engine that integrates all 6 tasks:
    1. Dynamic knowledge base expansion
    2. Multi-modal capabilities (text + image)
    3. Medical Q&A
    4. Domain expert (arXiv papers)
    5. Sentiment analysis
    6. Multi-language support
    """

    def __init__(self, config_path: str = ".env", lazy_init: bool = False):
        """Initialize the unified chatbot system.

        If lazy_init=True, heavy modules are initialized on-demand. This keeps
        Streamlit UI startup fast, and loads models/datasets when first used.
        """
        self.config = load_config(config_path)
        self._lazy_init = bool(lazy_init)
        logger.info("Initializing Unified Chatbot System")

        # Modules (may be initialized lazily)
        self.vector_db = None
        self.multimodal = None
        self.medical_qa = None
        self.domain_expert = None
        self.sentiment = None
        self.language = None

        if not self._lazy_init:
            self._init_all_modules()

        # Conversation history
        self.conversation_history = []
        self.user_profile = {}
        # Per-user last academic search topic (for Task 4 follow-up commands)
        self._last_academic_topic: Dict[str, str] = {}
        self._last_academic_context: Dict[str, List[Dict]] = {}
        self._general_question_pool: Optional[List[str]] = None
        self._medical_question_pool: Optional[List[str]] = None

        logger.info(
            "Unified Chatbot System initialized successfully"
            + (" (lazy init)" if self._lazy_init else "")
        )

    def _init_all_modules(self) -> None:
        self._ensure_vector_db()
        self._ensure_multimodal()
        self._ensure_medical_qa()
        self._ensure_domain_expert()
        self._ensure_sentiment()
        self._ensure_language()

    def _ensure_vector_db(self):
        if self.vector_db is None:
            from modules.vector_db import VectorDatabaseManager

            self.vector_db = VectorDatabaseManager(self.config)
        return self.vector_db

    def _load_persisted_vector_stats(self) -> Optional[Dict]:
        """Read lightweight vector DB stats from disk without forcing module init."""

        db_path = getattr(self.config, "VECTOR_DB_PATH", "")
        if not db_path:
            return None

        metadata_path = os.path.join(db_path, "metadata.json")
        if not os.path.exists(metadata_path):
            return None

        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except Exception:
            return None

        if not isinstance(metadata, list):
            return None

        last_update = "never"
        if metadata:
            latest_entry = metadata[-1] if isinstance(metadata[-1], dict) else {}
            last_update = str(latest_entry.get("timestamp") or "never")

        return {
            "documents": len(metadata),
            "index_size": len(metadata),
            "last_update": last_update,
            "update_status": None,
        }

    def _ensure_multimodal(self):
        if self.multimodal is None:
            from modules.multimodal import MultiModalProcessor

            self.multimodal = MultiModalProcessor(self.config)
        return self.multimodal

    def _ensure_medical_qa(self):
        if self.medical_qa is None:
            from modules.medical_qa import MedicalQASystem

            self.medical_qa = MedicalQASystem(self.config)
        return self.medical_qa

    def _ensure_domain_expert(self):
        if self.domain_expert is None:
            from modules.domain_expert import DomainExpertSystem

            self.domain_expert = DomainExpertSystem(self.config)
        return self.domain_expert

    def _ensure_sentiment(self):
        if self.sentiment is None:
            from modules.sentiment_analysis import SentimentAnalyzer

            self.sentiment = SentimentAnalyzer(self.config)
        return self.sentiment

    def _ensure_language(self):
        if self.language is None:
            from modules.language_support import LanguageProcessor

            self.language = LanguageProcessor(self.config)
        return self.language

    def _release_nonessential_modules(self, keep: Optional[set] = None) -> None:
        """Best-effort memory relief for long-running Streamlit sessions.

        Some tasks load large ML models (sentence-transformers, transformers, etc.).
        If the user later runs Task 6 (translation), memory pressure can cause the
        Streamlit process to exit abruptly, which shows up in the browser as
        "Connection failed with status 0".

        This method drops references to non-essential modules so Python can GC
        them, improving stability on lower-memory machines.
        """

        keep = keep or set()
        for attr in ("vector_db", "multimodal", "medical_qa", "domain_expert", "sentiment", "language"):
            if attr in keep:
                continue
            try:
                setattr(self, attr, None)
            except Exception:
                pass

        try:
            import gc

            gc.collect()
        except Exception:
            pass

        # If torch is present, try to release cached allocator memory (no-op on CPU).
        try:
            import sys

            torch = sys.modules.get("torch")
            if torch is not None and hasattr(torch, "cuda") and callable(getattr(torch.cuda, "empty_cache", None)):
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _is_medical_query_light(self, text: str) -> bool:
        text_l = (text or "").lower()
        keywords = [
            "symptom",
            "disease",
            "treatment",
            "medicine",
            "doctor",
            "health",
            "pain",
            "diagnosis",
            "medical",
            "illness",
            "cure",
            "drug",
            "vaccine",
            "therapy",
            "diabetes",
            "fever",
            "hypertension",
            "pneumonia",
            "asthma",
            "anemia",
        ]
        return any(k in text_l for k in keywords)

    def _is_academic_query_light(self, text: str) -> bool:
        text_l = (text or "").lower()
        keywords = [
            "paper",
            "research",
            "arxiv",
            "publication",
            "conference",
            "journal",
            "methodology",
            "literature review",
            "citation",
            "bibtex",
            "algorithm",
            "neural network",
            "machine learning",
            "deep learning",
        ]
        return any(k in text_l for k in keywords)

    def _maybe_handle_language_switch(self, user_input: str, user_id: str) -> Optional[Dict]:
        """Detect commands like 'switch to Spanish' and persist a preferred output language."""
        text = (user_input or "").strip()
        if not text:
            return None

        text_l = text.lower()
        patterns = [
            r"\b(switch|change)\s+(the\s+)?language\s+to\s+([a-zA-Z\- ]+)\b",
            r"\b(speak|reply|respond)\s+in\s+([a-zA-Z\- ]+)\b",
        ]

        match_lang = None
        for pat in patterns:
            m = re.search(pat, text_l)
            if m:
                match_lang = m.group(m.lastindex).strip()
                break

        if not match_lang:
            return None

        # Map language name to code.
        language = self._ensure_language()
        name_to_code = {
            v.lower(): k for k, v in getattr(language, "language_codes", {}).items()
        }
        # Also allow direct ISO code.
        requested = match_lang.replace("_", "-").strip()
        requested_code = name_to_code.get(requested) or name_to_code.get(requested.replace("-", " "))
        if requested in getattr(language, "supported_languages", []):
            requested_code = requested

        if not requested_code or requested_code not in getattr(language, "supported_languages", []):
            return {
                "text": f"I can’t switch to '{match_lang}'. Supported languages: {', '.join(language.supported_languages)}",
                "domain": "language",
                "sentiment_adapted": "NEUTRAL",
                "confidence": 0.0,
                "include_image": False,
                "context_used": 0,
                "language": self.config.DEFAULT_LANGUAGE,
                "suggestions": [
                    "Switch language to Spanish",
                    "Switch language to French",
                ],
            }

        # Persist preference
        if user_id not in self.user_profile:
            self.user_profile[user_id] = {}
        self.user_profile[user_id]["preferred_language"] = requested_code

        ack = f"Okay — I’ll respond in {language.language_codes.get(requested_code, requested_code)} from now on."
        # Acknowledge in the requested language.
        try:
            if not getattr(language, "enable_translation", True):
                localized = ""
                try:
                    localized = language.localize_phrase("switch_ack", requested_code)
                except Exception:
                    localized = ""
                ack = localized or ack
                ack = language.apply_cultural_adaptation(ack, requested_code)
            else:
                ack = language.translate_from_default(ack, requested_code)
                ack = language.apply_cultural_adaptation(ack, requested_code)
        except Exception:
            pass

        return {
            "text": ack,
            "domain": "language",
            "sentiment_adapted": "NEUTRAL",
            "confidence": 0.0,
            "include_image": False,
            "context_used": 0,
            "language": requested_code,
            "suggestions": [],
        }

    def _extract_requested_output_language(self, user_input: str) -> Tuple[str, Optional[str]]:
        """Extract requests like 'Answer in French' and strip them from the prompt."""

        text = (user_input or "").strip()
        if not text:
            return text, None

        language = self._ensure_language()
        patterns = [
            r"^(?P<content>.+?)\s*(?:[.?!,;:-]\s*)?(?:answer|respond|reply|write|give me(?: the)? response|return it)\s+(?:it\s+)?(?:back\s+)?(?:in|into)\s+(?P<lang>[A-Za-z][A-Za-z\- ]{1,30})[.?!]?\s*$",
            r"^(?P<content>.+?)\s+(?:in|into)\s+(?P<lang>[A-Za-z][A-Za-z\- ]{1,30})[.?!]?\s*$",
        ]

        for pattern in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            code = language.resolve_language_code(match.group("lang"))
            if code:
                cleaned = match.group("content").strip()
                return cleaned or text, code

        return text, None

    def _validate_input(self, user_input: str) -> Optional[str]:
        """
        Validate if user input is a proper query. Returns error message if invalid, None if OK.
        """
        text = user_input.strip()
        
        # Too short
        if len(text) < 2:
            return ("It looks like your message is too short. "
                    "Could you please ask a complete question? For example:\n"
                    "  \u2022 What is diabetes?\n"
                    "  \u2022 What are the symptoms of asthma?\n"
                    "  \u2022 How to prevent malaria?")
        
        # Too long (pasted tables, logs, etc.)
        if len(text) > 1000:
            return ("It seems like you've pasted a large block of text rather than asking a question.\n\n"
                    "Could you please rephrase your query as a clear question? For example:\n"
                    "  \u2022 What is diabetes?\n"
                    "  \u2022 How to prevent Typhoid Fever?\n"
                    "  \u2022 What are the treatments for pneumonia?")
        
        # Detect pasted output / tables (contains multiple domain/sentiment markers)
        table_markers = ["Domain:", "Sentiment:", "Confidence:", "CSV \u2014", "Local KB"]
        marker_count = sum(1 for m in table_markers if m in text)
        if marker_count >= 2:
            return ("It looks like you've pasted some output or a table instead of asking a question.\n\n"
                    "Please try asking a specific question, such as:\n"
                    "  \u2022 What is diabetes?\n"
                    "  \u2022 What are the symptoms of pneumonia?\n"
                    "  \u2022 How to prevent Typhoid Fever?")
        
        # Mostly non-letter characters (often pasted IDs, noise, etc.).
        # Use Unicode-aware letter detection so non-Latin languages (e.g., Arabic/Chinese)
        # are not incorrectly rejected.
        letter_chars = sum(1 for ch in text if ch.isalpha())
        if len(text) > 10 and letter_chars / len(text) < 0.3:
            return ("I couldn't understand your input. It doesn't seem to be a valid question.\n\n"
                    "Please try asking in natural language, for example:\n"
                    "  \u2022 What causes anemia?\n"
                    "  \u2022 How to diagnose hepatitis?")
        
        return None

    def _normalize_question_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower()).rstrip(" ?.!")

    def _extract_query_topic_tokens(self, text: str) -> List[str]:
        stop_words = {
            "a", "an", "and", "are", "about", "can", "cause", "causes", "define",
            "describe", "difference", "do", "does", "example", "examples", "explain", "for",
            "from", "give", "how", "i", "in", "is", "it", "list", "me", "of", "on", "or",
            "please", "show", "simple", "tell", "that", "the", "this", "to", "what", "when",
            "where", "which", "who", "why", "with", "used", "uses",
        }
        tokens = [token for token in re.findall(r"[a-z0-9+#.-]+", (text or "").lower()) if len(token) > 2]
        return [token for token in tokens if token not in stop_words]

    def _load_general_question_pool(self) -> List[str]:
        if self._general_question_pool is not None:
            return self._general_question_pool

        pool: List[str] = []
        source_file = getattr(self.config, "KNOWLEDGE_SOURCE_FILE", "")
        try:
            with open(source_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            self._general_question_pool = []
            return self._general_question_pool

        if isinstance(payload, dict):
            payload = payload.get("documents", [])

        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            first_sentence = re.split(r"(?<=[.!?])\s+", content, maxsplit=1)[0].strip()
            if not first_sentence:
                continue

            question = self._question_from_knowledge_sentence(first_sentence)
            if question:
                pool.append(question)

        self._general_question_pool = self._dedupe_questions(pool)
        return self._general_question_pool

    def _question_from_knowledge_sentence(self, sentence: str) -> Optional[str]:
        cleaned = re.sub(r"\s+", " ", sentence).strip().rstrip(".")
        if not cleaned:
            return None

        patterns = [
            (r"^(.+?)\s+stands for\b", "What does {subject} stand for?"),
            (r"^(.+?)\s+(stores|store|distributes|convert|converts|transforms|verifies|lets|organizes|packages|manages|focuses|works|work)\b", "Explain {subject}."),
            (r"^(.+?)\s+is\b", "What is {subject}?"),
            (r"^(.+?)\s+are\b", "What are {subject}?"),
            (r"^(.+?)\s+means\b", "What does {subject} mean?"),
        ]
        for pattern, template in patterns:
            match = re.match(pattern, cleaned, flags=re.IGNORECASE)
            if not match:
                continue
            subject = self._clean_question_subject(match.group(1))
            if len(subject) < 2:
                continue
            return template.format(subject=subject)

        if " while " in cleaned.lower():
            subject = self._clean_question_subject(cleaned.split(" while ", 1)[0])
            if subject:
                return f"Explain {subject}."
        return None

    def _clean_question_subject(self, subject: str) -> str:
        value = re.sub(r"\s+", " ", str(subject or "")).strip(" ,:-")
        if ", or " in value:
            value = value.split(",", 1)[0].strip()
        value = re.sub(r"^(a|an|the)\s+", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s{2,}", " ", value)
        return value.strip(" ,:-")

    def _load_medical_question_pool(self) -> List[str]:
        if self._medical_question_pool is not None:
            return self._medical_question_pool

        if self.medical_qa is None:
            self._ensure_medical_qa()

        csv_questions = getattr(self.medical_qa, "medquad_qa", []) if self.medical_qa is not None else []
        pool = [
            str(item.get("question") or "").strip()
            for item in csv_questions
            if isinstance(item, dict) and str(item.get("question") or "").strip()
        ]
        self._medical_question_pool = self._dedupe_questions(pool)
        return self._medical_question_pool

    def _dedupe_questions(self, questions: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for question in questions:
            normalized = self._normalize_question_text(question)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(str(question).strip())
        return deduped

    def _rotate_suggestions(
        self,
        user_id: str,
        domain: str,
        candidates: List[str],
        current_question: str,
        limit: int = 4,
    ) -> List[str]:
        profile = self.user_profile.setdefault(user_id, {})
        suggestion_history = profile.setdefault("suggestion_history", {})
        history = suggestion_history.setdefault(domain, [])

        asked = {
            self._normalize_question_text(conv.get("user_input", ""))
            for conv in self.conversation_history
            if conv.get("user_id") == user_id and conv.get("user_input")
        }
        current_normalized = self._normalize_question_text(current_question)
        if current_normalized:
            asked.add(current_normalized)

        normalized_history = {self._normalize_question_text(item) for item in history}

        fresh: List[str] = []
        for candidate in self._dedupe_questions(candidates):
            normalized = self._normalize_question_text(candidate)
            if not normalized or normalized in asked or normalized in normalized_history:
                continue
            fresh.append(candidate)
            if len(fresh) >= limit:
                break

        if len(fresh) < limit:
            suggestion_history[domain] = []
            normalized_history = set()
            for candidate in self._dedupe_questions(candidates):
                normalized = self._normalize_question_text(candidate)
                if not normalized or normalized in asked or normalized in {self._normalize_question_text(item) for item in fresh}:
                    continue
                fresh.append(candidate)
                if len(fresh) >= limit:
                    break

        suggestion_history[domain].extend(fresh)
        if domain != "medical":
            suggestion_history[domain] = suggestion_history[domain][-120:]
        return fresh[:limit]

    def _generate_suggestions(self, user_input: str, domain: str, response_text: str, user_id: str = "default") -> List[str]:
        """
        Generate follow-up suggestions: a mix of related questions (same topic)
        and diverse questions from the CSV for exploration.
        """
        import random
        suggestions: List[str] = []
        query_lower = user_input.lower()
        topic_words = self._extract_query_topic_tokens(query_lower)
        general_pool = self._load_general_question_pool()
        csv_questions = getattr(self.medical_qa, "medquad_qa", []) if self.medical_qa is not None else []

        # Keep suggestions aligned with the detected domain so users can verify tasks cleanly.
        if domain == "academic":
            lead_topic = self._last_academic_topic.get(user_id, "") or user_input
            paper_context = self._last_academic_context.get(user_id) or []
            candidates = []
            for item in paper_context:
                if isinstance(item, dict):
                    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
                    title = str(metadata.get("title") or "").strip()
                    if title:
                        candidates.extend([
                            f"Summarize {title}",
                            f"What are the key contributions of {title}?",
                            f"Explain the methodology in {title}",
                            f"What are the results in {title}?",
                            f"Who are the authors of {title}?",
                            f"Provide a BibTeX for {title}",
                        ])
            if not candidates:
                candidates = [
                    f"Give a short summary of {lead_topic}.",
                    f"List key contributions of {lead_topic}.",
                    f"What are limitations and future work for {lead_topic}?",
                    f"Provide a BibTeX citation for {lead_topic}.",
                    f"Compare {lead_topic} with a related method.",
                    f"Explain {lead_topic} more simply.",
                    f"What are the main algorithms discussed in {lead_topic}?",
                    f"Who are the authors of {lead_topic} and their affiliations?",
                    f"What datasets were used in {lead_topic}?",
                    f"How does {lead_topic} compare to previous work?",
                    f"What are the experimental results in {lead_topic}?",
                    f"What is the methodology used in {lead_topic}?",
                    f"What are the implications of {lead_topic} for the field?",
                    f"Provide key references cited in {lead_topic}.",
                    f"What are the challenges addressed in {lead_topic}?",
                ]
            return self._rotate_suggestions(user_id, domain, candidates, user_input)

        if domain == "general":
            related = [
                question
                for question in general_pool
                if any(token in self._normalize_question_text(question) for token in topic_words)
            ]
            diverse = [question for question in general_pool if question not in related]
            broad_candidates = [
                "What is artificial intelligence?",
                "How does machine learning work?",
                "Explain the difference between supervised and unsupervised learning.",
                "What are neural networks?",
                "What is a transformer model?",
                "How does natural language processing (NLP) function?",
                "Explain reinforcement learning in simple terms.",
                "What are the main types of computer vision tasks?",
                "How does blockchain ensure security?",
                "What are smart contracts?",
                "Explain quantum computing in layman terms.",
                "What is edge computing?",
                "Describe cloud computing models (IaaS, PaaS, SaaS).",
                "How does containerization help deployment?",
                "What is Kubernetes?",
                "Explain cybersecurity basics and common threats.",
                "What is zero trust security?",
                "How does SSL/TLS work?",
                "What does API mean and how is it used?",
                "Explain REST vs GraphQL.",
                "What is Big Data?",
                "How are data lakes different from data warehouses?",
                "Describe ETL and ELT processes.",
                "What are the benefits of DevOps culture?",
                "Explain CI/CD pipelines.",
                "What is the Internet of Things (IoT)?",
                "Explain autonomous vehicles and their challenges.",
                "What is augmented reality (AR) vs virtual reality (VR)?",
                "Describe the human genome project in brief.",
                "What are vaccines and how do they work?",
                "Explain climate change causes and effects.",
                "What is renewable energy and what are types?",
                "Describe the water cycle and its importance.",
                "What are common practices for mental wellness?",
                "Explain the principle of supply and demand.",
                "What is inflation and why does it matter?",
                "Explain blockchain consensus algorithms (PoW, PoS).",
                "What is computational linguistics?",
                "Describe the basics of software testing.",
                "What is a microservice architecture?",
                "How does facial recognition work?",
                "Explain the role of data privacy regulations (GDPR, CCPA).",
                "What is the significance of 5G networks?",
                "Describe the basic principles of astrophysics.",
                "What is the theory of relativity?",
                "Explain cellular respiration in biology.",
                "What is an ecosystem and its components?",
                "Explain the human circulatory system.",
                "What does DNA stand for and what is its function?",
                "Describe the structure of the solar system.",
                "What are the stages of software development life cycle?",
                "How does pattern recognition work?",
                "Explain ethics in AI and fairness concerns.",
                "What is data visualization and why is it useful?",
                "Explain the concept of probability and statistics.",
                "What is a citation and how to format one?",
                "Describe agile methodology and Scrum framework.",
                "What are the advantages of green buildings?",
                "Explain nanotechnology and its uses.",
                "What is genetic engineering?",
                "Describe the basic principles of pharmacology.",
                "What is mindfulness and how to practice it?",
                "Explain the role of mitochondria in cells.",
                "What is noise pollution and how does it affect health?",
                "Describe renewable water resource management.",
            ]
            candidates = list(dict.fromkeys(related + diverse + broad_candidates + [
                "Explain that more simply.",
                "Give an example.",
                "List key points.",
                "Compare two related concepts.",
                "What are the latest research trends in this area?",
                "How would you implement this in a project?",
                "What is a practical application of this idea?",
                "What are common misconceptions?"] ))
            return self._rotate_suggestions(user_id, domain, candidates, user_input)

        if domain == "greeting":
            candidates = general_pool + [
                "What can you do?",
                "Ask a medical question.",
                "Ask a research/arXiv question.",
                "Ask a general knowledge question.",
            ]
            return self._rotate_suggestions(user_id, domain, candidates, user_input)
        
        if domain == "multimodal":
            candidates = [
                "Generate an image of a futuristic city skyline.",
                "Generate an image of a robot reading a book.",
                "Generate an image of a medical infographic.",
                "Generate an image of a forest at sunrise.",
                "Generate an image of a cat playing with a ball.",
                "Generate an image of a spaceship in space.",
                "Generate an image of a underwater scene with fish.",
                "Generate an image of a mountain landscape.",
                "Generate an image of a historical castle.",
                "Generate an image of a modern office building.",
                "Upload an image and ask: What do you see?",
                "Upload an image and ask: What objects are visible?",
                "Upload an image and ask: Summarize the image in one sentence.",
                "Upload an image and ask: Describe the colors in the image.",
                "Upload an image and ask: What emotions does this image evoke?",
                "Upload an image and ask: Is there any text in the image?",
                "Upload an image and ask: What is the main subject?",
                "Upload an image and ask: How many people are in the image?",
                "Upload an image and ask: What time of day does this look like?",
                "Upload an image and ask: What weather is shown?",
            ]
            return self._rotate_suggestions(user_id, domain, candidates, user_input)

        if domain == "sentiment":
            candidates = [
                "I am feeling very happy today!",
                "This situation makes me really sad.",
                "I'm excited about the upcoming event.",
                "That news disappointed me a lot.",
                "I'm grateful for my friends and family.",
                "This is the worst day ever.",
                "I'm optimistic about the future.",
                "That comment made me angry.",
                "I'm proud of my achievements.",
                "This food tastes amazing!",
                "I'm worried about the exam.",
                "That movie was fantastic.",
                "I'm frustrated with this problem.",
                "I'm in love with this place.",
                "That idea scares me.",
                "I'm content with my life right now.",
                "This gift surprised me pleasantly.",
                "I'm bored with this routine.",
                "That performance was outstanding.",
                "I'm anxious about the meeting.",
                "This book is incredibly inspiring.",
                "I'm jealous of their success.",
                "That joke made me laugh so hard.",
                "I'm hopeful for a better tomorrow.",
                "This situation confuses me.",
                "I'm enthusiastic about learning new things.",
                "That mistake embarrassed me.",
                "I'm relaxed after the vacation.",
                "This achievement motivates me.",
                "I'm indifferent to that topic.",
                "I'm nervous about starting a new job.",
                "I am excited about meeting my friends.",
                "I'm overwhelmed with all this work.",
                "I just received fantastic news.",
                "I'm disappointed in myself.",
                "I feel calm and peaceful.",
                "I'm curious to learn more.",
                "I'm frustrated by how slow progress is.",
                "I feel grateful for how far I have come.",
                "I'm concerned about upcoming changes.",
                "I'm motivated to exercise today.",
                "I feel lonely and isolated.",
                "I'm proud of finishing my project.",
                "I'm stressed about the deadline.",
                "I'm feeling relaxed after meditation.",
                "I'm hopeful for the days ahead.",
                "I feel discouraged and tired.",
                "I am enthusiastic for the weekend.",
                "I'm afraid of failing the exam.",
                "I feel happy after talking with family.",
                "I'm disappointed with the outcome.",
                "I feel inspired by this artwork.",
                "That experience made me humbled.",
                "I am thankful for your help.",
                "I feel annoyed by frequent interruptions.",
                "I am forgiving and patient.",
                "I feel overjoyed with the celebration.",
                "I am uncertain about what to do next.",
            ]
            return self._rotate_suggestions(user_id, domain, candidates, user_input)

        if domain == "language":
            candidates = [
                "Hello, how are you?",
                "What is your name?",
                "Thank you very much.",
                "I love programming.",
                "Where is the library?",
                "How much does this cost?",
                "I need help with this.",
                "What time is it?",
                "Can you speak English?",
                "I don't understand.",
                "Translate: Hola, ¿cómo estás?",
                "Translate: Bonjour, comment allez-vous?",
                "Translate: Guten Tag, wie geht es Ihnen?",
                "Translate: Ciao, come stai?",
                "Translate: Olá, como você está?",
                "Translate: Namaste, kaise ho?",
                "Translate: Konnichiwa, ogenki desu ka?",
                "Translate: Annyeonghaseyo, eotteoke jinaeseyo?",
                "Translate: Ni hao, ni zai zuo shenme?",
                "Translate: Sawasdee, sabai dee mai?",
                "Switch language to Spanish.",
                "Switch language to French.",
                "Switch language to German.",
                "Switch language to Italian.",
                "Switch language to Portuguese.",
                "Switch language to Hindi.",
                "Switch language to Japanese.",
                "Switch language to Korean.",
                "Switch language to Chinese.",
                "Switch language to Thai.",
                "Switch language to Russian.",
                "Switch language to Arabic.",
                "Switch language to Vietnamese.",
                "Switch language to Indonesian.",
                "Switch language to Malay.",
                "Switch language to Bengali.",
                "Switch language to Turkish.",
                "Switch language to Dutch.",
                "Switch language to Swedish.",
                "Switch language to Polish.",
                "Translate: Привет, как дела?",
                "Translate: مرحبا كيف حالك؟",
                "Translate: 你好，今天怎么样？",
                "Translate: こんにちは、お元気ですか？",
                "Translate: 안녕하세요, 잘 지내세요?",
                "Translate: Saya ingin belajar bahasa baru.",
                "Translate: Estou aprendendo novas línguas.",
                "Translate: ¿Cuál es tu comida favorita?",
                "Translate: Quel est votre passe-temps préféré?",
                "Translate: Wie sagt man das auf Deutsch?",
            ]
            return self._rotate_suggestions(user_id, domain, candidates, user_input)
        
        if domain == "medical" and csv_questions:
            # --- Extract topic words from user query ---
            stop_words = {"what", "is", "are", "the", "of", "for", "how", "to", "do",
                          "does", "can", "tell", "me", "about", "with", "a", "an", "in",
                          "and", "or", "who", "symptoms", "treatment", "treatments",
                          "causes", "cause", "prevent", "prevention", "risk", "diagnose",
                          "diagnosis", "exams", "tests", "outlook", "research", "clinical",
                          "trials", "done", "being", "used"}
            words = re.findall(r'[a-z]+', query_lower)
            topic_words = [w for w in words if w not in stop_words and len(w) > 2]
            
            # --- Find related CSV questions (same topic, different qtype) ---
            if topic_words:
                related = []
                for qa in csv_questions:
                    q = qa['question_lower']
                    # Check if all topic words appear in the CSV question
                    if all(tw in q for tw in topic_words):
                        # Don't suggest the same question that was just asked
                        if q.strip().rstrip('? ') != query_lower.strip().rstrip('? '):
                            related.append(qa['question'])
                if related:
                    random.shuffle(related)
                    suggestions.extend(related[:2])
            
            # --- Add diverse questions from other topics ---
            diverse_pool = []
            # Pick from different qtypes for variety
            seen_topics = set(topic_words)
            for qa in random.sample(csv_questions, min(500, len(csv_questions))):
                q = qa['question']
                q_lower = qa['question_lower']
                # Skip if it's about the same topic or too generic
                if any(tw in q_lower for tw in seen_topics):
                    continue
                if len(q) > 15 and q not in suggestions:
                    diverse_pool.append(q)
                if len(diverse_pool) >= 20:
                    break
            
            if diverse_pool:
                random.shuffle(diverse_pool)
                remaining = 4 - len(suggestions)
                suggestions.extend(diverse_pool[:remaining])
            return self._rotate_suggestions(user_id, domain, suggestions + self._load_medical_question_pool(), user_input)
        
        # For non-medical domains, do NOT sample MedQuAD questions; it confuses task verification.
        
        # Fallback if CSV is empty
        if not suggestions:
            suggestions = [
                "What is diabetes?",
                "What are the symptoms of asthma?",
                "How to prevent Typhoid Fever?",
                "What are the treatments for pneumonia?",
            ]
        return self._rotate_suggestions(user_id, domain, suggestions, user_input)

    def chat(
        self,
        user_input: str,
        user_id: str = "default",
        language: Optional[str] = None,
        include_images: bool = False,
        image_paths: List[str] = None,
        task: Optional[int] = None,
    ) -> Dict:
        """
        Chat interface for the unified chatbot system.
        
        This is the primary interface method for conversing with the chatbot.
        It wraps process_user_input with additional parameters for convenience.
        
        Args:
            user_input: User's text input
            user_id: User identifier for personalization (default: "default")
            language: Preferred language code (optional, will auto-detect if not provided)
            include_images: Whether input includes images
            image_paths: List of image file paths if include_images=True
            task: Force a specific task (1-6) to be executed
            
        Returns:
            Dictionary with response and metadata
        """
        # If language is specified, set user preference
        if language:
            if user_id not in self.user_profile:
                self.user_profile[user_id] = {}
            self.user_profile[user_id]["preferred_language"] = language
        
        return self.process_user_input(
            user_input=user_input,
            user_id=user_id,
            include_images=include_images,
            image_paths=image_paths,
            task=task,
        )

    def process_user_input(
        self,
        user_input: str,
        user_id: str = "default",
        include_images: bool = False,
        image_paths: List[str] = None,
        task: Optional[int] = None,
    ) -> Dict:
        """
        Process user input through all components and generate response

        Args:
            user_input: User's text input
            user_id: User identifier for personalization
            include_images: Whether input includes images
            image_paths: List of image file paths if include_images=True

        Returns:
            Dictionary with response and metadata
        """
        try:
            logger.info(f"Processing input from user: {user_id}")

            # Handle explicit language switching commands early.
            try:
                maybe_switch = self._maybe_handle_language_switch(user_input, user_id)
                if maybe_switch is not None:
                    return maybe_switch
            except Exception:
                pass

            # If a specific task is selected, run ONLY that task.
            if task in {1, 2, 3, 4, 5, 6}:
                return self._process_forced_task(
                    task_id=task,
                    user_input=user_input,
                    user_id=user_id,
                    include_images=include_images,
                    image_paths=image_paths,
                )

            # Step 0: Validate input
            validation_error = self._validate_input(user_input)
            if validation_error:
                return {
                    "text": validation_error,
                    "domain": "general",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.5,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": [
                        "What is diabetes?",
                        "What are the symptoms of asthma?",
                        "How to prevent malaria?"
                    ],
                }

            # Step 1: Detect language (light first; only load translation if needed)
            cleaned_input, requested_output_language = self._extract_requested_output_language(user_input)
            detected_language = self.config.DEFAULT_LANGUAGE
            translated_input = cleaned_input

            language = None
            try:
                language = self._ensure_language()
                detected_language = language.detect_language(cleaned_input)
            except Exception:
                detected_language = self.config.DEFAULT_LANGUAGE

            if detected_language and detected_language != self.config.DEFAULT_LANGUAGE:
                language = self._ensure_language()
                translated_input = language.translate_to_default(cleaned_input, detected_language)

            # Step 2: Analyze sentiment (auto mode uses sentiment-aware tone)
            sentiment_result = self._ensure_sentiment().analyze(translated_input, user_id)

            # Step 3: Process images if provided
            image_analysis = None
            if include_images and image_paths:
                image_analysis = self._ensure_multimodal().process_images(image_paths)

            # Step 4: Determine domain and retrieve relevant context
            domain, context = self._determine_domain_and_context(
                translated_input, image_analysis
            )

            # Step 5: Generate response based on domain
            response = self._generate_response(
                translated_input,
                domain,
                context,
                sentiment_result,
                image_analysis,
                detected_language,
                user_id,
            )

            # Step 6: Handle multi-modal response if needed
            if image_analysis or response.get("include_image"):
                response = self._ensure_multimodal().enhance_with_images(response)

            # Step 7: Translate response back to user's language (or preferred language) if needed
            preferred = None
            try:
                preferred = (self.user_profile.get(user_id) or {}).get("preferred_language")
            except Exception:
                preferred = None

            target_out = preferred or requested_output_language or detected_language or self.config.DEFAULT_LANGUAGE
            if target_out != self.config.DEFAULT_LANGUAGE:
                if language is None:
                    language = self._ensure_language()
                response["text"] = language.translate_from_default(response["text"], target_out)
                response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                response["language"] = target_out

            # Step 8: Update knowledge base
            self._update_knowledge_base(user_input, response, domain)

            # Store in conversation history
            self.conversation_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                    "user_input": cleaned_input,
                    "detected_language": detected_language,
                    "domain": domain,
                    "sentiment": sentiment_result,
                    "response": response,
                }
            )

            return response

        except Exception as e:
            logger.error(f"Error processing user input: {str(e)}")
            return {
                "text": "I apologize, but I encountered an error processing your request. Please try again.",
                "status": "error",
                "error": str(e),
            }

    def _is_greeting_or_casual(self, text: str) -> bool:
        """Check if the input is a greeting or casual conversation."""
        text_lower = text.lower().strip().rstrip('!?.,')
        greetings = [
            "hi", "hello", "hey", "hola", "howdy", "sup", "yo",
            "good morning", "good afternoon", "good evening", "good night",
            "whats up", "what's up", "wassup", "how are you",
            "thanks", "thank you", "thx", "ty",
            "bye", "goodbye", "see you", "ok", "okay",
            "nice", "cool", "great", "awesome",
        ]
        return text_lower in greetings or len(text_lower.split()) <= 2 and text_lower.split()[0] in [g.split()[0] for g in greetings]

    def _get_greeting_response(self, text: str) -> str:
        """Generate a friendly response for greetings and casual messages."""
        text_lower = text.lower().strip().rstrip('!?.,')
        
        if text_lower in ["thanks", "thank you", "thx", "ty"]:
            return ("You're welcome! I'm happy to help. \U0001f60a\n\n"
                    "Feel free to ask me anything else. I can help with:\n"
                    "  \u2022 Medical questions (symptoms, treatments, prevention)\n"
                    "  \u2022 Scientific research and academic topics\n"
                    "  \u2022 General knowledge questions")
        
        if text_lower in ["bye", "goodbye", "see you"]:
            return ("Goodbye! Take care! \U0001f44b\n\n"
                    "Feel free to come back anytime you have questions.")
        
        if text_lower in ["nice", "cool", "great", "awesome", "ok", "okay"]:
            return ("Glad to hear that! \U0001f60a Is there anything else I can help you with?\n\n"
                    "Here are some things you can ask me:\n"
                    "  \u2022 What is diabetes?\n"
                    "  \u2022 What are the symptoms of asthma?\n"
                    "  \u2022 How to prevent Typhoid Fever?")
        
        # Default greeting
        return ("Hello! \U0001f44b Welcome to the Unified AI Chatbot!\n\n"
                "I can help you with a wide range of topics:\n"
                "  \u2022 \U0001f3e5 Medical Q&A \u2014 Ask about diseases, symptoms, treatments, prevention\n"
                "  \u2022 \U0001f4da Academic Research \u2014 Scientific papers and concepts\n"
                "  \u2022 \U0001f310 General Knowledge \u2014 Any topic you're curious about\n"
                "  \u2022 \U0001f60a Sentiment-Aware \u2014 I adapt my tone to how you feel\n"
                "  \u2022 \U0001f30d Multilingual \u2014 I support multiple languages\n\n"
                "Try asking me something like:\n"
                "  \u2022 What is diabetes?\n"
                "  \u2022 What are the symptoms of pneumonia?\n"
                "  \u2022 How to prevent Typhoid Fever?")

    def _determine_domain_and_context(
        self, user_input: str, image_analysis: Optional[Dict] = None
    ) -> Tuple[str, List[Dict]]:
        """
        Determine which domain the query belongs to and retrieve context

        Returns:
            Tuple of (domain, context_list)
        """
        # Check if it's a greeting or casual message
        if self._is_greeting_or_casual(user_input):
            domain = "greeting"
            context = []
            return domain, context
        
        # Lazy-safe routing: use light heuristics first, then load only what we need.
        if self._is_medical_query_light(user_input):
            med = self._ensure_medical_qa()
            if med.is_medical_query(user_input):
                domain = "medical"
                context = med.retrieve_context(user_input)
            else:
                domain = "general"
                context = self._ensure_vector_db().retrieve(user_input, top_k=5)
        elif self._is_academic_query_light(user_input):
            de = self._ensure_domain_expert()
            if de.is_academic_query(user_input):
                domain = "academic"
                context = de.retrieve_context(user_input)
            else:
                domain = "general"
                context = self._ensure_vector_db().retrieve(user_input, top_k=5)
        else:
            domain = "general"
            context = self._ensure_vector_db().retrieve(user_input, top_k=5)

        return domain, context

    def _generate_response(
        self,
        user_input: str,
        domain: str,
        context: List[Dict],
        sentiment_result: Dict,
        image_analysis: Optional[Dict],
        target_language: str,
        user_id: str = "default",
    ) -> Dict:
        """Generate response based on domain"""
        response_text = ""
        include_image = False
        medical_entities = None
        answer_source = None
        matched_question = None
        academic_analysis = None
        search_topic = None

        if domain == "greeting":
            response_text = self._get_greeting_response(user_input)
        elif domain == "medical":
            medical = self._ensure_medical_qa()
            medical_entities = medical.recognize_medical_entities(user_input)
            answer_result = medical.generate_answer_result(user_input, context)
            response_text = str(answer_result.get("text", ""))
            answer_source = answer_result.get("source_label")
            matched_question = answer_result.get("matched_question")
        elif domain == "academic":
            domain_expert = self._ensure_domain_expert()
            search_topic = domain_expert.clean_search_query(user_input) or user_input
            academic_analysis = domain_expert.build_topic_analysis(search_topic, context)
            response_text = domain_expert.generate_explanation(
                user_input,
                context,
                topic=search_topic,
                analysis=academic_analysis,
            )
        else:
            response_text = self._ensure_multimodal().generate_text_response(user_input, context)

        # Adapt response tone based on sentiment
        response_text = self._adapt_response_to_sentiment(
            user_input=user_input,
            response=response_text,
            sentiment_result=sentiment_result,
        )

        # Add image generation if appropriate
        if image_analysis or self._should_generate_image(user_input):
            include_image = True

        # Generate follow-up suggestions
        suggestions = self._generate_suggestions(user_input, domain, response_text, user_id=user_id)
        references = self._build_references(domain, context)
        if domain == "medical" and answer_source == "MedQuAD" and matched_question:
            references = [
                {
                    "title": "Matched MedQuAD Question",
                    "question": matched_question,
                    "source": "MedQuAD",
                }
            ] + references

        return {
            "text": response_text,
            "domain": domain,
            "sentiment_adapted": sentiment_result["sentiment"],
            "confidence": sentiment_result.get("confidence", 0.0),
            "include_image": include_image,
            "context_used": len(context),
            "language": target_language,
            "suggestions": suggestions,
            "references": references,
            "medical_entities": medical_entities,
            "answer_source": answer_source,
            "matched_question": matched_question,
            "academic_analysis": academic_analysis,
            "search_topic": search_topic,
            "pipeline": self._build_pipeline_summary(
                domain=domain,
                translated=target_language != self.config.DEFAULT_LANGUAGE,
                include_images=bool(image_analysis),
                context_count=len(context),
            ),
        }

    def _build_pipeline_summary(
        self,
        domain: str,
        translated: bool,
        include_images: bool,
        context_count: int,
    ) -> List[str]:
        steps = ["input_validation", "language_detection", "sentiment_analysis"]
        if include_images:
            steps.append("image_analysis")
        steps.append(f"domain_routing:{domain}")
        if context_count > 0:
            steps.append(f"retrieval:{context_count}")
        steps.append("response_generation")
        if translated:
            steps.append("response_translation")
        return steps

    def _build_references(self, domain: str, context: Optional[List[Dict]]) -> List[Dict]:
        references: List[Dict] = []
        for rank, item in enumerate(context or [], start=1):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            content = str(item.get("content") or "").strip()
            ref = {
                "rank": rank,
                "score": round(float(item.get("score", 0.0)), 3),
                "source": metadata.get("source", domain),
            }

            if domain == "academic":
                ref.update(
                    {
                        "title": metadata.get("title") or metadata.get("id") or "Local paper",
                        "authors": metadata.get("authors", ""),
                        "categories": metadata.get("categories", ""),
                        "updated": metadata.get("update_date", ""),
                    }
                )
            elif domain == "medical":
                ref.update(
                    {
                        "question": metadata.get("question", metadata.get("condition", "Medical context")),
                        "snippet": content[:220],
                    }
                )
            else:
                ref.update(
                    {
                        "domain": metadata.get("domain", domain),
                        "timestamp": metadata.get("timestamp", ""),
                        "snippet": content[:220],
                    }
                )

            references.append(ref)

        return references

    def _adapt_response_to_sentiment(
        self,
        user_input: str,
        response: str,
        sentiment_result: Dict,
    ) -> str:
        """Adapt response tone based on user sentiment and safety signals."""

        # Tone adaptation: delegate to the sentiment module so it can use detected emotions.
        sentiment = self._ensure_sentiment()
        adapted = sentiment.adapt_response_tone(response or "", sentiment_result or {})

        # Safety: if crisis keywords appear, append a short support message.
        crisis = sentiment.detect_crisis_indicators(user_input or "", sentiment_result or {})
        if crisis.get("is_crisis") and crisis.get("support_message"):
            adapted = f"{adapted}\n\n{crisis['support_message']}"

        return adapted

    def _should_generate_image(self, user_input: str) -> bool:
        """Determine if response should include generated image"""
        keywords = ["show", "generate", "create", "visualize", "image", "picture"]
        return any(keyword in user_input.lower() for keyword in keywords)

    def _update_knowledge_base(self, user_input: str, response: Dict, domain: str):
        """
        Update vector database with new information.
        Only stores high-quality factual content, NOT raw conversation history.
        """
        try:
            # Skip storing conversation in vector DB to avoid polluting it
            # The vector DB should only contain curated knowledge, not chat logs
            logger.info(f"Skipping vector DB update for conversation ({domain} domain)")
        except Exception as e:
            logger.warning(f"Failed to update knowledge base: {str(e)}")

    def get_conversation_history(self, user_id: str = None) -> List[Dict]:
        """Retrieve conversation history"""
        if user_id:
            return [
                conv for conv in self.conversation_history if conv["user_id"] == user_id
            ]
        return self.conversation_history

    def clear_conversation_history(self, user_id: str = None):
        """Clear conversation history"""
        if user_id:
            self.conversation_history = [
                conv for conv in self.conversation_history if conv["user_id"] != user_id
            ]
        else:
            self.conversation_history = []

    def get_system_status(self) -> Dict:
        """Get current system status"""
        modules = {
            "multimodal": "active" if self.multimodal is not None else "not_loaded",
            "medical_qa": "active" if self.medical_qa is not None else "not_loaded",
            "domain_expert": "active" if self.domain_expert is not None else "not_loaded",
            "sentiment_analysis": "active" if self.sentiment is not None else "not_loaded",
            "language_support": "active" if self.language is not None else "not_loaded",
            "vector_db": "active" if self.vector_db is not None else "not_loaded",
        }

        vector_stats = None
        try:
            if self.vector_db is not None:
                vector_stats = self.vector_db.get_stats()
            else:
                vector_stats = self._load_persisted_vector_stats()
        except Exception:
            vector_stats = None

        supported_languages = None
        try:
            if self.language is not None:
                supported_languages = getattr(self.language, "supported_languages", None)
        except Exception:
            supported_languages = None

        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "vector_db": vector_stats,
            "kb_updates": (
                self.vector_db.get_update_status() if self.vector_db is not None else None
            ),
            "conversation_count": len(self.conversation_history),
            "supported_languages": supported_languages,
            "modules": modules,
        }

    def trigger_knowledge_base_refresh(self, source: str = "manual") -> Dict:
        vector_db = self._ensure_vector_db()
        return vector_db.trigger_update(source=source)

    def _process_forced_task(
        self,
        task_id: int,
        user_input: str,
        user_id: str,
        include_images: bool,
        image_paths: Optional[List[str]],
    ) -> Dict:
        """Run ONLY a single internship task (1-6) as selected in the UI."""

        raw_input = user_input or ""

        # --- Multilingual wrapper for forced tasks ---
        # Task 6 is the dedicated language task, so leave it untouched.
        cleaned_input, requested_output_language = self._extract_requested_output_language(raw_input)
        detected_language = self.config.DEFAULT_LANGUAGE
        processed_input = cleaned_input

        preferred = None
        try:
            preferred = (self.user_profile.get(user_id) or {}).get("preferred_language")
        except Exception:
            preferred = None

        # For tasks other than Task 6, we try to translate the user's input to the
        # default language for downstream models, then translate the output back.
        if task_id != 6:
            try:
                language = self._ensure_language()
                detected_language = language.detect_language(cleaned_input) if cleaned_input.strip() else self.config.DEFAULT_LANGUAGE
            except Exception:
                detected_language = self.config.DEFAULT_LANGUAGE

            if detected_language and detected_language != self.config.DEFAULT_LANGUAGE:
                try:
                    language = self._ensure_language()
                    detected_language = language.detect_language(cleaned_input)
                    processed_input = language.translate_to_default(cleaned_input, detected_language)
                except Exception:
                    processed_input = cleaned_input

        target_out = preferred or requested_output_language or detected_language or self.config.DEFAULT_LANGUAGE

        validation_error = self._validate_input(raw_input)
        # Task 2 (images) and Task 6 (language detection/translation) must accept
        # non-standard text and non-Latin scripts.
        if validation_error and task_id not in {2, 6}:
            return {
                "text": validation_error,
                "domain": "general",
                "sentiment_adapted": "NEUTRAL",
                "confidence": 0.5,
                "include_image": False,
                "context_used": 0,
                "language": self.config.DEFAULT_LANGUAGE,
                "suggestions": [],
            }

        # Task 2 is image-first; allow empty/short text.
        if task_id == 2:
            mm = self._ensure_multimodal()
            prompt = (processed_input or raw_input or "").strip()

            if mm.is_image_generation_request(prompt):
                generated = mm.text_to_image(prompt)
                if generated:
                    response = {
                        "text": f"Generated image: {generated.get('summary') or generated.get('caption') or prompt}",
                        "domain": "multimodal",
                        "sentiment_adapted": "NEUTRAL",
                        "confidence": 0.85,
                        "include_image": True,
                        "context_used": 0,
                        "language": self.config.DEFAULT_LANGUAGE,
                        "generated_image_bytes": generated.get("image_bytes"),
                        "generated_image_name": generated.get("caption") or "Generated image",
                        "generated_image_path": generated.get("image_path"),
                        "generated_image_mime_type": generated.get("mime_type") or "image/png",
                        "suggestions": self._generate_suggestions(processed_input, "multimodal", f"Generated image: {generated.get('summary') or generated.get('caption') or prompt}", user_id=user_id),
                    }
                    if target_out != self.config.DEFAULT_LANGUAGE:
                        try:
                            language = self._ensure_language()
                            response["text"] = language.translate_from_default(response["text"], target_out)
                            response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                            response["language"] = target_out
                        except Exception:
                            response["language"] = target_out
                    return response

                return {
                    "text": "I couldn't generate an image for that prompt with the local renderer.",
                    "domain": "multimodal",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.0,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": self._generate_suggestions(processed_input, "multimodal", "I couldn't generate an image for that prompt with the local renderer.", user_id=user_id),
                }

            if not (include_images and image_paths):
                prompt_lower = prompt.lower()
                image_words = [
                    "image",
                    "photo",
                    "picture",
                    "screenshot",
                    "in the image",
                    "in this image",
                    "what do you see",
                    "what is in",
                    "objects",
                ]
                looks_image_related = any(w in prompt_lower for w in image_words)

                # If the user typed a normal text question while Task 2 is selected,
                # guide them to switch tasks instead of repeating upload instructions.
                if prompt_lower and not looks_image_related:
                    return {
                        "text": "Task 2 only answers questions about an uploaded image. Upload an image first, or switch to Task 1 for normal text questions.",
                        "domain": "multimodal",
                        "sentiment_adapted": "NEUTRAL",
                        "confidence": 0.0,
                        "include_image": False,
                        "context_used": 0,
                        "language": self.config.DEFAULT_LANGUAGE,
                        "suggestions": [
                            "Upload an image and ask: What is in the image?",
                            "Switch to Task 1 for text-only questions.",
                        ],
                    }
                return {
                    "text": "Task 2 (Multi‑Modal): Upload an image first, then ask questions about that uploaded image.",
                    "domain": "multimodal",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.0,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": self._generate_suggestions(processed_input, "multimodal", "Task 2 (Multi‑Modal): Upload an image first, then ask questions about that uploaded image.", user_id=user_id),
                }

            image_analysis = mm.analyze_images_with_prompt(image_paths, prompt)
            analyses = image_analysis.get("analysis", []) if isinstance(image_analysis, dict) else []
            answers = image_analysis.get("answers", []) if isinstance(image_analysis, dict) else []

            descriptions: List[str] = []
            for a in analyses:
                if isinstance(a, dict) and a.get("description"):
                    descriptions.append(str(a.get("description")))

            answer_texts: List[str] = []
            confidences: List[float] = []
            answer_objects: List[str] = []
            for ans in answers:
                if isinstance(ans, dict):
                    t = ans.get("answer")
                    if isinstance(t, str) and t.strip():
                        answer_texts.append(t.strip())
                    c = ans.get("confidence")
                    if isinstance(c, (int, float)):
                        try:
                            confidences.append(float(c))
                        except Exception:
                            pass
                    objs = ans.get("objects")
                    if isinstance(objs, list):
                        for o in objs:
                            if isinstance(o, str) and o.strip() and o.strip().lower() not in answer_objects:
                                answer_objects.append(o.strip().lower())

            header = "Image analysis" + (f" (prompt: {prompt})" if prompt else "")

            if prompt and answer_texts:
                # Prefer prompt-specific answers; optionally add captions for transparency.
                lines: List[str] = []
                multi = len(image_paths or []) > 1
                for idx, t in enumerate(answer_texts):
                    prefix = f"Image {idx + 1}: " if multi else ""
                    lines.append(f"- {prefix}{t}")
                body = "\n".join(lines)
            elif descriptions:
                body = "\n\n".join([f"- {d}" for d in descriptions])
            else:
                body = "- Image analysis unavailable (no cloud key and local captioning could not run)."

            def _image_subject_from_text(text: str) -> str:
                stop = {
                    "a",
                    "an",
                    "the",
                    "on",
                    "in",
                    "at",
                    "of",
                    "and",
                    "with",
                    "to",
                    "for",
                }
                common = {
                    "laptop",
                    "computer",
                    "keyboard",
                    "screen",
                    "phone",
                    "butterfly",
                    "flower",
                    "cat",
                    "dog",
                    "car",
                    "person",
                }
                tokens = [t.strip(".,:;()[]{}\"'`).").lower() for t in (text or "").split()]
                tokens = [t for t in tokens if t.isalpha() and t not in stop]
                for t in tokens:
                    if t in common:
                        return t
                return tokens[0] if tokens else "image"

            subject = _image_subject_from_text(descriptions[0]) if descriptions else "image"
            if answer_objects:
                # If we extracted objects, prefer the most salient one.
                subject = answer_objects[0]
            suggestions = [
                "What objects are in the image?",
                "Summarize the image in one sentence.",
                f"Describe the {subject} in detail.",
            ]

            confidence = 0.0
            if confidences:
                try:
                    confidence = max(0.0, min(1.0, sum(confidences) / float(len(confidences))))
                except Exception:
                    confidence = 0.0

            response = {
                "text": f"{header}:\n{body}",
                "domain": "multimodal",
                "sentiment_adapted": "NEUTRAL",
                "confidence": float(confidence),
                "include_image": False,
                "context_used": 0,
                "language": self.config.DEFAULT_LANGUAGE,
                "suggestions": suggestions,
            }
            # Translate output back to user's language (or preferred language).
            if target_out != self.config.DEFAULT_LANGUAGE:
                try:
                    language = self._ensure_language()
                    response["text"] = language.translate_from_default(response["text"], target_out)
                    response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                    response["language"] = target_out
                except Exception:
                    response["language"] = target_out
            return response

        if task_id == 3:
            med = self._ensure_medical_qa()
            context = med.retrieve_context(processed_input)
            answer_result = med.generate_answer_result(processed_input, context)
            entities = med.recognize_medical_entities(processed_input)
            references = self._build_references("medical", context)
            if answer_result.get("source_label") == "MedQuAD" and answer_result.get("matched_question"):
                references = [
                    {
                        "title": "Matched MedQuAD Question",
                        "question": answer_result.get("matched_question"),
                        "source": "MedQuAD",
                    }
                ] + references
            response = {
                "text": str(answer_result.get("text", "")),
                "domain": "medical",
                "sentiment_adapted": "NEUTRAL",
                "confidence": 0.0,
                "include_image": False,
                "context_used": len(context),
                "language": self.config.DEFAULT_LANGUAGE,
                "medical_entities": entities,
                "answer_source": answer_result.get("source_label"),
                "matched_question": answer_result.get("matched_question"),
                "references": references,
                "pipeline": ["forced_task:3", "medical_ner", f"retrieval:{len(context)}", "answer_generation"],
                "suggestions": self._generate_suggestions(processed_input, "medical", str(answer_result.get("text", "")), user_id=user_id),
            }
            if target_out != self.config.DEFAULT_LANGUAGE:
                try:
                    language = self._ensure_language()
                    response["text"] = language.translate_from_default(response["text"], target_out)
                    response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                    response["language"] = target_out
                except Exception:
                    response["language"] = target_out
            return response

        if task_id == 4:
            de = self._ensure_domain_expert()

            # Determine the effective search topic.
            # Follow-up meta-commands ("Give a short summary.", "Provide a BibTeX
            # citation.", "What are limitations?") have no standalone topic —
            # reuse the last academic topic queried by this user.
            # For genuine topic queries, clean instruction verbs/qualifiers so
            # "Explain transformers with citations" searches for "transformers".
            if de.is_followup_query(processed_input):
                search_topic = self._last_academic_topic.get(user_id, "") or processed_input
                context = self._last_academic_context.get(user_id) or de.retrieve_context(search_topic)
            else:
                cleaned = de.clean_search_query(processed_input)
                search_topic = cleaned if cleaned and len(cleaned) >= 3 else processed_input
                self._last_academic_topic[user_id] = search_topic
                context = de.retrieve_context(search_topic)
                self._last_academic_context[user_id] = context
            academic_analysis = de.build_topic_analysis(search_topic, context)
            explanation = de.generate_explanation(
                processed_input,
                context,
                topic=search_topic,
                analysis=academic_analysis,
            )
            response = {
                "text": explanation,
                "domain": "academic",
                "sentiment_adapted": "NEUTRAL",
                "confidence": 0.0,
                "include_image": False,
                "context_used": len(context),
                "language": self.config.DEFAULT_LANGUAGE,
                "references": self._build_references("academic", context),
                "academic_analysis": academic_analysis,
                "search_topic": search_topic,
                "pipeline": ["forced_task:4", f"retrieval:{len(context)}", "research_generation"],
                "suggestions": self._generate_suggestions(processed_input, "academic", explanation, user_id=user_id),
            }
            if target_out != self.config.DEFAULT_LANGUAGE:
                try:
                    language = self._ensure_language()
                    response["text"] = language.translate_from_default(response["text"], target_out)
                    response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                    response["language"] = target_out
                except Exception:
                    response["language"] = target_out
            return response

        if task_id == 5:
            sentiment = self._ensure_sentiment().analyze(processed_input, user_id)
            label = sentiment.get("sentiment", "NEUTRAL")
            conf = sentiment.get("confidence", 0.0)
            scores = sentiment.get("scores") if isinstance(sentiment, dict) else None
            emotions = sentiment.get("emotions") if isinstance(sentiment, dict) else None
            t_label = sentiment.get("transformer_label") if isinstance(sentiment, dict) else None
            t_score = sentiment.get("transformer_score") if isinstance(sentiment, dict) else None

            text_lines = [f"Sentiment: {label}", f"Confidence: {conf:.2f}"]
            if isinstance(emotions, list) and emotions:
                text_lines.append(f"Emotions: {', '.join([str(e) for e in emotions])}")
            if isinstance(scores, dict) and scores:
                text_lines.append(
                    "VADER: "
                    + ", ".join(
                        [
                            f"pos={scores.get('pos', scores.get('positive', 0)):.2f}",
                            f"neu={scores.get('neu', scores.get('neutral', 0)):.2f}",
                            f"neg={scores.get('neg', scores.get('negative', 0)):.2f}",
                            f"compound={scores.get('compound', 0):.2f}",
                        ]
                    )
                )
            if isinstance(t_label, str) and isinstance(t_score, (int, float)):
                text_lines.append(f"Transformer: {t_label} ({float(t_score):.2f})")
            response = {
                "text": "\n".join(text_lines),
                "domain": "sentiment",
                "sentiment_adapted": label,
                "confidence": conf,
                "include_image": False,
                "context_used": 0,
                "language": self.config.DEFAULT_LANGUAGE,
                "pipeline": ["forced_task:5", "sentiment_analysis"],
                "suggestions": self._generate_suggestions(processed_input, "sentiment", "\n".join(text_lines), user_id=user_id),
            }
            if target_out != self.config.DEFAULT_LANGUAGE:
                try:
                    language = self._ensure_language()
                    response["text"] = language.translate_from_default(response["text"], target_out)
                    response["text"] = language.apply_cultural_adaptation(response["text"], target_out)
                    response["language"] = target_out
                except Exception:
                    response["language"] = target_out
            return response

        if task_id == 6:
            # Task 6 can load additional translation models. In long-lived Streamlit
            # sessions, other tasks may have already loaded large models; release
            # them first to reduce the chance of the Streamlit process exiting.
            try:
                self._release_nonessential_modules(keep={"language"})
            except Exception:
                pass

            language = self._ensure_language()
            import re

            normalized = language.normalize_text(raw_input)
            # Users often type commands like "Translate: <text>"; strip that prefix so
            # language detection/translation operates on the actual content.
            m = re.match(r"(?is)^\s*(translate|translation)\s*[:\-]\s*(.+)$", normalized)
            translatable = (m.group(2).strip() if m else normalized)

            detected = language.detect_language(translatable)
            to_default = language.translate_to_default(translatable, detected)
            back = (
                language.translate_from_default(to_default, detected)
                if detected != self.config.DEFAULT_LANGUAGE
                else translatable
            )

            # Advanced language processing signals
            lang_name = getattr(language, "language_codes", {}).get(detected, detected)
            script = "unknown"
            try:
                script = language.detect_script(translatable)
            except Exception:
                script = "unknown"
            rtl = False
            try:
                rtl = bool(language.is_rtl_language(detected))
            except Exception:
                rtl = False

            conf_lines = ""
            try:
                confs = language.detect_language_with_confidence(translatable)
                top = confs[:3] if isinstance(confs, list) else []
                if top:
                    conf_lines = "\n".join([f"- {c[0]}: {float(c[1]):.2f}" for c in top if isinstance(c, tuple) and len(c) == 2])
            except Exception:
                conf_lines = ""

            guidelines = {}
            try:
                guidelines = language.get_cultural_guidelines(detected) or {}
            except Exception:
                guidelines = {}

            adapted_example = ""
            if detected != self.config.DEFAULT_LANGUAGE:
                try:
                    adapted_example = language.apply_cultural_adaptation(back, detected)
                except Exception:
                    adapted_example = ""

            note = ""
            if detected != self.config.DEFAULT_LANGUAGE:
                if not getattr(language, "enable_translation", True):
                    note = (
                        "\n\nNote: Translation is currently disabled for stability in the Streamlit demo. "
                        "Set ENABLE_TRANSLATION=1 in your .env to enable HuggingFace/deep-translator backends."
                    )
                else:
                    try:
                        same_forward = language.normalize_text(to_default) == language.normalize_text(translatable)
                        same_back = language.normalize_text(back) == language.normalize_text(translatable)
                    except Exception:
                        same_forward = to_default.strip() == (translatable or "").strip()
                        same_back = back.strip() == (translatable or "").strip()

                    if same_forward and same_back:
                        note = (
                            "\n\nNote: Translation backend appears unavailable, so output may be unchanged. "
                            "This build uses a lightweight offline phrasebook by default; optional online translation can be enabled via ENABLE_ONLINE_TRANSLATION=1."
                        )

            confidence = 0.0
            if detected != self.config.DEFAULT_LANGUAGE and getattr(language, "enable_translation", True):
                confidence = 0.7 if language.normalize_text(to_default) != language.normalize_text(translatable) else 0.0
            return {
                "text": (
                    f"Detected language: {detected} ({lang_name})\n"
                    f"Script: {script} | RTL: {rtl}\n\n"
                    + (f"Detection confidence (top):\n{conf_lines}\n\n" if conf_lines else "")
                    + (
                        "Cultural guidelines:\n"
                        + "\n".join(
                            [
                                f"- formality: {guidelines.get('formality', 'neutral')}",
                                f"- tone: {guidelines.get('tone', 'professional')}",
                                f"- greeting: {guidelines.get('greeting', '')}",
                                f"- closing: {guidelines.get('closing', '')}",
                            ]
                        )
                        + "\n\n"
                    )
                    + f"Translated to {self.config.DEFAULT_LANGUAGE}:\n{to_default}\n\n"
                    + f"Back-translated:\n{back}\n"
                    + (f"\nCulturally adapted (example):\n{adapted_example}\n" if adapted_example else "")
                    + note
                ),
                "domain": "language",
                "sentiment_adapted": "NEUTRAL",
                "confidence": confidence,
                "include_image": False,
                "context_used": 0,
                "language": detected,
                "pipeline": ["forced_task:6", "language_detection", "translation"],
                "suggestions": self._generate_suggestions(processed_input, "language", f"Detected language: {detected}", user_id=user_id),
            }

        # Task 1: KB / general response from vector DB.
        if task_id == 1:
            import re

            def _finalize_task1(resp: Dict) -> Dict:
                # Translate Task 1 output back to the user's (or preferred) language.
                if target_out != self.config.DEFAULT_LANGUAGE:
                    try:
                        language = self._ensure_language()
                        resp["text"] = language.translate_from_default(resp.get("text", "") or "", target_out)
                        resp["text"] = language.apply_cultural_adaptation(resp.get("text", "") or "", target_out)
                        resp["language"] = target_out
                    except Exception:
                        resp["language"] = target_out
                return resp

            prompt = (raw_input or "").strip().lower()
            # Avoid substring traps like "photosynthesis" containing "photo".
            is_image_intent = bool(
                re.search(r"\b(image|photo|picture)\b", prompt)
                or "in the image" in prompt
                or "in this image" in prompt
                or "what do you see" in prompt
                or "what's in the image" in prompt
                or "what is in the image" in prompt
            )
            if is_image_intent:
                return _finalize_task1({
                    "text": "This looks like an image question. Switch to Task 2 (Multi-Modal) and upload an image.",
                    "domain": "general",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.0,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": [],
                })

            # Guard rails: Task 1 is meant for non-medical, non-arXiv/general questions.
            # If the user asks a medical or academic question while Task 1 is forced,
            # route them to the correct task instead of returning unrelated KB content.
            if self._is_medical_query_light(processed_input):
                return _finalize_task1({
                    "text": "This looks like a medical question. Switch to Task 3 (Medical Q&A) and ask again.",
                    "domain": "general",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.0,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": [
                        "Switch to Task 3 — Medical Q&A",
                        "What are the symptoms of diabetes?",
                    ],
                })

            def _is_research_intent(text: str) -> bool:
                t = (text or "").lower()
                markers = [
                    "arxiv",
                    "paper",
                    "papers",
                    "research",
                    "recent work",
                    "state of the art",
                    "literature",
                    "survey",
                    "systematic review",
                    "citation",
                    "cite",
                    "bibtex",
                    "conference",
                    "journal",
                    "retrieval-augmented generation",
                ]
                return any(m in t for m in markers)

            # Only route to Task 4 when the user explicitly signals *research/papers* intent.
            # General AI concepts (e.g., "neural network") should not be forced into Task 4.
            if _is_research_intent(processed_input):
                return _finalize_task1({
                    "text": "This looks like a research/papers question. Switch to Task 4 (Domain Expert) and ask again.",
                    "domain": "general",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.0,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": [
                        "Switch to Task 4 — Domain Expert (arXiv)",
                        "Summarize recent work on retrieval-augmented generation.",
                    ],
                })

            # Handle generic follow-ups like "Give an example" using the last Task 1 topic.
            # This prevents the new retrieval guard (topic-token overlap) from treating
            # follow-ups as empty-topic queries.
            user_input_l = (raw_input or "").strip().lower()
            wants_example = user_input_l in {
                "example",
                "give example",
                "give an example",
                "show an example",
                "can you give an example",
            }
            if wants_example:
                last_topic = None
                try:
                    last_topic = self.user_profile.get(user_id, {}).get("last_task1_topic")
                except Exception:
                    last_topic = None

                if isinstance(last_topic, str) and last_topic.strip():
                    topic = last_topic.strip().lower()
                    if topic == "python":
                        return _finalize_task1({
                            "text": (
                                "Example (Python for AI/data science):\n"
                                "  • Read a CSV with pandas and compute summary stats.\n"
                                "  • Train a simple model with scikit-learn (e.g., spam vs not-spam).\n\n"
                                "If you meant an example of something else, tell me the topic."
                            ),
                            "domain": "general",
                            "sentiment_adapted": "NEUTRAL",
                            "confidence": 0.4,
                            "include_image": False,
                            "context_used": 0,
                            "language": self.config.DEFAULT_LANGUAGE,
                            "suggestions": [
                                "Give an example of Python in data science",
                                "Give an example of Python in machine learning",
                            ],
                        })

                    return _finalize_task1({
                        "text": (
                            f"Example request noted — do you mean an example about '{last_topic}'? "
                            "If yes, say: 'Give an example of "
                            f"{last_topic}'."
                        ),
                        "domain": "general",
                        "sentiment_adapted": "NEUTRAL",
                        "confidence": 0.2,
                        "include_image": False,
                        "context_used": 0,
                        "language": self.config.DEFAULT_LANGUAGE,
                        "suggestions": [
                            f"Give an example of {last_topic}",
                            "What is Python used for?",
                        ],
                    })

                return _finalize_task1({
                    "text": "Example of what topic? (e.g., 'Give an example of Python in AI')",
                    "domain": "general",
                    "sentiment_adapted": "NEUTRAL",
                    "confidence": 0.2,
                    "include_image": False,
                    "context_used": 0,
                    "language": self.config.DEFAULT_LANGUAGE,
                    "suggestions": [
                        "Give an example of Python in AI",
                        "Give an example of Python in data science",
                    ],
                })

        context = self._ensure_vector_db().retrieve(processed_input, top_k=5)

        # Track the last Task 1 topic for follow-ups like "Give an example".
        if task_id == 1:
            try:
                import re

                cleaned = re.sub(r"[^a-z0-9\s]", " ", (processed_input or "").lower()).split()
                stop = {
                    "a",
                    "an",
                    "the",
                    "what",
                    "which",
                    "who",
                    "where",
                    "when",
                    "why",
                    "how",
                    "is",
                    "are",
                    "was",
                    "were",
                    "to",
                    "of",
                    "for",
                    "in",
                    "on",
                    "at",
                    "with",
                    "about",
                    "explain",
                    "describe",
                    "define",
                    "summarize",
                    "simple",
                    "words",
                    "give",
                    "example",
                }
                topic_tokens = [t for t in cleaned if t not in stop and (len(t) >= 4 or t.isdigit())]
                if topic_tokens:
                    if user_id not in self.user_profile:
                        self.user_profile[user_id] = {}
                    # Use the first topical token as a simple "topic".
                    self.user_profile[user_id]["last_task1_topic"] = topic_tokens[0]
            except Exception:
                pass

        # Task 1 validation aid: if the KB has no matching context, avoid returning unrelated text.
        if task_id == 1 and not context:
            return _finalize_task1({
                "text": (
                    "I don't have specific information about that topic in my local knowledge base right now.\n\n"
                    "To validate Task 1, try one of these (they should return a relevant KB-based response):\n"
                    "  • What is Python used for?\n"
                    "  • What is Python?\n\n"
                    "If your question is medical, use Task 3. If it's research/papers, use Task 4."
                ),
                "domain": "general",
                "sentiment_adapted": "NEUTRAL",
                "confidence": 0.0,
                "include_image": False,
                "context_used": 0,
                "language": self.config.DEFAULT_LANGUAGE,
                "suggestions": [
                    "What is Python used for?",
                    "What is Python?",
                    "Switch to Task 3 — Medical Q&A",
                    "Switch to Task 4 — Domain Expert (arXiv)",
                ],
            })

        text = self._ensure_multimodal().generate_text_response(processed_input, context)
        try:
            confidence = max(
                [float(d.get("score", 0.0)) for d in (context or []) if isinstance(d, dict)],
                default=0.0,
            )
            confidence = max(0.0, min(1.0, confidence))
        except Exception:
            confidence = 0.0
        return _finalize_task1({
            "text": text,
            "domain": "general",
            "sentiment_adapted": "NEUTRAL",
            "confidence": float(confidence),
            "include_image": False,
            "context_used": len(context),
            "language": self.config.DEFAULT_LANGUAGE,
            "references": self._build_references("general", context),
            "pipeline": ["forced_task:1", f"retrieval:{len(context)}", "answer_generation"],
            "suggestions": self._generate_suggestions(processed_input, "general", text, user_id=user_id),
        })


if __name__ == "__main__":
    # Initialize chatbot
    chatbot = UnifiedChatbot()

    # Example usage
    print("Unified Chatbot System - Interactive Mode")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue

            if user_input.lower() == "exit":
                print("Goodbye!")
                break

            if user_input.lower() == "status":
                print(json.dumps(chatbot.get_system_status(), indent=2))
                continue

            response = chatbot.process_user_input(user_input)
            print(f"\nChatbot: {response['text']}")
            if response.get("include_image"):
                print("[Image would be displayed here]")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            print(f"Error: {str(e)}")

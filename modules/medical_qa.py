"""Task 3: Medical Q&A support."""

import csv
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

try:
    import spacy
except ImportError:
    spacy = None

try:
    from .vector_db import VectorDatabaseManager
except Exception:
    VectorDatabaseManager = None


logger = logging.getLogger(__name__)


class MedicalQASystem:
    """Lightweight medical retrieval over built-in facts and MedQuAD CSV."""

    MAX_QA = 8000

    def __init__(self, config):
        self.config = config
        self.data_path = Path(config.MEDQUAD_DATA_PATH)
        self.medical_knowledge: Dict[str, Dict[str, List[str] | str]] = {}
        self.condition_aliases: Dict[str, List[str]] = {}
        self.entity_catalog: Dict[str, Dict[str, str]] = {
            "symptoms": {},
            "diseases": {},
            "treatments": {},
        }
        self.medquad_qa: List[Dict[str, str]] = []
        self.question_index: Dict[str, List[Dict[str, str]]] = {}
        self.vector_db = None

        if VectorDatabaseManager is not None:
            try:
                self.vector_db = VectorDatabaseManager(config)
            except Exception as exc:
                logger.warning(f"Vector DB unavailable for medical QA: {exc}")

        self.nlp = None
        if spacy is not None:
            try:
                self.nlp = spacy.load(
                    "en_core_web_sm",
                    disable=["parser", "tagger", "lemmatizer", "attribute_ruler"],
                )
            except Exception:
                logger.warning("SpaCy model not available for medical entity recognition")

        self._initialize_basic_knowledge()
        self._load_medquad_csv(self.data_path / "medquad.csv")
        logger.info("Medical QA initialized")

    def _initialize_basic_knowledge(self) -> None:
        self.medical_knowledge = {
            "fever": {
                "definition": "A temporary rise in body temperature, often caused by infection or inflammation.",
                "symptoms": ["sweating", "chills", "body aches", "fatigue"],
                "treatment": ["rest", "fluids", "fever reducers if appropriate"],
                "when_to_seek_care": ["seek medical advice if fever is very high, lasts more than a few days, or keeps coming back", "seek urgent care if fever happens with confusion, trouble breathing, severe dehydration, stiff neck, chest pain, or seizures"],
            },
            "anxiety": {
                "definition": "A mental health condition that can cause excessive worry, fear, and physical stress symptoms.",
                "symptoms": ["restlessness", "racing thoughts", "muscle tension", "trouble sleeping", "fast heartbeat"],
                "treatment": ["stress management", "therapy", "medical evaluation when symptoms are severe or persistent"],
            },
            "dehydration": {
                "definition": "A condition where the body does not have enough fluid to function properly.",
                "symptoms": ["strong thirst", "dry mouth", "dark urine", "dizziness", "fatigue", "reduced urination"],
                "treatment": ["drink fluids", "replace electrolytes when needed", "seek medical help if symptoms are severe or persistent"],
                "when_to_seek_care": ["seek urgent care for confusion, fainting, rapid breathing, or inability to keep fluids down"],
            },
            "diabetes": {
                "definition": "A chronic condition that affects how the body regulates blood sugar.",
                "symptoms": ["increased thirst", "frequent urination", "fatigue"],
                "treatment": ["medication or insulin as prescribed", "diet control", "exercise"],
            },
            "hypertension": {
                "definition": "Persistently high blood pressure.",
                "symptoms": ["often none", "headache in some cases", "shortness of breath in severe cases"],
                "treatment": ["lifestyle changes", "medication", "regular monitoring"],
            },
            "asthma": {
                "definition": "A chronic inflammatory airway disease that can cause breathing difficulty.",
                "symptoms": ["wheezing", "shortness of breath", "chest tightness", "cough"],
                "treatment": ["avoid triggers", "inhalers", "medical follow-up"],
            },
            "migraine": {
                "definition": "A neurological condition that can cause intense, often one-sided headaches and sensitivity to light or sound.",
                "symptoms": ["throbbing headache", "nausea", "light sensitivity", "sound sensitivity", "visual aura in some people"],
                "causes": ["genetic predisposition", "stress", "hormonal changes", "sleep disruption", "certain foods or dehydration"],
                "treatment": ["rest in a dark quiet room", "hydration", "pain-relief or migraine-specific medicines as prescribed"],
            },
            "iron deficiency anemia": {
                "definition": "A condition in which the body lacks enough iron to make healthy red blood cells.",
                "symptoms": ["fatigue", "weakness", "shortness of breath", "pale skin", "dizziness", "headaches"],
                "causes": ["low iron intake", "blood loss", "poor iron absorption", "increased iron needs during pregnancy"],
                "treatment": ["treat the cause", "iron-rich diet", "iron supplements if advised by a clinician"],
            },
            "pneumonia": {
                "definition": "An infection that inflames air sacs in the lungs.",
                "symptoms": ["cough", "fever", "chest pain", "shortness of breath"],
                "treatment": ["medical evaluation", "fluids and rest", "targeted treatment based on cause"],
            },
            "covid-19": {
                "definition": "A respiratory illness caused by SARS-CoV-2.",
                "symptoms": ["fever", "cough", "fatigue", "sore throat", "loss of taste or smell"],
                "treatment": ["rest and hydration", "symptom relief", "seek medical care for breathing difficulty"],
            },
            "chest pain": {
                "definition": "Chest pain can range from minor causes to medical emergencies involving the heart or lungs.",
                "causes": ["muscle strain", "acid reflux", "anxiety", "lung problems", "heart-related problems"],
                "when_to_seek_care": ["call emergency services right away if chest pain is severe, crushing, or spreading to the arm, back, jaw, or neck", "seek urgent care if it happens with shortness of breath, fainting, sweating, nausea, or blue lips", "if it is new, unexplained, or persistent, arrange prompt medical evaluation"],
            },
        }
        self.condition_aliases = {
            "anxiety": ["anxiety", "anxious", "panic", "panic attack"],
            "asthma": ["asthma", "wheezing"],
            "chest pain": ["chest pain", "heart attack", "pressure in chest"],
            "covid-19": ["covid", "covid-19", "coronavirus", "sars-cov-2"],
            "dehydration": ["dehydration", "dehydrated", "dry mouth", "dark urine"],
            "diabetes": ["diabetes", "high blood sugar", "blood sugar"],
            "fever": ["fever", "high temperature"],
            "hypertension": ["hypertension", "high blood pressure"],
            "iron deficiency anemia": ["iron deficiency anemia", "anemia", "low iron"],
            "migraine": ["migraine", "migraine headache", "migraine headaches"],
            "pneumonia": ["pneumonia", "lung infection"],
        }
        self._build_entity_catalog()

    def _normalize_phrase(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
        return re.sub(r"\s+", " ", normalized)

    def _register_entity_term(self, bucket: str, term: str, canonical: str) -> None:
        normalized_term = self._normalize_phrase(term)
        if not normalized_term:
            return
        self.entity_catalog[bucket].setdefault(normalized_term, canonical.strip())

    def _build_entity_catalog(self) -> None:
        self.entity_catalog = {"symptoms": {}, "diseases": {}, "treatments": {}}

        for condition, aliases in self.condition_aliases.items():
            self._register_entity_term("diseases", condition, condition)
            for alias in aliases:
                self._register_entity_term("diseases", alias, condition)

        for condition, data in self.medical_knowledge.items():
            self._register_entity_term("diseases", condition, condition)

            symptoms = data.get("symptoms") if isinstance(data.get("symptoms"), list) else []
            for symptom in symptoms:
                self._register_entity_term("symptoms", str(symptom), str(symptom))

            treatments = data.get("treatment") if isinstance(data.get("treatment"), list) else []
            for treatment in treatments:
                self._register_entity_term("treatments", str(treatment), str(treatment))

    def _find_catalog_terms(self, text: str, bucket: str) -> List[str]:
        normalized_text = self._normalize_phrase(text)
        if not normalized_text:
            return []

        padded_text = f" {normalized_text} "
        matches: List[str] = []
        seen = set()

        catalog = self.entity_catalog.get(bucket, {})
        for normalized_term in sorted(catalog.keys(), key=len, reverse=True):
            if f" {normalized_term} " not in padded_text:
                continue
            canonical = catalog[normalized_term]
            if canonical not in seen:
                matches.append(canonical)
                seen.add(canonical)

        return matches

    def _load_medquad_csv(self, path: Path) -> None:
        if not path.exists():
            logger.warning(f"MedQuAD CSV not found at {path}")
            return

        try:
            with path.open("r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for index, row in enumerate(reader):
                    if index >= self.MAX_QA:
                        break

                    question = (row.get("Question") or "").strip()
                    answer = (row.get("Answer") or "").strip()
                    if not question or not answer:
                        continue

                    item = {
                        "question": question,
                        "answer": answer,
                        "question_lower": question.lower(),
                    }
                    self.medquad_qa.append(item)

                    for word in self._tokenize(question):
                        self.question_index.setdefault(word, []).append(item)

            logger.info(f"Loaded {len(self.medquad_qa)} MedQuAD items")
        except Exception as exc:
            logger.error(f"Failed to load MedQuAD CSV: {exc}")

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in text).split() if len(token) >= 3]

    def is_medical_query(self, query: str) -> bool:
        keywords = {
            "symptom",
            "symptoms",
            "disease",
            "anxiety",
            "anemia",
            "treatment",
            "treatments",
            "doctor",
            "medicine",
            "pain",
            "migraine",
            "emergency",
            "chest",
            "infection",
            "diagnosis",
            "fever",
            "cough",
            "asthma",
            "diabetes",
            "hypertension",
            "pneumonia",
        }
        query_tokens = set(self._tokenize(query))
        return bool(query_tokens & keywords)

    def recognize_medical_entities(self, text: str) -> Dict[str, List[str]]:
        entities = {
            "symptoms": self._find_catalog_terms(text, "symptoms"),
            "diseases": self._find_catalog_terms(text, "diseases"),
            "treatments": self._find_catalog_terms(text, "treatments"),
        }

        if self.nlp is None:
            return entities

        try:
            doc = self.nlp(text)
            seen_diseases = set(entities["diseases"])
            for ent in doc.ents:
                candidate = self._normalize_phrase(ent.text)
                canonical = self.entity_catalog["diseases"].get(candidate)
                if canonical and canonical not in seen_diseases:
                    entities["diseases"].append(canonical)
                    seen_diseases.add(canonical)
        except Exception:
            pass
        return entities

    @lru_cache(maxsize=200)
    def retrieve_context(self, query: str) -> List[Dict[str, object]]:
        query_lower = (query or "").lower()
        results: List[Dict[str, object]] = []

        # Prefer built-in knowledge for clearly identified conditions.
        identified_condition = None
        for name, aliases in self.condition_aliases.items():
            if any(alias in query_lower for alias in aliases):
                identified_condition = name
                data = self.medical_knowledge.get(name)
                if data:
                    results.append(
                        {
                            "content": self._format_condition(name, data),
                            "score": 22.0,
                            "metadata": {"source": "builtin", "condition": name},
                        }
                    )
                break

        if identified_condition:
            # If we found a strong condition match, also include a few related medquad results
            query_tokens = set(self._tokenize(query))
            for item in self.medquad_qa:
                question_lower = item.get("question_lower", "")
                if identified_condition in question_lower or any(alias in question_lower for alias in self.condition_aliases.get(identified_condition, [])):
                    results.append({
                        "content": item.get("answer", ""),
                        "score": 10.0,
                        "metadata": {"source": "MedQuAD", "question": item.get("question", "")},
                    })
                    if len(results) >= 5:
                        break
            return results

        for name, aliases in self.condition_aliases.items():
            if any(alias in query_lower for alias in aliases):
                data = self.medical_knowledge.get(name)
                if data is None:
                    continue
                results.append(
                    {
                        "content": self._format_condition(name, data),
                        "score": 12.0,
                        "metadata": {"source": "builtin", "condition": name},
                    }
                )

        for name, data in self.medical_knowledge.items():
            if name in query_lower:
                results.append(
                    {
                        "content": self._format_condition(name, data),
                        "score": 10.0,
                        "metadata": {"source": "builtin", "condition": name},
                    }
                )

        query_tokens = set(self._tokenize(query))
        ranked: List[Dict[str, object]] = []
        seen_questions = set()
        intent_terms = {
            "symptom": ["symptom", "symptoms", "sign", "signs"],
            "treatment": ["treat", "treatment", "therapy", "medication"],
            "cause": ["cause", "causes", "why", "trigger", "triggers"],
            "prevention": ["prevent", "prevention", "avoid"],
            "emergency": ["emergency", "urgent", "seek medical attention", "doctor"],
        }
        matched_intents = {
            name
            for name, terms in intent_terms.items()
            if any(term in query_lower for term in terms)
        }

        candidates = set()
        for token in query_tokens:
            candidates.update(item["question"] for item in self.question_index.get(token, []))

        for item in self.medquad_qa:
            question = item["question"]
            if candidates and question not in candidates:
                continue
            if question in seen_questions:
                continue
            seen_questions.add(question)

            question_lower = item["question_lower"]
            question_tokens = set(self._tokenize(question_lower))
            overlap = query_tokens & question_tokens
            if not overlap:
                continue

            score = float(len(overlap))
            if question_lower in query_lower or query_lower in question_lower:
                score += 4.0

            overlap_ratio = len(overlap) / max(len(query_tokens), 1)
            score += overlap_ratio * 4.0

            if matched_intents:
                if any(any(term in question_lower for term in intent_terms[intent]) for intent in matched_intents):
                    score += 2.0
                else:
                    score -= 1.5

            if score < 3.0:
                continue

            ranked.append(
                {
                    "content": item["answer"],
                    "score": round(score, 3),
                    "metadata": {"source": "medquad", "question": question},
                }
            )

        combined = results + ranked
        combined.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return combined[:3]

    def _format_condition(self, name: str, data: Dict[str, List[str] | str]) -> str:
        lines = [f"Condition: {name.capitalize()}"]
        sections = [
            ("definition", "Definition"),
            ("symptoms", "Symptoms"),
            ("causes", "Common causes"),
            ("treatment", "Treatment"),
            ("when_to_seek_care", "Seek urgent care if"),
        ]
        for key, label in sections:
            value = data.get(key)
            if isinstance(value, str) and value:
                lines.append(f"{label}: {value}")
            elif isinstance(value, list) and value:
                lines.append(f"{label}:")
                lines.extend([f"- {item}" for item in value])

        return "\n".join(lines)

    def _summarize_medquad_answer(self, query: str, answer: str) -> str:
        cleaned = re.sub(r"\s+", " ", (answer or "")).strip()
        if not cleaned:
            return ""

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        selected: List[str] = []
        query_tokens = set(self._tokenize(query))

        for sentence in sentences:
            sentence_clean = sentence.strip()
            if not sentence_clean:
                continue
            sentence_tokens = set(self._tokenize(sentence_clean))
            if query_tokens & sentence_tokens:
                selected.append(sentence_clean)
            if len(selected) >= 3:
                break

        if not selected:
            selected = [sentence.strip() for sentence in sentences[:2] if sentence.strip()]

        return "\n".join([f"- {sentence}" for sentence in selected[:3]])

    def _answer_result(
        self,
        text: str,
        source: str,
        matched_question: Optional[str] = None,
    ) -> Dict[str, object]:
        source_label = "MedQuAD" if source == "medquad" else "Built-in"
        result: Dict[str, object] = {
            "text": text,
            "source": source,
            "source_label": source_label,
        }
        if matched_question:
            result["matched_question"] = matched_question
        return result

    def generate_answer_result(
        self,
        query: str,
        context: Optional[List[Dict[str, object]]] = None,
    ) -> Dict[str, object]:
        query_lower = (query or "").lower()

        if "type 1" in query_lower and "type 2" in query_lower and "diabetes" in query_lower:
            return self._answer_result(
                (
                    "Type 1 vs Type 2 diabetes:\n"
                    "- Type 1: Autoimmune destruction of insulin-producing beta cells; usually requires insulin therapy.\n"
                    "- Type 2: Insulin resistance with progressive beta-cell dysfunction; often managed with lifestyle changes and medications, sometimes insulin.\n"
                    "- Typical onset: Type 1 often starts earlier in life, while Type 2 is more common in adults (but can occur at any age).\n"
                    "- Risk factors: Type 2 is strongly associated with obesity, inactivity, and family history."
                ),
                source="builtin",
            )

        if any(term in query_lower for term in ["covid", "covid-19", "coronavirus", "sars-cov-2"]):
            return self._answer_result(
                self._format_condition("covid-19", self.medical_knowledge["covid-19"]),
                source="builtin",
            )

        if "chest pain" in query_lower and any(term in query_lower for term in ["when should", "seek", "emergency", "urgent"]):
            return self._answer_result(
                self._format_condition("chest pain", self.medical_knowledge["chest pain"]),
                source="builtin",
            )

        if "fever" in query_lower and any(term in query_lower for term in ["when should", "medical concern", "see a doctor", "seek care"]):
            return self._answer_result(
                self._format_condition("fever", self.medical_knowledge["fever"]),
                source="builtin",
            )

        if any(term in query_lower for term in ["dehydration", "dehydrated"]) and any(term in query_lower for term in ["warning", "sign", "symptom"]):
            return self._answer_result(
                self._format_condition("dehydration", self.medical_knowledge["dehydration"]),
                source="builtin",
            )

        context = context if context is not None else self.retrieve_context(query)
        if not context:
            return self._answer_result(
                (
                    "I do not have detailed information about that medical topic right now. "
                    "Please consult a qualified healthcare professional for diagnosis or treatment advice."
                ),
                source="builtin",
            )

        lead = context[0] if isinstance(context[0], dict) else {}
        lead_score = float(lead.get("score", 0.0)) if isinstance(lead, dict) else 0.0
        metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}

        preferred_medquad = None
        for item in context:
            if not isinstance(item, dict):
                continue
            item_metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            if item_metadata.get("source") == "medquad" and float(item.get("score", 0.0)) >= 3.0:
                preferred_medquad = item
                break

        selected = preferred_medquad if preferred_medquad is not None else lead
        selected_metadata = selected.get("metadata", {}) if isinstance(selected.get("metadata"), dict) else {}
        source = str(selected_metadata.get("source") or "builtin")

        if source == "builtin":
            condition = selected_metadata.get("condition")
            if isinstance(condition, str) and condition in self.medical_knowledge:
                return self._answer_result(
                    self._format_condition(condition, self.medical_knowledge[condition]),
                    source="builtin",
                )

        if lead_score < 3.0 and preferred_medquad is None:
            return self._answer_result(
                (
                    "I could not find a confident medical match for that question. "
                    "Please rephrase it with the condition, symptom, or treatment you want to ask about, "
                    "and seek professional medical help if the issue is urgent."
                ),
                source="builtin",
            )

        snippets = []
        for item in context[:3]:
            content = item.get("content") if isinstance(item, dict) else None
            if isinstance(content, str) and content.strip():
                snippets.append(content.strip())

        if not snippets:
            return self._answer_result(
                (
                    "I found medical context, but it could not be formatted into an answer. "
                    "Please consult a qualified healthcare professional if your concern is urgent."
                ),
                source="builtin",
            )

        lead_answer = selected.get("content") if isinstance(selected.get("content"), str) else snippets[0]
        question = selected_metadata.get("question") if isinstance(selected_metadata, dict) else None
        if source == "medquad" and isinstance(question, str):
            summary = self._summarize_medquad_answer(query, lead_answer)
            if summary:
                return self._answer_result(
                    f"Best matching medical reference: {question}\n{summary}",
                    source="medquad",
                    matched_question=question,
                )

        return self._answer_result(str(lead_answer), source="builtin")

    def generate_answer(
        self,
        query: str,
        context: Optional[List[Dict[str, object]]] = None,
    ) -> str:
        return str(self.generate_answer_result(query, context).get("text", ""))
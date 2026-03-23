"""Task 4: Domain expert support for research-style answers over local arXiv data."""

import json
import logging
import re
from collections import Counter, deque
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class DomainExpertSystem:
    """Academic retrieval and explanation system over the local CS arXiv subset."""

    MAX_PAPERS = 15000
    STOP_TOKENS = {
        "about",
        "analysis",
        "and",
        "approach",
        "approaches",
        "based",
        "citation",
        "citations",
        "describe",
        "discuss",
        "explain",
        "field",
        "for",
        "from",
        "give",
        "into",
        "learning",
        "list",
        "machine",
        "method",
        "methods",
        "model",
        "models",
        "paper",
        "papers",
        "problem",
        "provide",
        "recent",
        "research",
        "results",
        "show",
        "study",
        "summary",
        "survey",
        "system",
        "tell",
        "that",
        "the",
        "their",
        "these",
        "this",
        "trends",
        "using",
        "with",
        "work",
    }
    GENERIC_CONCEPT_TOKENS = {
        "task",
        "tasks",
        "performance",
        "state",
        "art",
        "data",
        "dataset",
        "datasets",
        "benchmark",
        "benchmarks",
        "experiments",
        "experimental",
        "evaluation",
        "study",
        "paper",
        "papers",
        "method",
        "methods",
        "approach",
        "approaches",
        "problem",
        "problems",
        "result",
        "results",
    }
    FOLLOWUP_STARTERS = (
        "give a short summary",
        "list key contributions",
        "what are limitations",
        "what are the limitations",
        "what are the limitations of the paper",
        "what are the limitations of the paper you just referenced",
        "provide a bibtex citation",
        "provide bibtex citation",
        "provide a bibtex citation for that paper",
        "limitations and future work",
        "why is this important",
        "why does this matter",
        "how does this work",
        "how is this different",
        "compare this",
        "compare it",
        "what problem does this solve",
        "what are the tradeoffs",
    )
    FOLLOWUP_PATTERN = re.compile(
        r"^(it|this|that|they|those|these|the paper|the method|the model|the approach)\b",
        re.IGNORECASE,
    )
    METHOD_SENTENCE_MARKERS = (
        "propose",
        "present",
        "introduce",
        "evaluate",
        "train",
        "optimize",
        "retrieve",
        "compare",
        "benchmark",
        "fine-tune",
    )

    def __init__(self, config):
        self.config = config
        self.dataset_path = Path(config.ARXIV_DATASET_PATH) / "cs_papers.jsonl"
        self.papers: List[Dict[str, str]] = []
        self._generator = None
        self._generator_load_attempted = False
        self._load_dataset()
        logger.info("Domain Expert initialized")

    def _load_dataset(self) -> None:
        if not self.dataset_path.exists():
            logger.warning(f"arXiv dataset not found at {self.dataset_path}")
            return

        try:
            recent_papers: deque[Dict[str, str]] = deque(maxlen=self.MAX_PAPERS)
            with self.dataset_path.open("r", encoding="utf-8") as file:
                for line in file:
                    raw = (line or "").strip()
                    if not raw:
                        continue

                    try:
                        item = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    paper = {
                        "id": str(item.get("id") or ""),
                        "title": str(item.get("title") or "").strip(),
                        "abstract": str(item.get("abstract") or "").strip(),
                        "categories": str(item.get("categories") or "").strip(),
                        "authors": str(item.get("authors") or "").strip(),
                        "update_date": str(item.get("update_date") or "").strip(),
                    }
                    if paper["title"] or paper["abstract"]:
                        recent_papers.append(paper)

            self.papers = list(recent_papers)
            logger.info(f"Loaded {len(self.papers)} research papers")
        except Exception as exc:
            logger.error(f"Failed to load arXiv dataset: {exc}")

    def _tokenize(self, text: str) -> List[str]:
        normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in (text or ""))
        return [token for token in normalized.split() if len(token) >= 3]

    def _split_sentences(self, text: str) -> List[str]:
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text or "")
            if len(sentence.strip()) >= 40
        ]

    def _query_tokens(self, query: str) -> List[str]:
        tokens = [token for token in self._tokenize(query) if token not in self.STOP_TOKENS]
        expanded = list(tokens)
        aliases = {
            "transformer": ["transformer", "transformers", "attention"],
            "transformers": ["transformer", "transformers", "attention"],
            "rag": ["rag", "retrieval", "generation"],
            "retrieval": ["retrieval", "augmented", "generation", "rag"],
            "graph": ["graph", "graphs", "gnn", "gnns"],
            "neural": ["neural", "network", "networks"],
            "vision": ["vision", "visual", "image"],
            "language": ["language", "linguistic", "text"],
        }
        for token in list(tokens):
            expanded.extend(aliases.get(token, []))

        seen: List[str] = []
        for token in expanded:
            if token and token not in seen:
                seen.append(token)
        return seen

    def is_academic_query(self, query: str) -> bool:
        markers = {
            "paper",
            "papers",
            "research",
            "arxiv",
            "citation",
            "citations",
            "method",
            "methods",
            "model",
            "transformers",
            "retrieval",
            "generation",
            "neural",
            "graph",
            "survey",
            "literature",
            "authors",
            "bibtex",
        }
        return bool(set(self._tokenize(query)) & markers)

    def is_followup_meta_command(self, query: str) -> bool:
        lowered = (query or "").strip().lower()
        return any(lowered.startswith(item) for item in self.FOLLOWUP_STARTERS[:9])

    def is_followup_query(self, query: str) -> bool:
        lowered = (query or "").strip().lower()
        if not lowered:
            return False
        if any(lowered.startswith(item) for item in self.FOLLOWUP_STARTERS):
            return True
        if self.FOLLOWUP_PATTERN.match(lowered):
            return True
        return len(self._tokenize(lowered)) <= 8 and any(
            pronoun in lowered for pronoun in (" this", " it", " that", " they ")
        )

    def clean_search_query(self, query: str) -> str:
        lowered = (query or "").strip().lower()
        prefixes = [
            "explain",
            "summarize",
            "describe",
            "tell me about",
            "with citations",
            "recent work on",
            "recent trends in",
            "what is",
            "what are",
        ]
        cleaned = lowered
        for prefix in prefixes:
            cleaned = cleaned.replace(prefix, " ")
        return " ".join(self._tokenize(cleaned))

    @lru_cache(maxsize=200)
    def retrieve_context(self, query: str, top_k: int = 5) -> List[Dict[str, object]]:
        query_tokens = self._query_tokens(query)
        if not query_tokens:
            return []

        ranked: List[Dict[str, object]] = []
        query_phrase = " ".join(query_tokens)
        for paper in self.papers:
            title_tokens = set(self._tokenize(paper["title"]))
            abstract_tokens = set(self._tokenize(paper["abstract"]))
            category_tokens = set(self._tokenize(paper["categories"]))
            combined = title_tokens | abstract_tokens | category_tokens
            title_lower = paper["title"].lower()

            score = 0.0
            if query_phrase and query_phrase in title_lower:
                score += 10.0

            for token in query_tokens:
                if token in title_tokens:
                    score += 4.0
                elif token in category_tokens:
                    score += 3.0
                elif token in abstract_tokens:
                    score += 1.5

            overlap = len([token for token in query_tokens if token in combined])
            if overlap >= 2:
                score += overlap * 1.5

            if paper.get("update_date"):
                year = str(paper["update_date"])[:4]
                if year.isdigit() and int(year) >= 2020:
                    score += 0.2

            if score <= 0:
                continue

            ranked.append(
                {
                    "content": self._paper_to_context(paper),
                    "score": float(score),
                    "metadata": paper,
                }
            )

        ranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return ranked[:top_k]

    def search_papers(self, query: str, top_k: int = 8) -> List[Dict[str, object]]:
        results: List[Dict[str, object]] = []
        for item in self.retrieve_context(query, top_k=top_k):
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            results.append(
                {
                    "title": metadata.get("title") or metadata.get("id") or "Local paper",
                    "authors": metadata.get("authors", ""),
                    "categories": metadata.get("categories", ""),
                    "updated": metadata.get("update_date", ""),
                    "paper_id": metadata.get("id", ""),
                    "score": round(float(item.get("score", 0.0)), 3),
                    "abstract": metadata.get("abstract", ""),
                }
            )
        return results

    def _paper_to_context(self, paper: Dict[str, str]) -> str:
        lines = [f"Title: {paper.get('title', '')}"]
        if paper.get("authors"):
            lines.append(f"Authors: {paper['authors']}")
        if paper.get("categories"):
            lines.append(f"Categories: {paper['categories']}")
        if paper.get("update_date"):
            lines.append(f"Updated: {paper['update_date']}")
        if paper.get("abstract"):
            lines.append(f"Abstract: {paper['abstract']}")
        return "\n".join(lines)

    def _extractive_summary(self, query: str, context: List[Dict[str, object]], max_sentences: int = 3) -> str:
        query_tokens = set(self._query_tokens(query))
        scored_sentences: List[Dict[str, object]] = []

        for rank, item in enumerate(context[:4]):
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if not isinstance(metadata, dict):
                continue
            abstract = str(metadata.get("abstract") or "")
            for sentence in self._split_sentences(abstract):
                sentence_tokens = set(self._tokenize(sentence))
                if not sentence_tokens:
                    continue
                overlap = len(query_tokens & sentence_tokens)
                score = float(overlap * 3)
                score += max(0.0, 2.0 - (rank * 0.35))
                if any(marker in sentence.lower() for marker in self.METHOD_SENTENCE_MARKERS):
                    score += 1.25
                scored_sentences.append({"sentence": sentence, "score": score, "rank": rank})

        if not scored_sentences:
            lead_meta = context[0].get("metadata", {}) if context else {}
            if isinstance(lead_meta, dict):
                return str(lead_meta.get("abstract") or "")[:700].strip()
            return ""

        scored_sentences.sort(key=lambda item: (float(item["score"]), -int(item["rank"])), reverse=True)
        summary_sentences: List[str] = []
        for item in scored_sentences:
            sentence = str(item["sentence"]).strip()
            if not sentence or sentence in summary_sentences:
                continue
            summary_sentences.append(sentence)
            if len(summary_sentences) >= max_sentences:
                break

        return " ".join(summary_sentences)

    def _extract_key_concepts(self, query: str, context: List[Dict[str, object]], limit: int = 8) -> List[Dict[str, object]]:
        counter: Counter[str] = Counter()
        for weight, text in [(3, query)]:
            for token in self._query_tokens(text):
                if token in self.GENERIC_CONCEPT_TOKENS:
                    continue
                counter[token] += weight

        for rank, item in enumerate(context[:5]):
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if not isinstance(metadata, dict):
                continue
            title = str(metadata.get("title") or "")
            abstract = str(metadata.get("abstract") or "")
            text = f"{title} {abstract[:900]}"
            weight = max(1, 5 - rank)
            for token in self._tokenize(text):
                if token in self.STOP_TOKENS or token in self.GENERIC_CONCEPT_TOKENS:
                    continue
                counter[token] += weight

            acronyms = re.findall(r"\b[A-Z]{2,}\b", title + " " + abstract)
            for acronym in acronyms[:10]:
                counter[acronym.lower()] += weight + 1

        concepts: List[Dict[str, object]] = []
        for concept, score in counter.most_common(limit):
            label = concept.upper() if concept.isalpha() and len(concept) <= 5 else concept.replace("_", " ")
            concepts.append({"concept": label, "weight": int(score)})
        return concepts

    def _extract_method_signals(self, context: List[Dict[str, object]], limit: int = 4) -> List[str]:
        methods: List[str] = []
        for item in context[:3]:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if not isinstance(metadata, dict):
                continue
            abstract = str(metadata.get("abstract") or "")
            for sentence in self._split_sentences(abstract):
                lowered = sentence.lower()
                if any(marker in lowered for marker in self.METHOD_SENTENCE_MARKERS):
                    cleaned = sentence.strip()
                    if cleaned not in methods:
                        methods.append(cleaned)
                if len(methods) >= limit:
                    return methods
        return methods

    def _category_distribution(self, context: List[Dict[str, object]], limit: int = 6) -> List[Dict[str, object]]:
        counter: Counter[str] = Counter()
        for item in context:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if not isinstance(metadata, dict):
                continue
            categories = str(metadata.get("categories") or "")
            for category in categories.split():
                if category:
                    counter[category] += 1
        return [{"category": name, "count": count} for name, count in counter.most_common(limit)]

    def _timeline_distribution(self, context: List[Dict[str, object]], limit: int = 6) -> List[Dict[str, object]]:
        counter: Counter[str] = Counter()
        for item in context:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if not isinstance(metadata, dict):
                continue
            update_date = str(metadata.get("update_date") or "")
            year = update_date[:4]
            if year.isdigit():
                counter[year] += 1
        timeline = [{"year": year, "count": count} for year, count in sorted(counter.items())]
        return timeline[-limit:]

    def build_topic_analysis(self, query: str, context: List[Dict[str, object]]) -> Dict[str, object]:
        cleaned_topic = (self.clean_search_query(query) or query).strip()
        if not context:
            return {
                "topic": cleaned_topic,
                "paper_count": 0,
                "summary": "No strong paper matches were found in the local CS arXiv subset.",
                "key_concepts": [],
                "methods": [],
                "category_distribution": [],
                "timeline": [],
                "lead_paper": None,
            }

        lead_meta = context[0].get("metadata", {}) if isinstance(context[0], dict) else {}
        lead_paper = None
        if isinstance(lead_meta, dict):
            lead_paper = {
                "title": lead_meta.get("title", ""),
                "authors": lead_meta.get("authors", ""),
                "categories": lead_meta.get("categories", ""),
                "updated": lead_meta.get("update_date", ""),
                "paper_id": lead_meta.get("id", ""),
            }

        return {
            "topic": cleaned_topic,
            "paper_count": len(context),
            "summary": self._extractive_summary(cleaned_topic, context),
            "key_concepts": self._extract_key_concepts(cleaned_topic, context),
            "methods": self._extract_method_signals(context),
            "category_distribution": self._category_distribution(context),
            "timeline": self._timeline_distribution(context),
            "lead_paper": lead_paper,
        }

    def _load_local_generator(self):
        if self._generator_load_attempted:
            return self._generator

        self._generator_load_attempted = True
        model_name = str(getattr(self.config, "LOCAL_LLM_MODEL", "google/flan-t5-small") or "google/flan-t5-small")
        model_name_l = model_name.lower()

        try:
            from transformers import pipeline
        except Exception as exc:
            logger.warning(f"Open-source LLM pipeline unavailable for Task 4: {exc}")
            return None

        if any(marker in model_name_l for marker in ("gpt", "llama", "mistral", "phi", "opt")):
            task_order = ("text-generation", "text2text-generation")
        else:
            task_order = ("text2text-generation", "text-generation")

        for task_name in task_order:
            try:
                self._generator = pipeline(task_name, model=model_name, tokenizer=model_name, device=-1)
                logger.info(f"Loaded Task 4 local generator '{model_name}' using task '{task_name}'")
                return self._generator
            except Exception as exc:
                logger.warning(f"Could not load Task 4 generator '{model_name}' as {task_name}: {exc}")

        self._generator = None
        return None

    def _generate_with_local_llm(self, query: str, analysis: Dict[str, object]) -> Optional[str]:
        generator = self._load_local_generator()
        if generator is None:
            return None

        lead_paper = analysis.get("lead_paper") or {}
        key_concepts = ", ".join(
            [str(item.get("concept")) for item in (analysis.get("key_concepts") or [])[:6] if isinstance(item, dict)]
        )
        methods = " ".join([str(item) for item in (analysis.get("methods") or [])[:2]])
        prompt = (
            "Explain the following research topic in 4 to 6 sentences for a technically literate reader. "
            "Use only the evidence below and mention one limitation or tradeoff.\n\n"
            f"Topic: {analysis.get('topic') or query}\n"
            f"Lead paper: {lead_paper.get('title') or 'Unknown'}\n"
            f"Summary evidence: {analysis.get('summary') or ''}\n"
            f"Key concepts: {key_concepts}\n"
            f"Method evidence: {methods}\n"
        )

        generation_kwargs = {
            "truncation": True,
        }
        tokenizer = getattr(generator, "tokenizer", None)
        eos_token_id = getattr(tokenizer, "eos_token_id", None)
        if eos_token_id is not None:
            generation_kwargs["pad_token_id"] = eos_token_id

        try:
            result = generator(prompt, max_new_tokens=180, **generation_kwargs)
        except TypeError:
            result = generator(prompt, max_length=220, **generation_kwargs)
        except Exception as exc:
            logger.warning(f"Task 4 local generator failed during inference: {exc}")
            return None

        if not result or not isinstance(result, list):
            return None

        generated = str(result[0].get("generated_text", "")).strip()
        if not generated:
            return None
        if generated.startswith(prompt):
            generated = generated[len(prompt):].strip()
        generated = re.sub(r"\s+", " ", generated).strip()
        return generated or None

    def generate_answer(
        self,
        query: str,
        context: Optional[List[Dict[str, object]]] = None,
    ) -> str:
        return self.generate_explanation(query, context or self.retrieve_context(query))

    def generate_explanation(
        self,
        query: str,
        context: List[Dict[str, object]],
        topic: Optional[str] = None,
        analysis: Optional[Dict[str, object]] = None,
    ) -> str:
        cleaned_topic = (topic or self.clean_search_query(query) or query).strip()

        if not context:
            return (
                f"Research summary for '{cleaned_topic}': I could not find a strong paper match in the local subset, "
                "but this topic is typically discussed in terms of core methods, experimental setup, and limitations. "
                "Try asking for a narrower topic, a citation request, or recent work in a specific subfield."
            )

        analysis = analysis or self.build_topic_analysis(cleaned_topic, context)
        lead = context[0]
        meta = lead.get("metadata", {}) if isinstance(lead, dict) else {}
        title = meta.get("title", "") if isinstance(meta, dict) else ""
        abstract = meta.get("abstract", "") if isinstance(meta, dict) else ""
        authors = meta.get("authors", "") if isinstance(meta, dict) else ""
        update_date = meta.get("update_date", "") if isinstance(meta, dict) else ""

        if self.is_followup_meta_command(query):
            lowered = (query or "").lower()
            if "bibtex" in lowered:
                key = "".join(ch for ch in (title or "paper").lower() if ch.isalnum())[:24] or "paper"
                year = (update_date or "0000")[:4]
                paper_id = meta.get("id", "") if isinstance(meta, dict) else ""
                return (
                    "```bibtex\n"
                    f"@article{{{key},\n"
                    f"  title={{ {title or cleaned_topic} }},\n"
                    f"  author={{ {authors or 'Unknown'} }},\n"
                    f"  year={{ {year} }},\n"
                    f"  note={{ arXiv:{paper_id} }}\n"
                    "}\n"
                    "```"
                )

            if "short summary" in lowered:
                return f"Short summary: {str(analysis.get('summary') or abstract[:400]).strip()}"

            if "key contributions" in lowered:
                categories = meta.get("categories", "unknown") if isinstance(meta, dict) else "unknown"
                method_signals = analysis.get("methods") or []
                lines = [
                    f"Key contributions suggested by the lead paper '{title}':",
                    f"- Focuses on {cleaned_topic}.",
                    "- Provides a concrete method and evaluation described in the abstract.",
                    f"- Helps position the topic within categories: {categories}.",
                ]
                if method_signals:
                    lines.append(f"- Method signal: {method_signals[0]}")
                return "\n".join(lines)

            if "limitation" in lowered or "future work" in lowered:
                return (
                    f"Limitations and future work for '{cleaned_topic}' usually include dataset coverage, generalization, "
                    "and comparison against broader baselines. The retrieved local papers suggest reviewing scalability, evaluation breadth, "
                    "and follow-up work published after the lead paper."
                )

        llm_explanation = self._generate_with_local_llm(query, analysis)
        related_titles: List[str] = []
        for item in context[1:4]:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            if isinstance(metadata, dict) and metadata.get("title"):
                related_titles.append(str(metadata["title"]))

        key_concepts = [
            str(item.get("concept"))
            for item in (analysis.get("key_concepts") or [])[:6]
            if isinstance(item, dict) and item.get("concept")
        ]
        method_signals = [str(item) for item in (analysis.get("methods") or [])[:2]]
        summary_text = str(analysis.get("summary") or abstract[:900]).strip()

        lines = [
            f"Research explanation for '{cleaned_topic}':",
            f"A strong local arXiv match is '{title}'" + (f" by {authors}" if authors else "") + ".",
            llm_explanation or summary_text,
        ]
        if method_signals:
            lines.append("Method signals: " + " ".join(method_signals))
        if key_concepts:
            lines.append("Key concepts: " + ", ".join(key_concepts))
        if related_titles:
            lines.append("Related local papers:")
            lines.extend([f"- {item}" for item in related_titles])
        lines.append(
            "Use follow-up prompts like 'Give a short summary', 'List key contributions', 'What are limitations and future work?', or 'Provide a BibTeX citation.'"
        )
        return "\n\n".join([line for line in lines if line])

"""
Task 1: Dynamic Knowledge Base Expansion
Optimized Vector Database Manager
"""

import os
import logging
import json
import pickle
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import threading
import time

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


logger = logging.getLogger(__name__)


class VectorDatabaseManager:
    """
    Optimized vector database manager
    """

    _embedding_model = None
    _update_thread_started = False

    MAX_DOCS = 5000
    STOP_WORDS = {
        "a", "an", "and", "are", "as", "at", "be", "between", "by", "can",
        "difference", "do", "does", "explain", "for", "from", "how", "i", "in",
        "into", "is", "it", "of", "on", "or", "please", "show", "simple", "tell",
        "than", "that", "the", "this", "to", "was", "what", "when", "where", "which",
        "who", "why", "with", "words"
    }

    def __init__(self, config):

        self.config = config
        self.db_path = config.VECTOR_DB_PATH

        self.index = None
        self.documents = []
        self.metadata = []
        self._document_fingerprints = set()
        self._update_lock = threading.Lock()
        self._next_update_at: Optional[str] = None
        self.update_status: Dict[str, Any] = {
            "running": False,
            "last_run": None,
            "last_success": None,
            "last_error": None,
            "last_duration_seconds": None,
            "last_source": None,
            "documents_added": 0,
            "next_run": None,
        }

        # Load embedding model once globally
        self.embedding_model = self._load_embedding_model()

        self._load_or_create_database()
        self._document_fingerprints = {
            self._fingerprint_document(content)
            for content in self.documents
            if str(content or "").strip()
        }
        startup_started_at = datetime.now()
        startup_added = self._ingest_configured_sources(reason="startup")
        startup_finished_at = datetime.now()
        self.update_status.update(
            {
                "last_run": startup_started_at.isoformat(),
                "last_success": startup_finished_at.isoformat(),
                "last_error": None,
                "last_duration_seconds": round(
                    (startup_finished_at - startup_started_at).total_seconds(), 3
                ),
                "last_source": "startup",
                "documents_added": int(startup_added or 0),
            }
        )

        # Start update thread only once
        if not VectorDatabaseManager._update_thread_started:
            self._start_periodic_updates()
            VectorDatabaseManager._update_thread_started = True

        logger.info("Vector Database initialized")

    def _load_embedding_model(self):

        if VectorDatabaseManager._embedding_model is not None:
            return VectorDatabaseManager._embedding_model

        if SentenceTransformer is None:
            logger.warning("SentenceTransformer not available")
            return None

        try:
            logger.info("Loading embedding model (one-time)...")

            VectorDatabaseManager._embedding_model = SentenceTransformer(
                self.config.EMBEDDING_MODEL
            )

        except Exception as e:
            logger.warning(f"Embedding model load failed: {e}")
            VectorDatabaseManager._embedding_model = None

        return VectorDatabaseManager._embedding_model

    def _load_or_create_database(self):

        os.makedirs(self.db_path, exist_ok=True)

        index_path = os.path.join(self.db_path, "faiss_index.bin")
        metadata_path = os.path.join(self.db_path, "metadata.json")
        docs_path = os.path.join(self.db_path, "documents.pkl")

        if os.path.exists(index_path) and faiss:
            try:

                self.index = faiss.read_index(index_path)

                with open(metadata_path, "r") as f:
                    self.metadata = json.load(f)

                with open(docs_path, "rb") as f:
                    self.documents = pickle.load(f)

                if self._index_document_count() != len(self.documents):
                    logger.warning(
                        "Vector index/document count mismatch detected; rebuilding index"
                    )
                    self._rebuild_index()
                    self._save_database()

                logger.info(
                    f"Loaded existing database with {len(self.documents)} documents"
                )

                return

            except Exception as e:
                logger.error(f"Database load failed: {e}")

        self._create_new_database()

    def _create_new_database(self):

        if self.embedding_model:
            dimension = self.embedding_model.get_sentence_embedding_dimension()
        else:
            dimension = 384

        if faiss:
            # Faster FAISS index
            self.index = faiss.IndexHNSWFlat(dimension, 32)
        else:
            logger.warning("FAISS not available, using fallback mode")
            self.index = None

        self.documents = []
        self.metadata = []

        self._save_database()

        logger.info("Created new vector database")

    def _index_document_count(self) -> int:

        if self.index is None:
            return 0
        return int(getattr(self.index, "ntotal", 0))

    def _rebuild_index(self):

        if not self.embedding_model or not faiss:
            return

        dimension = self.embedding_model.get_sentence_embedding_dimension()
        self.index = faiss.IndexHNSWFlat(dimension, 32)

        contents = [str(doc or "").strip() for doc in self.documents if str(doc or "").strip()]
        if not contents:
            return

        embeddings = self.embedding_model.encode(
            contents,
            convert_to_numpy=True,
            batch_size=32,
            show_progress_bar=False,
        )
        self.index.add(embeddings.astype(np.float32))

    def _save_database(self):

        try:

            index_path = os.path.join(self.db_path, "faiss_index.bin")
            metadata_path = os.path.join(self.db_path, "metadata.json")
            docs_path = os.path.join(self.db_path, "documents.pkl")

            if self.index is not None and faiss:
                faiss.write_index(self.index, index_path)

            with open(metadata_path, "w") as f:
                json.dump(self.metadata, f, indent=2)

            with open(docs_path, "wb") as f:
                pickle.dump(self.documents, f)

        except Exception as e:
            logger.error(f"Database save error: {e}")

    def add_documents(self, documents: List[Dict]):

        if not documents:
            return

        unique_documents = []
        for document in documents:
            content = str(document.get("content", "")).strip()
            if not content:
                continue
            fingerprint = self._fingerprint_document(content)
            if fingerprint in self._document_fingerprints:
                continue
            self._document_fingerprints.add(fingerprint)
            unique_documents.append(document)

        documents = unique_documents

        if not documents:
            return

        contents = [
            d.get("content", "").strip()
            for d in documents
            if d.get("content")
        ]

        if not contents:
            return

        try:

            if self.embedding_model and faiss:

                embeddings = self.embedding_model.encode(
                    contents,
                    convert_to_numpy=True,
                    batch_size=32,
                    show_progress_bar=False
                )

                embeddings = embeddings.astype(np.float32)

                self.index.add(embeddings)

        except Exception as e:
            logger.error(f"Embedding error: {e}")

        for doc in documents:

            self.documents.append(doc.get("content", ""))

            self.metadata.append(
                {
                    "id": len(self.documents) - 1,
                    "domain": doc.get("domain", "general"),
                    "timestamp": doc.get(
                        "timestamp",
                        datetime.now().isoformat()
                    ),
                    "source": doc.get("source", "internal"),
                }
            )

        # Limit KB size
        if len(self.documents) > self.MAX_DOCS:

            self.documents = self.documents[-self.MAX_DOCS :]
            self.metadata = self.metadata[-self.MAX_DOCS :]

        # Save less frequently
        self._save_database()

        logger.info(f"Added {len(documents)} documents")

    def _fingerprint_document(self, content: str) -> str:

        normalized = " ".join(str(content or "").split()).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load_configured_source_documents(self) -> List[Dict]:

        source_file = getattr(self.config, "KNOWLEDGE_SOURCE_FILE", "")
        if not source_file:
            return []

        if not os.path.exists(source_file):
            logger.warning(f"Knowledge source file not found: {source_file}")
            return []

        try:
            with open(source_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.error(f"Failed to load knowledge source file: {exc}")
            return []

        if isinstance(payload, dict):
            payload = payload.get("documents", [])

        documents = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            documents.append(
                {
                    "content": content,
                    "domain": item.get("domain", "general"),
                    "source": item.get("source", "configured_source"),
                    "timestamp": item.get("timestamp", datetime.now().isoformat()),
                }
            )

        return documents

    def _ingest_configured_sources(self, reason: str) -> int:

        documents = self._load_configured_source_documents()
        before = len(self.documents)
        self.add_documents(documents)
        added = len(self.documents) - before
        if added:
            logger.info(f"Added {added} configured knowledge documents during {reason}")
            self._save_database()
        return added

    def retrieve(self, query: str, top_k: int = 5):

        if not self.documents:
            return []

        if not self.embedding_model or not faiss:

            logger.warning("Using keyword fallback")

            return self._keyword_search(query, top_k)

        try:

            reranked = self._hybrid_rerank(query, top_k)
            if reranked:
                return reranked

            query_embedding = self.embedding_model.encode(
                [query],
                convert_to_numpy=True
            ).astype(np.float32)

            distances, indices = self.index.search(
                query_embedding,
                min(top_k, len(self.documents))
            )

            results = []

            for i, idx in enumerate(indices[0]):

                if idx < len(self.documents):

                    score = float(1 / (1 + distances[0][i]))

                    results.append(
                        {
                            "content": self.documents[idx],
                            "score": score,
                            "metadata": self.metadata[idx],
                        }
                    )

            return results

        except Exception as e:

            logger.error(f"Retrieve error: {e}")

            return []

    def _hybrid_rerank(self, query: str, top_k: int) -> List[Dict]:

        query_tokens = self._meaningful_tokens(query)
        if not query_tokens:
            return []

        query_embedding = self.embedding_model.encode(
            [query],
            convert_to_numpy=True
        ).astype(np.float32)

        candidate_count = min(max(top_k * 10, 25), len(self.documents))
        distances, indices = self.index.search(query_embedding, candidate_count)

        ranked = []
        for rank_position, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue

            content = self.documents[idx]
            content_tokens = self._meaningful_tokens(content)
            overlap = len(query_tokens & content_tokens)
            phrase_bonus = 2 if any(token in str(content).lower() for token in query_tokens) else 0
            semantic_score = float(1 / (1 + distances[0][rank_position]))

            combined_score = (overlap * 10.0) + phrase_bonus + semantic_score
            if overlap == 0:
                combined_score -= 5.0

            ranked.append(
                {
                    "content": content,
                    "score": combined_score,
                    "metadata": self.metadata[idx],
                    "_overlap": overlap,
                }
            )

        ranked.sort(
            key=lambda item: (item.get("_overlap", 0), float(item.get("score", 0.0))),
            reverse=True,
        )

        filtered = [item for item in ranked if item.get("_overlap", 0) > 0]
        if not filtered:
            return []

        for item in filtered:
            item.pop("_overlap", None)

        return filtered[:top_k]

    def _meaningful_tokens(self, text: str) -> set:

        return {
            token
            for token in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(text or '')).split()
            if len(token) >= 3 and token not in self.STOP_WORDS
        }

    def _keyword_search(self, query: str, top_k: int = 5):

        query = query.lower()

        results = []

        for i, doc in enumerate(self.documents):

            text = doc.lower()

            score = sum(word in text for word in query.split())

            if score > 0:

                results.append(
                    {
                        "content": doc,
                        "score": score,
                        "metadata": self.metadata[i],
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:top_k]

    def get_stats(self):

        return {
            "documents": len(self.documents),
            "index_size": len(self.documents),
            "last_update": (
                self.metadata[-1]["timestamp"]
                if self.metadata
                else "never"
            ),
            "update_status": self.get_update_status(),
        }

    def get_update_status(self) -> Dict[str, Any]:

        status = dict(self.update_status)
        status["next_run"] = self._next_update_at
        return status

    def trigger_update(self, source: str = "manual") -> Dict[str, Any]:

        if self.update_status.get("running"):
            return self.get_update_status()

        thread = threading.Thread(
            target=self._run_update_cycle,
            args=(source,),
            daemon=True,
        )
        thread.start()
        return self.get_update_status()

    def _start_periodic_updates(self):

        thread = threading.Thread(
            target=self._periodic_update_loop,
            daemon=True
        )

        thread.start()

        logger.info("Started update thread")

    def _periodic_update_loop(self):

        while True:

            try:

                interval = self.config.UPDATE_INTERVAL_DAYS * 24 * 3600
                self._next_update_at = (
                    datetime.now() + timedelta(seconds=interval)
                ).isoformat()
                self.update_status["next_run"] = self._next_update_at

                time.sleep(interval)

                logger.info("Running periodic update")

                self._run_update_cycle(source="scheduled")

            except Exception as e:

                logger.error(f"Update loop error: {e}")
                self.update_status["last_error"] = str(e)

    def _run_update_cycle(self, source: str) -> None:

        if not self._update_lock.acquire(blocking=False):
            logger.info("Skipping knowledge-base update because another update is already running")
            return

        started_at = datetime.now()
        self.update_status.update(
            {
                "running": True,
                "last_run": started_at.isoformat(),
                "last_source": source,
                "last_error": None,
                "documents_added": 0,
            }
        )

        try:
            added = 0
            added += self._ingest_configured_sources(reason=source)
            added += self._update_from_arxiv()
            self.update_status["documents_added"] = int(added or 0)
            self.update_status["last_success"] = datetime.now().isoformat()
        except Exception as exc:
            self.update_status["last_error"] = str(exc)
            logger.error(f"Knowledge-base update failed: {exc}")
        finally:
            duration = (datetime.now() - started_at).total_seconds()
            self.update_status["last_duration_seconds"] = round(duration, 3)
            self.update_status["running"] = False
            interval = self.config.UPDATE_INTERVAL_DAYS * 24 * 3600
            self._next_update_at = (
                datetime.now() + timedelta(seconds=interval)
            ).isoformat()
            self.update_status["next_run"] = self._next_update_at
            self._update_lock.release()

    def _update_from_arxiv(self):

        if not self.embedding_model:
            return 0

        try:

            docs = self._fetch_arxiv_documents()

            if docs:
                self.add_documents(docs)

                logger.info(f"Added {len(docs)} arXiv papers")
                return len(docs)

            return 0

        except Exception as e:

            logger.error(f"arXiv update failed: {e}")
            raise

    def _fetch_arxiv_documents(self) -> List[Dict[str, str]]:

        query_params = urllib.parse.urlencode(
            {
                "search_query": "cat:cs.AI",
                "start": 0,
                "max_results": 5,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        endpoint = f"https://export.arxiv.org/api/query?{query_params}"
        request = urllib.request.Request(
            endpoint,
            headers={
                "User-Agent": "ChatBot/1.0 (https://localhost)",
                "Accept": "application/atom+xml",
            },
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()

        root = ET.fromstring(payload)
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
        }

        documents: List[Dict[str, str]] = []
        for entry in root.findall("atom:entry", namespaces):
            title = (entry.findtext("atom:title", default="", namespaces=namespaces) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=namespaces) or "").strip()
            if not title and not summary:
                continue

            documents.append(
                {
                    "content": f"{title}\n{summary}".strip(),
                    "domain": "academic",
                    "source": "arxiv",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return documents
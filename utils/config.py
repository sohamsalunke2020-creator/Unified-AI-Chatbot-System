"""Configuration management for the chatbot system"""

import os
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Configuration class for all settings"""

    def __init__(self):
        # Load environment variables
        env_path = Path(__file__).parent.parent / ".env"
        if not env_path.exists():
            env_path = Path(__file__).parent.parent / ".env.example"
        load_dotenv(env_path)

        # Google AI APIs
        self.GOOGLE_PALM_API_KEY = os.getenv(
            "GOOGLE_PALM_API_KEY", "your_palm_api_key_here"
        )
        self.GOOGLE_GEMINI_API_KEY = os.getenv(
            "GOOGLE_GEMINI_API_KEY", "your_gemini_api_key_here"
        )
        self.GOOGLE_VISION_API_KEY = os.getenv(
            "GOOGLE_VISION_API_KEY", "your_vision_api_key_here"
        )

        # Vector Database
        self.VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "faiss")
        self.VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./data/vector_db")
        self.KNOWLEDGE_SOURCE_FILE = os.getenv(
            "KNOWLEDGE_SOURCE_FILE", "./data/vector_db/knowledge_sources.json"
        )
        self.EMBEDDING_MODEL = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )

        # Data Paths
        self.MEDQUAD_DATA_PATH = os.getenv("MEDQUAD_DATA_PATH", "./data/medquad")
        self.ARXIV_DATA_PATH = os.getenv("ARXIV_DATA_PATH", "./data/arxiv")
        self.ARXIV_CACHE_PATH = os.getenv("ARXIV_CACHE_PATH", "./data/arxiv_cache")
        self.ARXIV_DATASET_PATH = os.getenv("ARXIV_DATASET_PATH", "./data/arxiv_dataset")

        # Language Settings
        self.SUPPORTED_LANGUAGES = os.getenv(
            "SUPPORTED_LANGUAGES", "en,es,fr,zh,ar"
        ).split(",")
        self.DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")

        # Translation (Task 6 / language switching)
        # Disabled by default to avoid heavy `transformers/torch` imports that can
        # destabilize Streamlit sessions on low-memory machines.
        self.ENABLE_TRANSLATION = os.getenv("ENABLE_TRANSLATION", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }

        # Model Settings
        self.SENTIMENT_MODEL = os.getenv(
            "SENTIMENT_MODEL", "distilbert-base-uncased-finetuned-sst-2-english"
        )
        self.LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "google/flan-t5-small")

        # Update Configuration
        self.UPDATE_INTERVAL_DAYS = int(os.getenv("UPDATE_INTERVAL_DAYS", "7"))
        self.BATCH_UPDATE_SIZE = int(os.getenv("BATCH_UPDATE_SIZE", "100"))

        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE", "./logs/chatbot.log")

        # Create necessary directories
        self._create_directories()

    def _create_directories(self):
        """Create necessary directories"""
        directories = [
            self.VECTOR_DB_PATH,
            self.MEDQUAD_DATA_PATH,
            self.ARXIV_DATA_PATH,
            self.ARXIV_CACHE_PATH,
            self.ARXIV_DATASET_PATH,
            os.path.dirname(self.LOG_FILE),
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)


def load_config(config_path: str = ".env") -> Config:
    """Load configuration from file"""
    return Config()

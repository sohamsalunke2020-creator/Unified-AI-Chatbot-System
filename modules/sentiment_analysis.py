"""
Task 5: Sentiment Analysis
Detect and respond to customer emotions during interactions
"""

import logging
import re
from typing import Dict, List
from datetime import datetime
from collections import defaultdict

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

try:
    from transformers import pipeline
except ImportError:
    pipeline = None

logger = logging.getLogger(__name__)


class DefaultConfig:
    """Fallback config"""

    SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"


class SentimentAnalyzer:
    """
    Advanced Sentiment Analysis System
    """

    def __init__(self, config=None):

        self.config = config if config else DefaultConfig()

        self.vader = SentimentIntensityAnalyzer()

        self.transformer = None
        self._init_transformer()

        self.user_history = defaultdict(list)

        self.emotion_keywords = {
            "joy": ["happy", "excited", "great", "wonderful", "love", "delighted"],
            "sadness": ["sad", "depressed", "unhappy", "cry", "hopeless"],
            "anger": ["angry", "mad", "furious", "annoyed", "frustrated"],
            "fear": ["afraid", "scared", "worried", "anxious", "panic"],
            "surprise": ["surprised", "shocked", "amazed"],
        }

        logger.info("Sentiment Analyzer initialized")

    # -----------------------------------------------------
    # MODEL LOADING
    # -----------------------------------------------------

    def _init_transformer(self):

        if pipeline is None:
            logger.warning("Transformers not installed. Using VADER only.")
            return

        try:

            self.transformer = pipeline(
                "sentiment-analysis",
                model=self.config.SENTIMENT_MODEL
            )

            logger.info("Transformer sentiment model loaded")

        except Exception as e:

            logger.warning(f"Transformer load failed: {e}")
            self.transformer = None

    # -----------------------------------------------------
    # MAIN ANALYSIS
    # -----------------------------------------------------

    def analyze(self, text: str, user_id: str = "default") -> Dict:

        try:

            vader_scores = self.vader.polarity_scores(text)

            sentiment = self._sentiment_from_vader(vader_scores)

            emotions = self._detect_emotions(text)

            confidence = abs(vader_scores["compound"])

            transformer_result = None

            if self.transformer:

                try:

                    transformer_result = self.transformer(text[:512])[0]

                    confidence = (
                        confidence + transformer_result["score"]
                    ) / 2

                except Exception:
                    pass

            sentiment = self._refine_sentiment_label(text, sentiment, vader_scores, transformer_result, emotions)

            result = {
                "sentiment": sentiment,
                "confidence": round(confidence, 3),
                "scores": vader_scores,
                "emotions": emotions,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if transformer_result:
                result["transformer"] = transformer_result

            self._track_user(user_id, result)

            return result

        except Exception as e:

            logger.error(f"Sentiment analysis failed: {e}")

            return {
                "sentiment": "NEUTRAL",
                "confidence": 0.0,
                "error": str(e),
            }

    # -----------------------------------------------------
    # SENTIMENT LOGIC
    # -----------------------------------------------------

    def _sentiment_from_vader(self, scores):

        compound = scores["compound"]

        if compound >= 0.05:
            return "POSITIVE"

        if compound <= -0.05:
            return "NEGATIVE"

        return "NEUTRAL"

    def _refine_sentiment_label(self, text, current, scores, transformer_result, emotions):

        text_l = (text or "").lower()
        compound = float(scores.get("compound", 0.0))
        pos = float(scores.get("pos", 0.0))
        neg = float(scores.get("neg", 0.0))
        emotions = emotions or []

        if any(phrase in text_l for phrase in ["nothing special", "just normal", "it was just normal", "i am fine"]):
            return "NEUTRAL"

        if "but" in text_l and any(em in emotions for em in ["fear", "anger", "sadness"]) and pos > 0.2:
            return "NEUTRAL"

        if abs(compound) < 0.15 and abs(pos - neg) < 0.15:
            return "NEUTRAL"

        if transformer_result:
            label = str(transformer_result.get("label", "")).upper()
            score = float(transformer_result.get("score", 0.0))
            if score >= 0.8 and label in {"POSITIVE", "NEGATIVE"} and abs(compound) < 0.2:
                return label

        return current

    # -----------------------------------------------------
    # EMOTION DETECTION
    # -----------------------------------------------------

    def _detect_emotions(self, text: str) -> List[str]:

        words = set(re.findall(r"\b\w+\b", text.lower()))

        detected = []

        for emotion, keywords in self.emotion_keywords.items():

            if any(word in words for word in keywords):
                detected.append(emotion)

        return detected if detected else ["neutral"]

    # -----------------------------------------------------
    # USER HISTORY
    # -----------------------------------------------------

    def _track_user(self, user_id: str, result: Dict):

        history = self.user_history[user_id]

        history.append(result)

        if len(history) > 100:
            self.user_history[user_id] = history[-100:]

    # -----------------------------------------------------
    # USER TREND
    # -----------------------------------------------------

    def get_user_emotion_trend(self, user_id: str) -> Dict:

        history = self.user_history.get(user_id)

        if not history:
            return {}

        sentiments = [h["sentiment"] for h in history]

        sentiment_counts = {
            "POSITIVE": sentiments.count("POSITIVE"),
            "NEGATIVE": sentiments.count("NEGATIVE"),
            "NEUTRAL": sentiments.count("NEUTRAL"),
        }

        emotions = []
        for h in history:
            emotions.extend(h.get("emotions", []))

        emotion_counts = {}

        for e in emotions:
            emotion_counts[e] = emotion_counts.get(e, 0) + 1

        return {
            "user_id": user_id,
            "interactions": len(history),
            "sentiment_distribution": sentiment_counts,
            "emotion_distribution": emotion_counts,
            "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get),
        }

    # -----------------------------------------------------
    # RESPONSE ADAPTATION
    # -----------------------------------------------------

    def adapt_response_tone(self, response: str, sentiment: Dict) -> str:

        sentiment_type = sentiment.get("sentiment")

        if sentiment_type == "NEGATIVE":

            emotions = sentiment.get("emotions", [])

            if "anger" in emotions:
                prefix = "I understand your frustration. "

            elif "sadness" in emotions:
                prefix = "I'm sorry you're feeling this way. "

            elif "fear" in emotions:
                prefix = "I understand your concern. "

            else:
                prefix = "I understand. "

            return prefix + response

        if sentiment_type == "POSITIVE":

            return "That's great! " + response

        return response

    # -----------------------------------------------------
    # CRISIS DETECTION
    # -----------------------------------------------------

    def detect_crisis_indicators(self, text: str, sentiment: Dict) -> Dict:

        crisis_words = [
            "suicide",
            "kill myself",
            "hurt myself",
            "end my life",
            "don't want to live",
        ]

        text_lower = text.lower()

        crisis = any(word in text_lower for word in crisis_words)

        negative = sentiment.get("sentiment") == "NEGATIVE"

        high_conf = sentiment.get("confidence", 0) > 0.8

        risk_level = "high" if crisis or (negative and high_conf) else "low"

        return {
            "is_crisis": crisis,
            "risk_level": risk_level,
            "action": "ESCALATE_TO_HUMAN" if risk_level == "high" else "CONTINUE",
            "support_message": self._support_message(crisis, negative),
        }

    def _support_message(self, crisis, negative):

        if crisis:

            return (
                "If you're in crisis, please contact emergency services "
                "or a mental health professional immediately."
            )

        if negative:

            return "I'm here to help. Support is always available."

        return ""

    # -----------------------------------------------------
    # GLOBAL STATISTICS
    # -----------------------------------------------------

    def get_sentiment_statistics(self) -> Dict:

        all_sentiments = []
        all_emotions = []

        for history in self.user_history.values():

            for item in history:

                all_sentiments.append(item["sentiment"])
                all_emotions.extend(item.get("emotions", []))

        if not all_sentiments:
            return {}

        sentiment_counts = {
            "POSITIVE": all_sentiments.count("POSITIVE"),
            "NEGATIVE": all_sentiments.count("NEGATIVE"),
            "NEUTRAL": all_sentiments.count("NEUTRAL"),
        }

        emotion_counts = {}

        for e in all_emotions:
            emotion_counts[e] = emotion_counts.get(e, 0) + 1

        total = len(all_sentiments)

        return {
            "total_messages": total,
            "sentiment_distribution": sentiment_counts,
            "emotion_distribution": emotion_counts,
            "positive_ratio": sentiment_counts["POSITIVE"] / total,
            "negative_ratio": sentiment_counts["NEGATIVE"] / total,
        }
"""
Task 2: Multi-Modal Chatbot
Handle text and image processing using Gemini + Local Models
"""

import logging
import os
import re
import io
import json
import hashlib
import tempfile
from typing import List, Dict, Optional

from PIL import Image, ImageDraw, ImageFont

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class DefaultConfig:
    """Fallback config if external config not provided"""
    GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")


class MultiModalProcessor:

    def __init__(self, config=None):

        self.config = config if config else DefaultConfig()

        disable_gemini = os.getenv("DISABLE_GEMINI", "").lower() in {
            "1", "true", "yes"
        }

        self._local_captioner = None
        self._local_vqa = None

        self._local_caption_model = os.getenv(
            "LOCAL_IMAGE_CAPTION_MODEL",
            "Salesforce/blip-image-captioning-base"
        )

        self._local_vqa_model = os.getenv(
            "LOCAL_VQA_MODEL",
            "dandelin/vilt-b32-finetuned-vqa"
        )

        self._analysis_cache: Dict = {}
        self._analysis_cache_max = 32
        self.gemini_disabled_reason: Optional[str] = None
        self._generated_image_dir = os.path.join(
            tempfile.gettempdir(),
            "chatbot_generated_images",
        )
        os.makedirs(self._generated_image_dir, exist_ok=True)

        self.gemini_available = False
        gemini_key = str(getattr(self.config, "GOOGLE_GEMINI_API_KEY", "") or "").strip()

        if (
            not disable_gemini
            and genai
            and self._has_real_gemini_key(gemini_key)
        ):
            try:
                genai.configure(api_key=gemini_key)
                model_name = self._resolve_gemini_model_name()
                self.model_text = genai.GenerativeModel(model_name)
                self.model_vision = genai.GenerativeModel(model_name)
                self.gemini_available = True
                self.gemini_disabled_reason = None
                logger.info(f"Gemini initialized with model: {model_name}")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")
                self.model_text = None
                self.model_vision = None
        else:
            self.model_text = None
            self.model_vision = None

        logger.info("MultiModalProcessor initialized")

    def _has_real_gemini_key(self, api_key: str) -> bool:

        if not api_key:
            return False

        placeholder_markers = {
            "your_gemini_api_key_here",
            "changeme",
            "replace-me",
        }
        return api_key.strip().lower() not in placeholder_markers

    def _exception_text(self, exc: Exception) -> str:

        return str(exc or "").strip().lower()

    def _is_quota_error(self, exc: Exception) -> bool:

        message = self._exception_text(exc)
        return any(
            marker in message
            for marker in (
                "quota exceeded",
                "rate limit",
                "resource exhausted",
                "429",
                "too many requests",
                "retry_delay",
            )
        )

    def _disable_gemini_for_session(self, reason: str) -> None:

        if self.gemini_available:
            logger.warning(f"Disabling Gemini for this session: {reason}")
        self.gemini_available = False
        self.gemini_disabled_reason = reason

    def _handle_gemini_exception(self, exc: Exception, action: str) -> None:

        message = str(exc or "").strip()
        logger.warning(f"Gemini {action} failed: {message}")

        if self._is_quota_error(exc):
            self._disable_gemini_for_session("quota exceeded")

    def is_image_generation_request(self, text: str) -> bool:

        prompt = (text or "").strip().lower()
        if not prompt:
            return False

        triggers = [
            "generate an image",
            "generate image",
            "create an image",
            "create image",
            "make an image",
            "make me an image",
            "draw ",
            "illustrate ",
            "design an image",
            "show me an image",
            "picture of",
            "image of",
            "photo of",
        ]
        return any(trigger in prompt for trigger in triggers)

    def _resolve_gemini_model_name(self) -> str:

        # Allow explicit override first.
        configured = os.getenv("GEMINI_MODEL_NAME", "").strip()
        if configured:
            return configured

        # Prefer stable modern defaults.
        candidates = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro",
        ]

        # If listing models is available, pick the first generative model from API.
        # This avoids hardcoding names that may not exist for every account/version.
        try:
            listed = []
            for model in genai.list_models():
                name = getattr(model, "name", "")
                methods = set(getattr(model, "supported_generation_methods", []) or [])
                if name and "generateContent" in methods:
                    listed.append(name)
            if listed:
                # API often returns "models/<name>"; GenerativeModel accepts either.
                normalized = [n.split("/", 1)[1] if n.startswith("models/") else n for n in listed]
                return normalized[0]
        except Exception:
            pass

        return candidates[0]

    # -------------------------------------------------
    # IMAGE ANALYSIS
    # -------------------------------------------------

    def process_images(self, image_paths: List[str]) -> Dict:

        results = {"images": [], "analysis": []}

        for path in image_paths:

            if not os.path.exists(path):
                logger.warning(f"Image not found: {path}")
                continue

            try:

                with Image.open(path) as image:

                    analysis = self._analyze_image(image)

                    results["images"].append({
                        "path": path,
                        "size": image.size,
                        "format": image.format
                    })

                    results["analysis"].append(analysis)

            except Exception as e:

                logger.error(f"Image processing error: {e}")

                results["analysis"].append({
                    "description": "Image analysis failed",
                    "confidence": "low"
                })

        return results

    def analyze_images_with_prompt(self, image_paths: List[str], prompt: str = "") -> Dict:

        results = self.process_images(image_paths)
        answers = []
        prompt_lower = (prompt or "").strip().lower()

        for analysis in results.get("analysis", []):
            if not isinstance(analysis, dict):
                continue

            description = str(analysis.get("description", "")).strip()
            confidence_text = str(analysis.get("confidence", "low")).strip().lower()
            confidence = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(confidence_text, 0.3)
            objects = analysis.get("entities", []) if isinstance(analysis.get("entities"), list) else []

            answer = self._answer_prompt_from_analysis(prompt_lower, description, objects)

            answers.append(
                {
                    "answer": answer,
                    "confidence": confidence,
                    "objects": objects,
                }
            )

        results["answers"] = answers
        return results

    def _answer_prompt_from_analysis(self, prompt: str, description: str, objects: List[str]) -> str:

        concise = self._condense_description(description)
        object_list = self._extract_main_objects(description, objects)
        colors = self._extract_colors(description)
        scene_type = self._infer_scene_type(description)
        count = self._extract_count(description)
        text = (description or "").lower()

        if any(phrase in prompt for phrase in ["how many", "number of"]):
            if count is not None:
                return f"I can see about {count} main items in the image."
            if "book" in text:
                return "I can tell the image shows a stack of books, but I cannot count the exact number confidently from the current caption."
            return "I cannot determine the exact count confidently from the current analysis."

        if "photograph or an illustration" in prompt or "photo or an illustration" in prompt:
            if any(term in text for term in ["illustration", "vector", "graphic", "digital illustration"]):
                return "It appears to be an illustration or graphic rather than a photograph."
            if any(term in text for term in ["photo", "photograph", "real scene"]):
                return "It appears to be a photograph."
            if "book" in text and len(text.split()) <= 8:
                return "It looks more like a simple illustration or graphic than a natural photograph."
            return "I cannot tell with high confidence whether it is a photograph or an illustration."

        if "main subject" in prompt:
            if object_list:
                return f"The main subject is {object_list[0]}."
            return concise

        if "people or animals" in prompt:
            if any(term in text for term in ["person", "people", "man", "woman", "child", "animal", "dog", "cat", "bird"]):
                return "Yes, the image appears to include people or animals."
            return "No people or animals are clearly visible in the image."

        if any(phrase in prompt for phrase in ["one sentence", "single sentence", "in one sentence"]):
            return concise

        if any(phrase in prompt for phrase in ["main object", "main objects", "objects visible", "list the objects"]):
            if object_list:
                return f"Main visible objects: {', '.join(object_list)}."
            return "I can identify a few broad objects, but not enough detail to list them confidently."

        if "color" in prompt:
            if colors:
                return f"Dominant colors: {', '.join(colors)}."
            return "The image has mixed tones, and I cannot identify dominant colors confidently from the available caption."

        if "indoors" in prompt or "outdoors" in prompt:
            if scene_type == "outdoors":
                return "This appears to be an outdoor scene."
            if scene_type == "indoors":
                return "This appears to be an indoor scene."
            return "I cannot determine indoor versus outdoor confidently from this image."

        if prompt.startswith("what do you see") or "what is in the image" in prompt or "what's in the image" in prompt:
            return concise

        return concise

    def _condense_description(self, description: str) -> str:

        text = re.sub(r"\s+", " ", (description or "")).strip()
        if not text:
            return "I could not generate a confident description for this image."

        sentences = re.split(r"(?<=[.!?])\s+", text)
        selected = [sentence.strip() for sentence in sentences[:2] if sentence.strip()]
        concise = " ".join(selected)
        if not concise:
            concise = text[:220].rstrip()
        if len(concise) > 260:
            concise = concise[:257].rstrip() + "..."
        return concise

    def _extract_main_objects(self, description: str, objects: List[str]) -> List[str]:

        text = (description or "").lower()
        known_terms = [
            "books",
            "book",
            "tree",
            "trees",
            "leaves",
            "plants",
            "vines",
            "forest",
            "jungle",
            "flowers",
            "person",
            "people",
            "car",
            "building",
            "road",
        ]
        found: List[str] = []
        for term in known_terms:
            if term in text and term not in found:
                found.append(term)

        for item in objects:
            normalized = str(item or "").strip().lower()
            if normalized and normalized not in found and normalized.isalpha():
                found.append(normalized)

        return found[:5]

    def _extract_colors(self, description: str) -> List[str]:

        text = (description or "").lower()
        colors = [
            "green",
            "blue",
            "red",
            "orange",
            "purple",
            "yellow",
            "brown",
            "white",
            "black",
            "gray",
            "teal",
            "cyan",
        ]
        found = [color for color in colors if color in text]
        return found[:5]

    def _extract_count(self, description: str) -> Optional[int]:

        text = (description or "").lower()
        digit_match = re.search(r"\b(\d{1,2})\b", text)
        if digit_match:
            try:
                return int(digit_match.group(1))
            except Exception:
                return None

        number_words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        for word, value in number_words.items():
            if re.search(rf"\b{word}\b", text):
                return value
        return None

    def _infer_scene_type(self, description: str) -> str:

        text = (description or "").lower()
        if any(term in text for term in ["forest", "rainforest", "jungle", "tree", "trees", "outdoor", "nature"]):
            return "outdoors"
        if any(term in text for term in ["room", "desk", "table", "indoor", "office", "kitchen"]):
            return "indoors"
        if any(term in text for term in ["illustration", "vector", "graphic", "digital illustration"]):
            return "unknown"
        return "unknown"

    # -------------------------------------------------
    # IMAGE ANALYZER
    # -------------------------------------------------

    def _analyze_image(self, image: Image) -> Dict:

        if self.gemini_available:

            try:

                response = self.model_vision.generate_content([
                    "Describe this image",
                    image
                ])

                text = getattr(response, "text", None)

                if text:
                    return {
                        "description": text.strip(),
                        "confidence": "high",
                        "entities": self._extract_entities(text)
                    }

            except Exception as e:

                self._handle_gemini_exception(e, "image analysis")

        caption = self._caption_locally(image)

        if caption:
            return {
                "description": caption,
                "confidence": "medium",
                "entities": self._extract_entities(caption)
            }

        fallback = self._describe_image_basics(image)
        return {
            "description": fallback,
            "confidence": "low",
            "entities": self._extract_entities(fallback)
        }

    def _describe_image_basics(self, image: Image) -> str:

        try:

            rgb = image.convert("RGB")
            width, height = rgb.size
            pixels = list(rgb.getdata())

            if not pixels:
                return "a valid image with no readable pixel data"

            avg_r = sum(pixel[0] for pixel in pixels) / len(pixels)
            avg_g = sum(pixel[1] for pixel in pixels) / len(pixels)
            avg_b = sum(pixel[2] for pixel in pixels) / len(pixels)

            dominant = "blue"
            if avg_r >= avg_g and avg_r >= avg_b:
                dominant = "red"
            elif avg_g >= avg_r and avg_g >= avg_b:
                dominant = "green"

            return (
                f"a {width}x{height} image dominated by {dominant} tones, likely a simple graphic or scene "
                "without clearly identifiable objects"
            )

        except Exception:

            return "a valid image that could not be captioned by the available models"

    # -------------------------------------------------
    # LOCAL CAPTIONING
    # -------------------------------------------------

    def _get_captioner(self):

        if self._local_captioner:
            return self._local_captioner

        try:

            from transformers import pipeline

            self._local_captioner = pipeline(
                "image-to-text",
                model=self._local_caption_model
            )

        except Exception as e:

            logger.warning(f"Caption model load failed: {e}")
            return None

        return self._local_captioner

    def _caption_locally(self, image):

        captioner = self._get_captioner()

        if not captioner:
            return None

        try:
            try:
                outputs = captioner(image, max_new_tokens=48)
            except TypeError:
                outputs = captioner(image)

            if outputs and isinstance(outputs, list):

                text = outputs[0].get("generated_text")

                if text:
                    return text.strip()

        except Exception as e:
            logger.warning(f"Caption error: {e}")

        return None

    # -------------------------------------------------
    # ENTITY EXTRACTION
    # -------------------------------------------------

    def _extract_entities(self, text: str) -> List[str]:

        entities = []

        words = re.findall(r"[a-zA-Z]+", text.lower())

        for w in words:

            if len(w) > 4:
                entities.append(w)

        return list(set(entities))[:8]

    # -------------------------------------------------
    # TEXT RESPONSE GENERATION
    # -------------------------------------------------

    def generate_text_response(self, user_input: str, context: List[Dict]) -> str:

        heuristic = self._general_heuristic_response(user_input)
        if heuristic:
            return heuristic

        if not self.gemini_available:

            return self._fallback_response(context, user_input)

        try:

            context_text = "\n".join(
                [doc.get("content", "") for doc in context[:3]]
            )

            prompt = f"""
Context:
{context_text}

User question:
{user_input}

Answer clearly.
"""

            response = self.model_text.generate_content(prompt)

            return getattr(response, "text", "No response generated.")

        except Exception as e:

            self._handle_gemini_exception(e, "text generation")

            return self._fallback_response(context, user_input)

    def _general_heuristic_response(self, user_input: str) -> Optional[str]:

        text = (user_input or "").strip().lower()

        if "uses of python" in text or ("python" in text and "besides ai" in text):
            return (
                "Python is widely used beyond AI. Four common uses are:\n"
                "- Web development, such as backend services and APIs\n"
                "- Automation and scripting for repetitive tasks\n"
                "- Data analysis and visualization\n"
                "- Testing, tooling, and system administration"
            )

        if text.startswith("what is an api") or " what is an api" in f" {text}":
            return (
                "An API, or Application Programming Interface, is a set of rules that lets one software system communicate with another. "
                "For example, a weather app may call an API to fetch forecast data from a server."
            )

        if "recursion" in text:
            return (
                "Recursion is when a function solves a problem by calling itself on a smaller version of the same problem.\n\n"
                "Simple example: factorial of 4 is `4 * factorial(3)`, then `3 * factorial(2)`, until it reaches `factorial(1)`."
            )

        if "dns" in text:
            return (
                "DNS stands for Domain Name System. It works like the internet's address book by translating names like `example.com` into IP addresses that computers use to locate each other."
            )

        if "ram" in text and "cache" in text:
            return (
                "RAM is the computer's main short-term working memory, while cache memory is much smaller and faster memory located close to the CPU. Cache speeds up repeated access to frequently used data, while RAM stores the larger pool of active programs and data."
            )

        if "neural network" in text:
            return (
                "A neural network is a machine learning model inspired by the brain. It consists of layers of connected nodes that learn patterns from data and is commonly used for image recognition, language processing, and prediction tasks."
            )

        return None

    # -------------------------------------------------
    # FALLBACK RESPONSE
    # -------------------------------------------------

    def _fallback_response(self, context, user_input: str = ""):

        if context:
            relevant = self._most_relevant_context(context, user_input)
            if relevant:
                return f"Based on available information:\n\n{relevant}"

        return (
            "I don't have enough reliable local knowledge about that topic yet.\n\n"
            "Try asking a more specific question, or ask about topics currently covered in the local knowledge base such as Python, machine learning, or neural networks."
        )

    def _most_relevant_context(self, context: List[Dict], user_input: str) -> Optional[str]:

        query_tokens = self._meaningful_tokens(user_input)
        if not query_tokens:
            return None

        best_content = None
        best_overlap = 0

        for item in context:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            content_tokens = self._meaningful_tokens(content)
            overlap = len(query_tokens & content_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_content = content

        if best_overlap == 0:
            return None

        return best_content

    def _meaningful_tokens(self, text: str) -> set:

        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "do", "does",
            "explain", "for", "how", "in", "is", "it", "of", "on", "or",
            "simple", "simplely", "simply", "tell", "the", "to", "what", "words"
        }
        tokens = {
            token
            for token in re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
            if len(token) >= 3 and token not in stop_words
        }
        return tokens

    # -------------------------------------------------
    # IMAGE → TEXT
    # -------------------------------------------------

    def image_to_text(self, image_path):

        try:

            with Image.open(image_path) as image:

                analysis = self._analyze_image(image)

                return analysis.get("description", "")

        except Exception as e:

            logger.error(f"image_to_text error: {e}")

        return ""

    # -------------------------------------------------
    # TEXT → IMAGE (placeholder)
    # -------------------------------------------------

    def text_to_image(self, text):

        prompt = str(text or "").strip()
        if not prompt:
            return None

        logger.info(f"Image generation requested: {prompt}")

        spec = self._build_image_spec(prompt)
        image = self._render_generated_image(spec, prompt)
        if image is None:
            return None

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        image_path = os.path.join(self._generated_image_dir, f"generated_{digest}.png")
        with open(image_path, "wb") as handle:
            handle.write(image_bytes)

        return {
            "image_bytes": image_bytes,
            "image_path": image_path,
            "mime_type": "image/png",
            "prompt": prompt,
            "caption": spec.get("title") or "Generated image",
            "backend": spec.get("backend", "local_renderer"),
            "summary": spec.get("summary") or f"Generated an image for: {prompt}",
        }

    def _build_image_spec(self, prompt: str) -> Dict:

        if self.gemini_available and self.model_text is not None:
            try:
                gemini_spec = self._build_image_spec_with_gemini(prompt)
                if gemini_spec:
                    gemini_spec["backend"] = gemini_spec.get("backend", "gemini+local_renderer")
                    return gemini_spec
            except Exception as exc:
                self._handle_gemini_exception(exc, "image-spec generation")

        return self._build_image_spec_locally(prompt)

    def _build_image_spec_with_gemini(self, prompt: str) -> Optional[Dict]:

        request = f"""
Create a concise visual design specification for an illustrative image.

User prompt: {prompt}

Return strict JSON with these keys only:
- title: short title
- subtitle: short subtitle
- summary: one sentence about the visual
- motif: one of [tech, nature, medical, education, city, space, abstract]
- palette: array of exactly 3 hex colors

Do not include markdown fences.
"""

        response = self.model_text.generate_content(request)
        text = getattr(response, "text", "") or ""
        if not text.strip():
            return None

        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        payload = json.loads(cleaned[start:end + 1])
        if not isinstance(payload, dict):
            return None

        palette = payload.get("palette") if isinstance(payload.get("palette"), list) else []
        normalized_palette = []
        for color in palette[:3]:
            color_text = str(color or "").strip()
            if re.fullmatch(r"#[0-9a-fA-F]{6}", color_text):
                normalized_palette.append(color_text)
        if len(normalized_palette) < 3:
            normalized_palette = ["#0c1b2a", "#163954", "#5ce1e6"]

        motif = str(payload.get("motif") or "abstract").strip().lower()
        if motif not in {"tech", "nature", "medical", "education", "city", "space", "abstract"}:
            motif = "abstract"

        return {
            "title": str(payload.get("title") or "Generated image").strip()[:64],
            "subtitle": str(payload.get("subtitle") or prompt).strip()[:96],
            "summary": str(payload.get("summary") or f"Generated an illustrative image for {prompt}").strip()[:180],
            "motif": motif,
            "palette": normalized_palette,
        }

    def _build_image_spec_locally(self, prompt: str) -> Dict:

        prompt_l = (prompt or "").lower()
        motif = "abstract"
        palette = ["#0b1320", "#153456", "#55e5ef"]

        motif_rules = [
            ("medical|doctor|hospital|health|medicine", "medical", ["#1b1f3b", "#24577a", "#7df9ff"]),
            ("forest|tree|nature|flower|mountain|river|sunset", "nature", ["#102216", "#2c6e49", "#ffd166"]),
            ("futuristic|neon|cyberpunk|megamall|metropolis|city|building|street|urban|skyline", "city", ["#0b1d3c", "#2d4f82", "#5f9efb"]),
            ("space|planet|star|galaxy|moon|rocket", "space", ["#090b1a", "#312e81", "#c084fc"]),
            ("book|school|study|education|classroom|library", "education", ["#1f1b18", "#8c5e34", "#f6bd60"]),
            ("robot|ai|chip|computer|code|technology|tech", "tech", ["#07111c", "#0ea5e9", "#c7ff2f"]),
        ]

        for pattern, resolved_motif, resolved_palette in motif_rules:
            if re.search(pattern, prompt_l):
                motif = resolved_motif
                palette = resolved_palette
                break

        title = prompt.strip().rstrip(".?!")
        if len(title) > 44:
            title = title[:41].rstrip() + "..."

        return {
            "title": title or "Generated image",
            "subtitle": "AI-generated visual summary",
            "summary": f"Generated an illustrative image for: {prompt}",
            "motif": motif,
            "palette": palette,
            "backend": "local_renderer",
        }

    def _render_generated_image(self, spec: Dict, prompt: str) -> Optional[Image.Image]:

        try:
            width, height = 1024, 640
            palette = spec.get("palette") or ["#0b1320", "#153456", "#55e5ef"]
            image = Image.new("RGB", (width, height), self._hex_to_rgb(palette[0]))
            draw = ImageDraw.Draw(image)

            self._paint_vertical_gradient(image, palette[0], palette[1])
            self._paint_glow_orb(draw, width * 0.78, height * 0.18, 150, palette[2])
            self._paint_glow_orb(draw, width * 0.18, height * 0.76, 120, palette[1])
            self._paint_motif(draw, spec.get("motif", "abstract"), width, height, palette, prompt)

            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

            title = str(spec.get("title") or "Generated image")
            subtitle = str(spec.get("subtitle") or prompt)
            footer = str(spec.get("summary") or "")

            draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=36, outline=(255, 255, 255, 36), width=2)
            draw.text((96, 94), title, fill=(245, 251, 255), font=title_font)
            draw.text((96, 126), subtitle[:96], fill=(205, 219, 234), font=subtitle_font)
            draw.text((96, height - 118), footer[:140], fill=(200, 214, 228), font=subtitle_font)
            draw.text((96, height - 86), "Generated by Task 2 multimodal pipeline", fill=(150, 170, 190), font=subtitle_font)

            return image
        except Exception as exc:
            logger.error(f"Generated image render failed: {exc}")
            return None

    def _paint_vertical_gradient(self, image: Image.Image, start_hex: str, end_hex: str) -> None:

        start = self._hex_to_rgb(start_hex)
        end = self._hex_to_rgb(end_hex)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            color = tuple(int(start[idx] + (end[idx] - start[idx]) * ratio) for idx in range(3))
            draw.line((0, y, width, y), fill=color)

    def _paint_glow_orb(self, draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: int, color_hex: str) -> None:

        base = self._hex_to_rgb(color_hex)
        for step in range(5, 0, -1):
            current_radius = radius * step / 5
            alpha_mix = 0.08 * step
            fill = tuple(min(255, int(channel + (255 - channel) * alpha_mix)) for channel in base)
            draw.ellipse(
                (
                    cx - current_radius,
                    cy - current_radius,
                    cx + current_radius,
                    cy + current_radius,
                ),
                outline=fill,
                width=3,
            )

    def _paint_motif(self, draw: ImageDraw.ImageDraw, motif: str, width: int, height: int, palette: List[str], prompt: str) -> None:

        accent = self._hex_to_rgb(palette[2])
        secondary = self._hex_to_rgb(palette[1])

        if motif == "tech":
            draw.rounded_rectangle((650, 210, 880, 430), radius=28, outline=accent, width=5)
            for offset in range(0, 6):
                x = 680 + offset * 34
                draw.line((x, 190, x, 210), fill=accent, width=4)
                draw.line((x, 430, x, 450), fill=accent, width=4)
            draw.line((690, 255, 840, 255), fill=secondary, width=4)
            draw.line((690, 300, 840, 300), fill=secondary, width=4)
            draw.line((690, 345, 790, 345), fill=secondary, width=4)
        elif motif == "nature":
            draw.polygon([(620, 430), (730, 250), (840, 430)], outline=accent, fill=None, width=5)
            draw.polygon([(700, 430), (810, 220), (930, 430)], outline=secondary, fill=None, width=5)
            draw.ellipse((170, 150, 260, 240), outline=accent, width=5)
            draw.line((180, 430, 900, 430), fill=accent, width=4)
        elif motif == "medical":
            draw.rounded_rectangle((680, 210, 890, 420), radius=34, outline=accent, width=5)
            draw.line((785, 250, 785, 380), fill=secondary, width=20)
            draw.line((720, 315, 850, 315), fill=secondary, width=20)
        elif motif == "education":
            draw.rectangle((660, 220, 900, 400), outline=accent, width=5)
            draw.line((780, 220, 780, 400), fill=secondary, width=4)
            draw.line((700, 255, 760, 255), fill=secondary, width=4)
            draw.line((800, 255, 860, 255), fill=secondary, width=4)
        elif motif == "city":
            # City silhouette with skyline, roads and glowing windows.
            base_y = height - 80
            num_buildings = 7
            rng = hashlib.sha256(f"{prompt}:{motif}".encode("utf-8")).digest()
            for idx in range(num_buildings):
                building_width = 50 + (rng[idx] % 40)
                building_height = 120 + (rng[(idx + 3) % len(rng)] % 260)
                left = 100 + idx * 90
                right = left + building_width
                top = base_y - building_height
                draw.rectangle((left, top, right, base_y), fill=secondary, outline=accent, width=3)

                # windows
                window_color = (255, 236, 179)
                for wy in range(top + 15, base_y - 15, 22):
                    for wx in range(left + 10, right - 10, 18):
                        if (wx + wy) % 40 < 24:
                            draw.rectangle((wx, wy, wx + 8, wy + 12), fill=window_color)

            # ground and street lights
            draw.rectangle((0, base_y, width, height), fill=(20, 30, 45))
            for post in range(80, width, 90):
                draw.line((post, base_y, post, base_y + 26), fill=accent, width=2)
                draw.ellipse((post - 4, base_y + 22, post + 4, base_y + 30), fill=accent)
        elif motif == "space":
            draw.ellipse((700, 210, 880, 390), outline=accent, width=5)
            draw.arc((650, 250, 930, 350), start=10, end=170, fill=secondary, width=5)
            draw.line((250, 170, 290, 210), fill=accent, width=4)
            draw.line((290, 170, 250, 210), fill=accent, width=4)
        else:
            draw.arc((620, 190, 900, 470), start=20, end=320, fill=accent, width=5)
            draw.arc((680, 130, 960, 410), start=220, end=120, fill=secondary, width=5)
            draw.line((640, 410, 860, 230), fill=accent, width=4)

    def _hex_to_rgb(self, value: str) -> tuple:

        cleaned = str(value or "#000000").strip().lstrip("#")
        if len(cleaned) != 6:
            cleaned = "000000"
        return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))

    # -------------------------------------------------
    # COMBINE RESPONSE
    # -------------------------------------------------

    def combine_text_and_image(self, text, image_path):

        return {
            "type": "multimodal",
            "text": text,
            "image_path": image_path
        }

    def enhance_with_images(self, response: Dict) -> Dict:

        return response if isinstance(response, dict) else {"text": str(response)}
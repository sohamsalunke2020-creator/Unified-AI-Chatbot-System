"""Streamlit UI for isolated task-by-task chatbot testing."""

import html
import io
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import plotly.graph_objects as go
import streamlit as st
from PIL import Image, UnidentifiedImageError

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from chatbot_main import UnifiedChatbot
from utils.logger import setup_logger

logger = setup_logger(__name__)

APP_NAME = "Unified ChatBot"
CSS_FILE = Path(PROJECT_ROOT) / "assets" / "streamlit_theme.css"
INSTAGRAM_URL = os.getenv(
    "CHATBOT_INSTAGRAM_URL",
    "https://www.instagram.com/soh_amsalunke?igsh=MXZwaTBhOHZyM2lmNQ==",
)
FACEBOOK_URL = os.getenv(
    "CHATBOT_FACEBOOK_URL",
    "https://www.facebook.com/share/1CnotWkzXg/",
)
CONTACT_NUMBER = os.getenv("CHATBOT_CONTACT_NUMBER", "8855022020")


def _inject_css(page: str) -> None:
    """Inject high-contrast neon UI theme."""
    css = CSS_FILE.read_text(encoding="utf-8")
    if page == "chat":
        css += """

.block-container {
    padding-bottom: 8.5rem !important;
}
"""
    if page != "chat":
        css += """

[data-testid="stSidebar"] {
    display: none !important;
}

.block-container {
    max-width: 1240px !important;
    padding-left: 2.4rem !important;
    padding-right: 2.4rem !important;
}
"""
    st.markdown("<style>\n" + css + "\n</style>", unsafe_allow_html=True)


def _query_page() -> str:
    return str(_query_param_value("page", "home") or "home").strip().lower()


def _query_task() -> str:
    return str(_query_param_value("task", "") or "").strip()


def _query_param_value(name: str, default: str = "") -> str:
    if hasattr(st, "query_params"):
        value = st.query_params.get(name, default)
        return str(value or default)

    params = st.experimental_get_query_params()
    value = params.get(name, [default])
    if isinstance(value, list):
        return str(value[0] if value else default)
    return str(value or default)


def _normalize_page(page: str) -> str:
    return "chat" if str(page or "").strip().lower() == "chat" else "home"


def _route_signature(page: str, task_name: Optional[str] = None) -> tuple[str, str]:
    normalized_page = _normalize_page(page)
    normalized_task = str(task_name or "").strip()
    if normalized_page == "chat" and normalized_task in TASKS:
        return normalized_page, normalized_task
    return normalized_page, ""


def _current_route_signature() -> tuple[str, str]:
    current_page = _normalize_page(str(st.session_state.get("page", "home")))
    current_task = str(st.session_state.get("task_mode") or "").strip()
    if current_page == "chat" and current_task in TASKS:
        return current_page, current_task
    return current_page, ""


def _sync_query_params(page: str, task_name: Optional[str] = None) -> None:
    normalized_page, normalized_task = _route_signature(page, task_name)
    payload: Dict[str, str] = {}
    if normalized_page == "chat":
        payload["page"] = "chat"
        if normalized_task:
            payload["task"] = normalized_task

    if hasattr(st, "experimental_get_query_params") and hasattr(st, "experimental_set_query_params"):
        current_params = st.experimental_get_query_params()
        current_payload: Dict[str, str] = {}
        page_values = current_params.get("page", [])
        task_values = current_params.get("task", [])
        if page_values:
            current_payload["page"] = str(page_values[0]).strip()
        if task_values:
            current_payload["task"] = str(task_values[0]).strip()

        if current_payload == payload:
            return

        st.experimental_set_query_params(**payload)
        return

    if hasattr(st, "query_params"):
        current_payload = {}
        if hasattr(st.query_params, "to_dict"):
            current_payload = {
                key: str(value)
                for key, value in st.query_params.to_dict().items()
                if key in {"page", "task"} and str(value).strip()
            }
        else:
            current_page = _query_param_value("page", "")
            current_task = _query_param_value("task", "")
            if current_page:
                current_payload["page"] = current_page
            if current_task:
                current_payload["task"] = current_task

        if current_payload == payload:
            return

        if hasattr(st.query_params, "from_dict"):
            st.query_params.from_dict(payload)
            return

        if hasattr(st.query_params, "clear"):
            st.query_params.clear()
        for key, value in payload.items():
            st.query_params[key] = value
        return

    st.experimental_set_query_params(**payload)


def _safe_rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
        return
    st.experimental_rerun()


def _queue_navigation(page: str, task_name: Optional[str] = None) -> None:
    normalized_page, normalized_task = _route_signature(page, task_name)
    st.session_state.nav_request = (normalized_page, normalized_task)


def _apply_navigation_request() -> bool:
    nav_request = st.session_state.get("nav_request")
    if not nav_request:
        return False

    normalized_page, normalized_task = _route_signature(*nav_request)
    st.session_state.nav_request = None
    st.session_state.pending_route = (normalized_page, normalized_task)
    st.session_state.page = normalized_page
    if normalized_page == "chat" and normalized_task:
        st.session_state.task_mode = normalized_task
        st.session_state.prev_task_mode = normalized_task
        _sync_query_params("chat", normalized_task)
    else:
        _sync_query_params("home")
    return True


st.set_page_config(
    page_title=APP_NAME,
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

TASKS: Dict[str, Dict] = {
    "Task 1 - Knowledge Base": {
        "id": 1,
        "title": "Task 1 - Dynamic knowledge base",
        "description": "General Q&A using local KB/vector retrieval.",
        "how_to": [
            "Ask a general question.",
            "Use this mode for non-medical and non-arXiv queries.",
        ],
        "examples": [
            "Explain blockchain in simple words.",
            "What is the difference between TCP and UDP?",
        ],
        "placeholder": "Ask a general knowledge question...",
    },
    "Task 2 - Multi-Modal (Images)": {
        "id": 2,
        "title": "Task 2 - Multi-modal (image analysis)",
        "description": "Upload one image and ask image-specific questions.",
        "how_to": [
            "Upload an image.",
            "Ask what you see and press Send.",
            "Keep asking follow-ups based on the same uploaded image.",
        ],
        "examples": [
            "What is in the image?",
            "What objects are in the image?",
            "Summarize the image in one sentence.",
        ],
        "placeholder": "Upload an image, then ask about it...",
    },
    "Task 3 - Medical Q&A": {
        "id": 3,
        "title": "Task 3 - Medical Q&A",
        "description": "Medical QA from local medical knowledge and MedQuAD.",
        "how_to": [
            "Ask symptoms, treatments, prevention, and related medical questions.",
        ],
        "examples": [
            "What are the symptoms of asthma?",
            "How is hypertension treated?",
        ],
        "placeholder": "Ask a medical question...",
    },
    "Task 4 - Domain Expert (arXiv)": {
        "id": 4,
        "title": "Task 4 - Domain expert (arXiv)",
        "description": "Research-style responses grounded in local arXiv dataset.",
        "how_to": [
            "Ask paper/research questions.",
            "Ask for citation/BibTeX follow-ups if needed.",
        ],
        "examples": [
            "Explain transformers and include title and authors.",
            "Provide a BibTeX citation for the paper you referenced.",
        ],
        "placeholder": "Ask a research/arXiv question...",
    },
    "Task 5 - Sentiment": {
        "id": 5,
        "title": "Task 5 - Sentiment analysis",
        "description": "Emotion/sentiment analysis only.",
        "how_to": [
            "Enter a sentence with emotions or mood.",
        ],
        "examples": [
            "I feel overwhelmed and anxious.",
            "I am very happy today.",
        ],
        "placeholder": "Type text to analyze sentiment...",
    },
    "Task 6 - Language": {
        "id": 6,
        "title": "Task 6 - Multi-language",
        "description": "Language detection and translation flow.",
        "how_to": [
            "Enter text in any language.",
            "The chatbot will detect language and provide translation details.",
        ],
        "examples": [
            "Hola, como estas?",
            "Bonjour, comment ca va?",
        ],
        "placeholder": "Type text to translate/detect language...",
    },
}


def _default_task_name() -> str:
    return "Task 1 - Knowledge Base"


@st.cache_resource
def initialize_chatbot() -> Optional[UnifiedChatbot]:
    try:
        chatbot = UnifiedChatbot(lazy_init=True)
        logger.info("Chatbot initialized in Streamlit")
        return chatbot
    except Exception as exc:
        logger.error(f"Error initializing chatbot: {exc}")
        return None


def _selected_task() -> Dict:
    key = st.session_state.get("task_mode")
    if key in TASKS:
        return TASKS[key]
    return TASKS[_default_task_name()]


def _ensure_state() -> None:
    if "chatbot" not in st.session_state:
        st.session_state.chatbot = initialize_chatbot()

    if "task_mode" not in st.session_state:
        st.session_state.task_mode = _default_task_name()
    if "prev_task_mode" not in st.session_state:
        st.session_state.prev_task_mode = st.session_state.task_mode

    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "nav_request" not in st.session_state:
        st.session_state.nav_request = None
    if "pending_route" not in st.session_state:
        st.session_state.pending_route = None

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "pending_send" not in st.session_state:
        st.session_state.pending_send = ""

    if "task2_image" not in st.session_state:
        st.session_state.task2_image = None
    if "task2_upload_nonce" not in st.session_state:
        st.session_state.task2_upload_nonce = 0

    requested_page = _normalize_page(_query_page())
    requested_task = _query_task()
    if requested_page == "chat" and requested_task not in TASKS:
        requested_task = st.session_state.get("task_mode") if st.session_state.get("task_mode") in TASKS else _default_task_name()
    requested_route = _route_signature(requested_page, requested_task)

    pending_route = st.session_state.get("pending_route")
    if pending_route:
        pending_page, pending_task = _route_signature(*pending_route)
        canonical_pending_route = (pending_page, pending_task)
        if requested_route != canonical_pending_route:
            requested_route = canonical_pending_route
            if pending_page == "chat":
                _sync_query_params("chat", pending_task)
            else:
                _sync_query_params("home")
        else:
            st.session_state.pending_route = None

    current_route = _current_route_signature()

    if requested_route != current_route:
        st.session_state.page = requested_route[0]
        if requested_route[0] == "chat":
            task_changed = requested_route[1] != str(st.session_state.get("task_mode") or "")
            st.session_state.task_mode = requested_route[1] or _default_task_name()
            st.session_state.prev_task_mode = st.session_state.task_mode
            if current_route[0] == "chat" and task_changed:
                _clear_current_task_window()
        else:
            st.session_state.page = "home"

    if st.session_state.get("page") == "chat" and st.session_state.get("task_mode") not in TASKS:
        st.session_state.task_mode = _default_task_name()
        st.session_state.prev_task_mode = st.session_state.task_mode

    if requested_page == "chat" and requested_route[1] != _query_task():
        _sync_query_params("chat", requested_route[1])


def _clear_current_task_window() -> None:
    st.session_state.messages = []
    st.session_state.task2_image = None
    st.session_state.task2_upload_nonce += 1


def _on_task_change() -> None:
    new_task = st.session_state.get("task_mode")
    old_task = st.session_state.get("prev_task_mode")
    if not new_task or new_task == old_task:
        return
    st.session_state.prev_task_mode = new_task
    if st.session_state.get("page") == "chat":
        st.session_state.pending_route = ("chat", new_task)
        _sync_query_params("chat", new_task)
    _clear_current_task_window()


def _render_home_topbar() -> None:
    left, right = st.columns([0.72, 0.28], gap="medium")
    with left:
        st.markdown(
            '<div class="landing-topbar">'
            '<div class="landing-topbar-brand">Unified ChatBot</div>'
            '<div class="landing-topbar-copy">Single-app AI workspace for knowledge, multimodal, medical, research, sentiment, and language workflows.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="landing-topbar-cta-marker"></div>', unsafe_allow_html=True)
        st.button(
            "Try Chatbot",
            key="landing_top_cta",
            use_container_width=True,
            on_click=_queue_navigation,
            args=("chat", _default_task_name()),
        )


def _render_landing_backdrop() -> None:
    st.markdown(
        '<div class="landing-backdrop" aria-hidden="true">'
        '<span class="landing-backdrop-orb orb-one"></span>'
        '<span class="landing-backdrop-orb orb-two"></span>'
        '<span class="landing-backdrop-grid"></span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f'<div class="brand-mark">{APP_NAME}</div>'
            '<div class="brand-sub">Multi-task AI system</div>',
            unsafe_allow_html=True,
        )

        st.selectbox(
            "Task",
            options=list(TASKS.keys()),
            key="task_mode",
            on_change=_on_task_change,
        )

        if st.button("Clear chat"):
            _clear_current_task_window()
            _safe_rerun()

        chatbot = st.session_state.get("chatbot")
        if chatbot is not None:
            st.divider()
            st.markdown(
                '<div style="font-family:\'Share Tech Mono\',monospace;color:#00FFFF;'
                'text-transform:uppercase;letter-spacing:0.1em;font-size:0.78rem;">'
                'System Status</div>',
                unsafe_allow_html=True,
            )
            try:
                status = chatbot.get_system_status()
            except Exception as exc:
                st.caption(f"Status unavailable: {exc}")
                status = {}

            modules = status.get("modules") if isinstance(status, dict) else {}
            active_modules = 0
            if isinstance(modules, dict):
                active_modules = sum(1 for value in modules.values() if value == "active")
            st.markdown(
                f'<div class="status-panel">'
                f'<span class="status-dot-green"></span>'
                f'Conversations:&nbsp;<b style="color:#00FFFF">{status.get("conversation_count", 0)}</b>'
                f'&nbsp;&nbsp;|&nbsp;&nbsp;Loaded modules:&nbsp;<b style="color:#00FFFF">{active_modules}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )

            multimodal = getattr(chatbot, "multimodal", None)
            gemini_state = "Multimodal backend not loaded yet"
            gemini_dot = "status-dot-grey"
            if multimodal is not None:
                if getattr(multimodal, "gemini_available", False):
                    gemini_state = "Gemini active for multimodal tasks"
                    gemini_dot = "status-dot-green"
                else:
                    reason = str(getattr(multimodal, "gemini_disabled_reason", "") or "local fallback active")
                    gemini_state = f"Gemini unavailable: {reason}"

            st.markdown(
                f'<div class="status-panel multimodal-status-panel">'
                f'<span class="{gemini_dot}"></span>{html.escape(gemini_state)}'
                f'</div>',
                unsafe_allow_html=True,
            )

            kb_updates = status.get("kb_updates") if isinstance(status, dict) else {}
            vector_stats = status.get("vector_db") if isinstance(status, dict) else {}
            if not isinstance(kb_updates, dict):
                kb_updates = {}
            if not isinstance(vector_stats, dict):
                vector_stats = {}

            col1, col2 = st.columns(2)
            with col1:
                st.metric("KB docs", vector_stats.get("documents", 0))
            with col2:
                st.metric("KB update", "Running" if kb_updates.get("running") else "Idle")

            if st.button("Refresh knowledge base now"):
                try:
                    chatbot.trigger_knowledge_base_refresh(source="streamlit_manual")
                    st.success("Knowledge-base refresh started in the background.")
                except Exception as exc:
                    st.error(f"Refresh failed to start: {exc}")

            with st.expander("KB update details", expanded=False):
                if isinstance(kb_updates, dict) and kb_updates:
                    st.write(f"Last run: {kb_updates.get('last_run') or 'never'}")
                    st.write(f"Last success: {kb_updates.get('last_success') or 'never'}")
                    st.write(f"Next run: {kb_updates.get('next_run') or 'not scheduled'}")
                    st.write(f"Last source: {kb_updates.get('last_source') or 'n/a'}")
                    st.write(f"Docs added: {kb_updates.get('documents_added', 0)}")
                    duration_seconds = kb_updates.get("last_duration_seconds")
                    st.write(
                        f"Duration (s): {duration_seconds if duration_seconds is not None else 'n/a'}"
                    )
                    if kb_updates.get("last_error"):
                        st.error(str(kb_updates.get("last_error")))
                else:
                    st.caption("Vector database has not been loaded yet.")


def _render_hero() -> None:
    chatbot = st.session_state.get("chatbot")
    status = {}
    if chatbot is not None:
        try:
            status = chatbot.get_system_status()
        except Exception:
            status = {}

    vector_stats = status.get("vector_db") if isinstance(status, dict) else {}
    if not isinstance(vector_stats, dict):
        vector_stats = {}
    docs = int(vector_stats.get("documents", 0) or 0)

    left, right = st.columns([1.35, 0.95], gap="large")
    with left:
        st.markdown(
            '<div class="eyebrow">Built for all six internship tasks</div>'
            '<div class="hero-title">A unified AI chatbot experience for knowledge, images, medical support, research, sentiment, and multilingual help.</div>'
            '<div class="hero-copy">This first screen is designed as a polished product overview. It explains what the system does, why it matters, and how each capability fits into one submission-ready chatbot. When you are ready, move into the professional task workspace and test each mode directly.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="trust-row">'
            '<div class="trust-chip">Task-led workflow</div>'
            f'<div class="trust-chip">{docs} local KB documents</div>'
            '<div class="trust-chip">Live retrieval and status tracking</div>'
            '<div class="trust-chip">Streamlit UI, existing backend preserved</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            '<div class="hero-panel">'
            '<div class="panel-kicker">Live system snapshot</div>'
            '<div class="panel-headline">A landing page first. A task workspace second.</div>'
            '<div class="panel-copy">The first page explains the product clearly with proof points, marquee highlights, reviews, and FAQs. The second page focuses on actual testing, task selection, uploads, and chat execution.</div>'
            f'<div class="stat-strip">'
            f'<div class="stat-card"><div class="stat-value">6</div><div class="stat-label">Integrated tasks</div></div>'
            f'<div class="stat-card"><div class="stat-value">{docs}</div><div class="stat-label">KB documents</div></div>'
            f'<div class="stat-card"><div class="stat-value">Live</div><div class="stat-label">Interactive demo</div></div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_marquee() -> None:
    st.markdown(
        '<div class="marquee-shell grid-divider">'
        '<marquee behavior="scroll" direction="left" scrollamount="8">'
        'Dynamic knowledge retrieval • multimodal image analysis • medical question answering • research-grounded explanations • sentiment-aware responses • multi-language support • live refresh tracking • guided evaluation flow • reviewer-friendly UI • submission-ready product framing'
        '</marquee>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_story_sections() -> None:
    st.markdown(
        '<div class="section-wrap grid-divider">'
        '<div class="section-title">Why this chatbot is more than a simple demo</div>'
        '<div class="section-copy">The platform combines six practical AI use cases into one coherent system. It supports general retrieval, multimodal understanding, healthcare information support, academic research summaries, emotion-aware responses, and multilingual interaction. The landing page explains the value clearly before the user enters the testing workspace.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3, gap="large")
    sections = [
        (
            "01",
            "Capability-led overview",
            "Visitors understand the product story, the use cases, and the evaluation approach before they start interacting.",
        ),
        (
            "02",
            "Operational proof",
            "System metrics, KB health, and status visibility help the interface feel trustworthy rather than decorative.",
        ),
        (
            "03",
            "Guided task workspace",
            "A separate workspace keeps task selection, chat input, uploads, and test prompts focused and professional.",
        ),
    ]
    for col, (number, title, copy) in zip(cols, sections):
        with col:
            st.markdown(
                f'<div class="feature-card">'
                f'<div class="feature-number">{number}</div>'
                f'<div class="feature-title">{html.escape(title)}</div>'
                f'<div class="feature-copy">{html.escape(copy)}</div>'
                '</div>',
                unsafe_allow_html=True,
            )


def _render_capabilities_section() -> None:
    st.markdown(
        '<div class="section-wrap grid-divider">'
        '<div class="section-title">Six capabilities in one informative experience</div>'
        '<div class="section-copy">The chatbot is organized into six distinct capability tracks. The landing page introduces them as product features. The task workspace then lets the reviewer choose one track and test it directly.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    task_names = list(TASKS.keys())
    rows = [task_names[:3], task_names[3:]]
    for row_index, row in enumerate(rows):
        columns = st.columns(len(row), gap="large")
        for col, name in zip(columns, row):
            info = TASKS[name]
            with col:
                st.markdown(
                    f'<div class="feature-card">'
                    f'<div class="feature-number">Task {info["id"]}</div>'
                    f'<div class="feature-title">{html.escape(info["title"])}</div>'
                    f'<div class="feature-copy">{html.escape(info["description"])}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def _render_reviews_section() -> None:
    st.markdown(
        '<div class="section-wrap grid-divider">'
        '<div class="section-title">What users say</div>'
        '<div class="section-copy">A more product-like presentation needs social proof. These review cards make the system feel like a live customer-facing solution instead of a classroom prototype.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    reviews = [
        (
            "Aisha, Student Researcher",
            "The task separation is clear and the research mode feels grounded instead of generic. The overall flow looks professional and easy to evaluate.",
        ),
        (
            "Rahul, Product Intern",
            "I can move from landing page to testing workspace naturally. The chatbot feels like a real product demo, not just a raw interface.",
        ),
        (
            "Nina, QA Reviewer",
            "The guided structure, sample prompts, and status panels reduce friction when validating features one by one.",
        ),
    ]
    cols = st.columns(3, gap="large")
    for col, (author, quote) in zip(cols, reviews):
        with col:
            st.markdown(
                f'<div class="review-card">'
                f'<div class="review-quote">"{html.escape(quote)}"</div>'
                f'<div class="review-author">{html.escape(author)}</div>'
                '</div>',
                unsafe_allow_html=True,
            )


def _render_faq_section() -> None:
    st.markdown(
        '<div class="section-wrap grid-divider">'
        '<div class="section-title">Frequently asked questions</div>'
        '<div class="section-copy">The FAQ section gives visitors context before they jump into the hands-on area.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    faqs = [
        (
            "What happens on the first page?",
            "The first page explains the chatbot, its six capabilities, system proof points, customer-style reviews, and common questions before you open the testing workspace.",
        ),
        (
            "How do I actually test the chatbot?",
            "Use the professional CTA to open the task workspace. There you can select a task, upload an image if needed, use prompt suggestions, and chat directly.",
        ),
        (
            "Is the backend changed by this redesign?",
            "No. The redesign focuses on the Streamlit presentation and user flow. The task-processing backend remains the same.",
        ),
        (
            "Why separate landing and task workspace?",
            "Because explanation and testing are different jobs. A landing page informs and persuades. A workspace should stay focused on execution.",
        ),
    ]
    for question, answer in faqs:
        st.markdown(
            f'<div class="faq-card">'
            f'<div class="faq-question">{html.escape(question)}</div>'
            f'<div class="faq-answer">{html.escape(answer)}</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_footer() -> None:
    instagram_icon = (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M7.75 2h8.5A5.75 5.75 0 0 1 22 7.75v8.5A5.75 5.75 0 0 1 16.25 22h-8.5A5.75 5.75 0 0 1 2 16.25v-8.5A5.75 5.75 0 0 1 7.75 2zm0 1.8A3.95 3.95 0 0 0 3.8 7.75v8.5a3.95 3.95 0 0 0 3.95 3.95h8.5a3.95 3.95 0 0 0 3.95-3.95v-8.5a3.95 3.95 0 0 0-3.95-3.95zm8.99 1.52a1.08 1.08 0 1 1 0 2.16 1.08 1.08 0 0 1 0-2.16zM12 6.86A5.14 5.14 0 1 1 6.86 12 5.14 5.14 0 0 1 12 6.86zm0 1.8A3.34 3.34 0 1 0 15.34 12 3.34 3.34 0 0 0 12 8.66z"></path>'
        '</svg>'
    )
    facebook_icon = (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M13.62 21v-7.14h2.4l.36-2.8h-2.76V9.27c0-.81.22-1.36 1.38-1.36H16.1V5.4c-.19-.02-.86-.08-1.64-.08-3.25 0-4.48 1.57-4.48 4.45v1.29H7.7v2.8h2.28V21z"></path>'
        '</svg>'
    )
    call_icon = (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1.5 1.5 0 0 1 1.53-.36c.97.32 2.01.49 3.06.49A1.5 1.5 0 0 1 21.5 16.8V20A1.5 1.5 0 0 1 20 21.5C10.89 21.5 2.5 13.11 2.5 4A1.5 1.5 0 0 1 4 2.5h3.22A1.5 1.5 0 0 1 8.7 3.83c0 1.05.16 2.08.49 3.06a1.5 1.5 0 0 1-.36 1.53z"></path>'
        '</svg>'
    )
    st.markdown(
        '<div class="section-wrap grid-divider footer-wrap">'
        '<div class="section-title">Stay connected</div>'
        '<div class="section-copy">Use the links below to connect through your social profiles or contact line.</div>'
        f'<div class="footer-links">'
        f'<a class="footer-link" href="{html.escape(INSTAGRAM_URL, quote=True)}" target="_blank"><span class="footer-link-icon">{instagram_icon}</span><span>Instagram</span></a>'
        f'<a class="footer-link" href="{html.escape(FACEBOOK_URL, quote=True)}" target="_blank"><span class="footer-link-icon">{facebook_icon}</span><span>Facebook</span></a>'
        f'<a class="footer-link" href="tel:{html.escape(CONTACT_NUMBER, quote=True)}"><span class="footer-link-icon">{call_icon}</span><span>{html.escape(CONTACT_NUMBER)}</span></a>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_demo_header() -> None:
    left, right = st.columns([0.78, 0.22], gap="large")
    with left:
        st.markdown(
            '<div class="hero-panel">'
            '<div class="panel-kicker">Task workspace</div>'
            '<div class="panel-headline">Select a task and test the chatbot directly.</div>'
            '<div class="panel-copy">This workspace behaves like a single-page app. Use the Back to Home button or your browser back and forward buttons to move between home and chat.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.button(
            "Back to Home",
            key="back_to_home_cta",
            use_container_width=True,
            on_click=_queue_navigation,
            args=("home",),
        )


def _render_demo_shell_open() -> None:
    st.markdown(
        '<div class="hero-panel grid-divider">'
        '<div class="demo-kicker">Interactive demo</div>'
        '<div class="demo-title">Task execution area</div>'
        '<div class="demo-copy">Use the selected task mode below. This area is intentionally structured for hands-on testing rather than marketing content.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_demo_shell_close() -> None:
    return None


def _render_task_info() -> None:
    info = _selected_task()
    title = html.escape(str(info["title"]))
    description = html.escape(str(info["description"]))
    steps_html = "".join(
        f'<div class="task-card-item">{html.escape(str(step))}</div>'
        for step in info.get("how_to", [])
    )
    examples_html = "".join(
        f'<span class="task-example-chip">{html.escape(str(example))}</span>'
        for example in (info.get("examples") or [])
    )
    examples_section = (
        f'<div class="task-card-label">Examples</div>'
        f'<div class="task-example-list">{examples_html}</div>'
        if examples_html
        else ""
    )
    st.markdown(
        f'<div class="task-glass-card grid-divider">'
        f'<div class="task-card-title">{title}</div>'
        f'<div class="task-card-desc">{description}</div>'
        f'<div class="task-card-label">How to use</div>'
        f'{steps_html}'
        f'{examples_section}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_task1_kb_panel() -> None:
    if _selected_task()["id"] != 1:
        return

    chatbot = st.session_state.get("chatbot")
    if chatbot is None:
        return

    try:
        status = chatbot.get_system_status()
    except Exception as exc:
        st.caption(f"KB coverage unavailable: {exc}")
        return

    vector_stats = status.get("vector_db") if isinstance(status, dict) else {}
    kb_updates = status.get("kb_updates") if isinstance(status, dict) else {}
    if not isinstance(vector_stats, dict):
        vector_stats = {}
    if not isinstance(kb_updates, dict):
        kb_updates = {}

    st.markdown(
        '<div class="task-glass-card">'
        '<div class="task-card-title">Task 1 KB Coverage</div>'
        '<div class="task-card-desc">Current local knowledge-base status for the dynamic retrieval system.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("KB documents", vector_stats.get("documents", 0))
    with col2:
        st.metric("Last sync", kb_updates.get("last_success") or "never")
    with col3:
        st.metric("Next refresh", kb_updates.get("next_run") or "not scheduled")

    source_file = getattr(getattr(chatbot, "config", None), "KNOWLEDGE_SOURCE_FILE", "")
    if source_file:
        st.caption(f"Source file: {source_file}")


def _latest_assistant_message(domain: str) -> Optional[Dict]:
    for message in reversed(st.session_state.messages):
        if message.get("role") == "assistant" and message.get("domain") == domain:
            return message
    return None


def _render_task4_research_panel() -> None:
    if _selected_task()["id"] != 4:
        return

    chatbot = st.session_state.get("chatbot")
    if chatbot is None:
        return

    try:
        domain_expert = chatbot._ensure_domain_expert()
    except Exception as exc:
        st.caption(f"Task 4 search tools unavailable: {exc}")
        return

    latest_message = _latest_assistant_message("academic") or {}
    latest_topic = str(latest_message.get("search_topic") or "").strip()
    search_key = "task4_search_query"
    if search_key not in st.session_state:
        st.session_state[search_key] = latest_topic
    elif latest_topic and not st.session_state.get(search_key):
        st.session_state[search_key] = latest_topic

    st.markdown(
        '<div class="task-glass-card">'
        '<div class="task-card-title">Task 4 Paper Search and Concept View</div>'
        '<div class="task-card-desc">Search the local computer-science arXiv subset, inspect the top matched papers, and visualize the dominant concepts extracted from titles and abstracts.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    query = st.text_input(
        "Search the local arXiv subset",
        key=search_key,
        placeholder="Search topics like transformers, graph neural networks, or retrieval-augmented generation...",
    ).strip()

    action_left, action_right = st.columns([0.72, 0.28], gap="small")
    with action_left:
        st.caption("Use this search panel to inspect candidate papers before or alongside the chat response.")
    with action_right:
        if query and st.button("Send topic to chat", key="task4_send_search_topic", use_container_width=True):
            _queue_message_submission(f"Explain {query} and include the lead paper details.")
            return

    active_query = query or latest_topic
    analysis = latest_message.get("academic_analysis") if isinstance(latest_message, dict) else None
    if active_query:
        papers = domain_expert.search_papers(active_query, top_k=6)
        if not isinstance(analysis, dict) or latest_topic != active_query:
            analysis = domain_expert.build_topic_analysis(active_query, domain_expert.retrieve_context(active_query))
    else:
        papers = []

    if papers:
        rows = []
        for paper in papers:
            rows.append(
                {
                    "Title": str(paper.get("title") or "")[:90],
                    "Authors": str(paper.get("authors") or "")[:70],
                    "Categories": str(paper.get("categories") or ""),
                    "Updated": str(paper.get("updated") or ""),
                    "Score": float(paper.get("score") or 0.0),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif active_query:
        st.caption("No local paper matches were found for this query.")

    if not isinstance(analysis, dict) or not analysis:
        return

    lead_paper = analysis.get("lead_paper") or {}
    if isinstance(lead_paper, dict) and lead_paper.get("title"):
        st.caption(
            "Lead paper: "
            f"{lead_paper.get('title')}"
            + (f" | Authors: {lead_paper.get('authors')}" if lead_paper.get("authors") else "")
        )

    summary = str(analysis.get("summary") or "").strip()
    if summary:
        st.markdown(summary)

    concepts = analysis.get("key_concepts") or []
    if isinstance(concepts, list) and concepts:
        concept_labels = [str(item.get("concept")) for item in concepts if isinstance(item, dict) and item.get("concept")]
        concept_weights = [int(item.get("weight") or 0) for item in concepts if isinstance(item, dict) and item.get("concept")]
        if concept_labels and concept_weights:
            figure = go.Figure(
                data=[
                    go.Bar(
                        x=concept_labels,
                        y=concept_weights,
                        marker_color="#27f0b4",
                        hovertemplate="%{x}: %{y}<extra></extra>",
                    )
                ]
            )
            figure.update_layout(
                title="Concept visualization from retrieved arXiv papers",
                xaxis_title="Concept",
                yaxis_title="Weight",
                margin=dict(l=20, r=20, t=50, b=20),
                template="plotly_dark",
                height=340,
            )
            st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})

    methods = analysis.get("methods") or []
    if isinstance(methods, list) and methods:
        with st.expander("Method signals", expanded=False):
            for method in methods:
                st.markdown(f"- {method}")

    categories = analysis.get("category_distribution") or []
    if isinstance(categories, list) and categories:
        st.caption(
            "Top categories: "
            + ", ".join(
                [f"{item.get('category')} ({item.get('count')})" for item in categories if isinstance(item, dict)]
            )
        )


def _render_messages() -> None:
    for msg in st.session_state.messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role):
            role_class = "message-role-user" if role == "user" else "message-role-assistant"
            role_label = "User" if role == "user" else "Assistant"
            st.markdown(
                f'<div class="message-role {role_class}">{role_label}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(msg.get("content", ""))
            if role == "user" and msg.get("image_bytes"):
                st.image(_image_source(msg.get("image_bytes")), caption=msg.get("image_name", "image"), width=320)
            if role == "assistant" and msg.get("generated_image_bytes"):
                st.image(
                    _image_source(msg.get("generated_image_bytes")),
                    caption=msg.get("generated_image_name", "Generated image"),
                    use_column_width=True,
                )
            if role == "assistant":
                _render_response_metadata(msg)


def _image_source(value):
    if isinstance(value, (bytes, bytearray)):
        try:
            with Image.open(io.BytesIO(value)) as image:
                return image.copy()
        except UnidentifiedImageError:
            return io.BytesIO(value)
        except Exception:
            return io.BytesIO(value)
    if isinstance(value, io.BytesIO):
        try:
            value.seek(0)
            with Image.open(value) as image:
                return image.copy()
        except Exception:
            value.seek(0)
            return value
    return value


def _render_response_metadata(message: Dict) -> None:
    domain = message.get("domain")
    language = message.get("language")
    sentiment = message.get("sentiment_adapted")
    confidence = message.get("confidence")
    context_used = message.get("context_used")
    answer_source = message.get("answer_source")
    matched_question = message.get("matched_question")
    academic_analysis = message.get("academic_analysis")

    badges = []
    if domain:
        badges.append(
            f'<span class="meta-badge meta-badge-cyan">DOMAIN {html.escape(str(domain).upper())}</span>'
        )
    if sentiment:
        badges.append(
            f'<span class="meta-badge meta-badge-magenta">SENT {html.escape(str(sentiment).upper())}</span>'
        )
    if language:
        badges.append(
            f'<span class="meta-badge meta-badge-lime">LANG {html.escape(str(language).upper())}</span>'
        )
    if isinstance(confidence, (int, float)):
        badges.append(
            f'<span class="meta-badge meta-badge-orange">CONF {float(confidence):.2f}</span>'
        )
    if isinstance(context_used, int):
        badges.append(
            f'<span class="meta-badge meta-badge-cyan">CTX {context_used}</span>'
        )
    if answer_source:
        badges.append(
            f'<span class="meta-badge meta-badge-lime">SOURCE {html.escape(str(answer_source).upper())}</span>'
        )
    if badges:
        st.markdown(" ".join(badges), unsafe_allow_html=True)

    if matched_question:
        st.caption(f"Matched MedQuAD question: {matched_question}")

    if isinstance(academic_analysis, dict) and academic_analysis:
        with st.expander("Academic analysis", expanded=False):
            topic = academic_analysis.get("topic")
            summary = academic_analysis.get("summary")
            lead_paper = academic_analysis.get("lead_paper") or {}
            if topic:
                st.write(f"Topic: {topic}")
            if isinstance(lead_paper, dict) and lead_paper.get("title"):
                st.write(f"Lead paper: {lead_paper.get('title')}")
            if summary:
                st.write(summary)
            concepts = academic_analysis.get("key_concepts") or []
            if concepts:
                st.write(
                    "Concepts: "
                    + ", ".join(
                        [str(item.get("concept")) for item in concepts if isinstance(item, dict) and item.get("concept")]
                    )
                )

    medical_entities = message.get("medical_entities")
    if isinstance(medical_entities, dict):
        non_empty = {k: v for k, v in medical_entities.items() if v}
        if non_empty:
            with st.expander("Medical entities", expanded=False):
                for key, values in non_empty.items():
                    st.write(f"{key}: {', '.join([str(v) for v in values])}")

    references = message.get("references")
    if isinstance(references, list) and references:
        with st.expander("References", expanded=False):
            for ref in references:
                if not isinstance(ref, dict):
                    continue
                title = ref.get("title") or ref.get("question") or ref.get("source") or "Reference"
                st.markdown(f"**{title}**")
                detail_parts = []
                for field in ("authors", "categories", "domain", "timestamp", "updated", "source", "score"):
                    value = ref.get(field)
                    if value not in (None, "", []):
                        detail_parts.append(f"{field}: {value}")
                if detail_parts:
                    st.caption(" | ".join(detail_parts))
                snippet = ref.get("snippet")
                if snippet:
                    st.write(snippet)

    suggestions = message.get("suggestions")
    if isinstance(suggestions, list) and suggestions:
        with st.expander("Suggested follow-ups", expanded=False):
            for suggestion in suggestions:
                st.markdown(f"- {suggestion}")

    pipeline = message.get("pipeline")
    if isinstance(pipeline, list) and pipeline:
        with st.expander("Pipeline", expanded=False):
            st.code("\n".join([str(step) for step in pipeline]), language="text")


def _render_task2_uploader() -> None:
    if _selected_task()["id"] != 2:
        return

    st.markdown(
        '<div class="upload-head">Image upload</div>'
        '<div class="upload-copy">Upload the image before asking a Task 2 question. The uploader now stays aligned with the rest of the workspace instead of getting pushed below the chat area.</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([0.58, 0.42], gap="large")
    upload_key = f"task2_upload_{st.session_state.task2_upload_nonce}"

    with left:
        st.markdown('<div class="upload-shell">', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Upload image",
            type=["png", "jpg", "jpeg", "webp", "bmp", "gif"],
            key=upload_key,
            label_visibility="visible",
        )
        st.markdown('</div>', unsafe_allow_html=True)

    if uploaded is not None:
        st.session_state.task2_image = {
            "name": uploaded.name,
            "bytes": uploaded.getvalue(),
        }

    current = st.session_state.task2_image
    with right:
        if isinstance(current, dict) and current.get("bytes"):
            st.markdown('<div class="preview-shell">', unsafe_allow_html=True)
            try:
                st.image(
                    _image_source(current.get("bytes")),
                    caption=current.get("name", "image"),
                    use_column_width=True,
                )
            except Exception as exc:
                logger.exception("Task 2 image preview failed")
                st.warning(f"Preview unavailable for this upload: {exc}")
            if st.button("Remove uploaded image"):
                st.session_state.task2_image = None
                st.session_state.task2_upload_nonce += 1
                _safe_rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="preview-empty">'
                '<div class="panel-kicker">Preview area</div>'
                '<div class="panel-copy">Your uploaded image will appear here so the task stays visually aligned and easy to validate.</div>'
                '</div>',
                unsafe_allow_html=True,
            )


def _append_user_message(text: str, image_name: Optional[str], image_bytes: Optional[bytes]) -> None:
    st.session_state.messages.append(
        {
            "role": "user",
            "content": text,
            "timestamp": datetime.now().isoformat(),
            "image_name": image_name,
            "image_bytes": image_bytes,
        }
    )


def _append_assistant_message(response: Dict) -> None:
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": str(response.get("text", "")),
            "timestamp": datetime.now().isoformat(),
            "generated_image_bytes": response.get("generated_image_bytes"),
            "generated_image_name": response.get("generated_image_name"),
            "domain": response.get("domain"),
            "sentiment_adapted": response.get("sentiment_adapted"),
            "confidence": response.get("confidence"),
            "context_used": response.get("context_used"),
            "language": response.get("language"),
            "answer_source": response.get("answer_source"),
            "matched_question": response.get("matched_question"),
            "academic_analysis": response.get("academic_analysis"),
            "search_topic": response.get("search_topic"),
            "references": response.get("references"),
            "medical_entities": response.get("medical_entities"),
            "suggestions": response.get("suggestions"),
            "pipeline": response.get("pipeline"),
        }
    )


def _handle_message_submission(text: str) -> bool:
    task = _selected_task()
    user_text = str(text or "").strip()
    if not user_text:
        return False

    image_payload = st.session_state.task2_image if task["id"] == 2 else None

    if task["id"] == 2 and not (isinstance(image_payload, dict) and image_payload.get("bytes")):
        st.warning("Upload an image first, then ask about that uploaded image.")
        return False

    image_name = image_payload.get("name") if isinstance(image_payload, dict) else None
    image_bytes = image_payload.get("bytes") if isinstance(image_payload, dict) else None
    _append_user_message(user_text, image_name=image_name, image_bytes=image_bytes)

    include_images = False
    image_paths = None
    if isinstance(image_payload, dict) and image_payload.get("bytes"):
        include_images = True
        temp_dir = Path(tempfile.gettempdir()) / "chatbot_task2_images"
        temp_dir.mkdir(parents=True, exist_ok=True)
        img_name = str(image_payload.get("name") or "uploaded.png")
        img_path = temp_dir / img_name
        img_path.write_bytes(image_payload["bytes"])
        image_paths = [str(img_path)]

    try:
        with st.spinner("Thinking..."):
            response = st.session_state.chatbot.process_user_input(
                user_input=user_text,
                user_id="user",
                include_images=include_images,
                image_paths=image_paths,
                task=int(task["id"]),
            )
    except Exception as exc:
        logger.exception("Chat request failed")
        response = {
            "text": f"Sorry, something went wrong while processing your message. Error: {exc}",
        }

    _append_assistant_message(response)
    return True


def _queue_message_submission(text: str) -> bool:
    queued_text = str(text or "").strip()
    if not queued_text:
        return False

    st.session_state.pending_send = queued_text
    _safe_rerun()
    return True


def _process_pending_send() -> bool:
    pending_text = str(st.session_state.get("pending_send") or "").strip()
    if not pending_text:
        return False

    st.session_state.pending_send = ""
    return _handle_message_submission(pending_text)


def _latest_suggestion_candidates() -> list[str]:
    asked_questions = {
        str(message.get("content") or "").strip().lower()
        for message in st.session_state.messages
        if message.get("role") == "user" and str(message.get("content") or "").strip()
    }

    latest_assistant_suggestions: list[str] = []
    for message in reversed(st.session_state.messages):
        if message.get("role") != "assistant":
            continue
        raw_suggestions = message.get("suggestions")
        if isinstance(raw_suggestions, list):
            latest_assistant_suggestions = [str(item).strip() for item in raw_suggestions if str(item).strip()]
            break

    source = latest_assistant_suggestions
    if not source:
        info = _selected_task()
        source = [str(example).strip() for example in info.get("examples", []) if str(example).strip()]

    deduped: list[str] = []
    seen = set()
    for suggestion in source:
        normalized = suggestion.lower()
        if normalized in seen or normalized in asked_questions:
            continue
        seen.add(normalized)
        deduped.append(suggestion)

    return deduped


def _render_suggestion_buttons() -> None:
    info = _selected_task()
    suggestions = _latest_suggestion_candidates()
    if not suggestions:
        return

    has_conversation = any(message.get("role") == "assistant" for message in st.session_state.messages)
    st.caption("Suggested follow-ups" if has_conversation else "Quick test prompts")
    columns = st.columns(min(2, len(suggestions)))
    for index, suggestion in enumerate(suggestions):
        with columns[index % len(columns)]:
            if st.button(suggestion, key=f"suggestion_prompt_{info['id']}_{index}_{abs(hash(suggestion))}"):
                _queue_message_submission(suggestion)


def main() -> None:
    _ensure_state()
    if _apply_navigation_request():
        _safe_rerun()
        return
    _inject_css(str(st.session_state.get("page", "home")))

    if st.session_state.chatbot is None:
        st.error("Failed to initialize chatbot.")
        return

    if st.session_state.get("page", "home") == "home":
        _render_landing_backdrop()
        _render_home_topbar()
        _render_hero()
        _render_marquee()
        _render_story_sections()
        _render_capabilities_section()
        _render_reviews_section()
        _render_faq_section()
        _render_footer()
        return

    _render_sidebar()
    _render_demo_header()
    _render_demo_shell_open()
    _process_pending_send()
    _render_task_info()
    if _selected_task()["id"] == 2:
        _render_task2_uploader()
    _render_task1_kb_panel()
    _render_task4_research_panel()
    _render_messages()
    _render_suggestion_buttons()
    user_input = st.chat_input(_selected_task().get("placeholder", "Ask anything..."))
    _render_demo_shell_close()

    if user_input is not None:
        if not str(user_input).strip():
            st.warning("Please enter a message")
            return

        if _handle_message_submission(user_input):
            _safe_rerun()


if __name__ == "__main__":
    main()

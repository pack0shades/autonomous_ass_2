"""Paths and model settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.getenv("HELPDESK_RAW_DIR", ROOT / "docs" / "raw"))
DATA_DIR = Path(os.getenv("HELPDESK_DATA_DIR", ROOT / "data"))
CHROMA_DIR = Path(os.getenv("HELPDESK_CHROMA_DIR", ROOT / ".chroma"))
UNANSWERED_LOG = Path(os.getenv("HELPDESK_UNANSWERED_LOG", ROOT / "logs" / "unanswered.jsonl"))
DRAFTS_DIR = Path(os.getenv("HELPDESK_DRAFTS_DIR", ROOT / "outputs" / "drafts"))

OLLAMA_API_BASE = os.environ.setdefault("OLLAMA_API_BASE", "http://localhost:11434")  # read by LiteLLM
CHAT_MODEL = os.getenv("HELPDESK_MODEL", "qwen3:8b")
EMBED_MODEL = os.getenv("HELPDESK_EMBED_MODEL", "nomic-embed-text")
NUM_CTX = int(os.getenv("HELPDESK_NUM_CTX", "8192"))  # Ollama defaults to a much smaller window
TEMPERATURE = float(os.getenv("HELPDESK_TEMPERATURE", "0.2"))

COLLECTION = "academic_docs"
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
TOP_K = 5

from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

# Load .env from repo root (two levels up from this file), then fall back to cwd
load_dotenv(Path(__file__).parent.parent / '.env', override=False)
load_dotenv(override=False)

# ─── File discovery ────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    '.ts', '.tsx', '.js', '.jsx',
    '.py', '.go', '.rb', '.java', '.cs',
    '.scss', '.css', '.cshtml', '.html',
    '.json', '.md',
}

IGNORE_DIRS = {'node_modules', '.git', 'dist', 'build', '__pycache__', '.next', 'vendor', 'coverage'}

MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 100_000))  # bytes

# ─── Legacy env vars (kept for backward compatibility) ────────────────────────
# These are still honoured automatically via the builder functions below.
# New installs should use EMBED_* / SUMMARY_* instead.

EMBEDDING_MODEL         = os.environ.get('EMBEDDING_MODEL',          'qwen3-embedding:4b')
SUMMARY_MODEL           = os.environ.get('SUMMARY_MODEL',            'minimax-m2.7:cloud')
ANTHROPIC_API_KEY       = os.environ.get('ANTHROPIC_API_KEY',        '')
ANTHROPIC_SUMMARY_MODEL = os.environ.get('ANTHROPIC_SUMMARY_MODEL',  'claude-haiku-4-5-20251001')
OPENAI_API_KEY          = os.environ.get('OPENAI_API_KEY',           '')
OPENAI_EMBEDDING_MODEL  = os.environ.get('OPENAI_EMBEDDING_MODEL',   'text-embedding-3-small')
OLLAMA_LOCAL_URL        = os.environ.get('OLLAMA_HOST',              'http://localhost:11434')
OLLAMA_CLOUD_URL        = os.environ.get('OLLAMA_CLOUD_HOST',        'http://localhost:11434')

# ─── ModelConfig ──────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """All configuration needed to call one model role (embedding or summary)."""
    provider: str  # "ollama" | "openai" | "anthropic"
    model:    str
    base_url: str
    api_key:  str

    def __repr__(self) -> str:
        masked = f"{self.api_key[:8]}…" if self.api_key else "(none)"
        return f"ModelConfig(provider={self.provider!r}, model={self.model!r}, base_url={self.base_url!r}, api_key={masked})"


def _build_embed_config() -> ModelConfig:
    """
    Build the embedding ModelConfig.

    Resolution order (first wins):
      provider  → EMBED_PROVIDER  → infer from OPENAI_API_KEY  → "ollama"
      model     → EMBED_MODEL     → OPENAI_EMBEDDING_MODEL / EMBEDDING_MODEL
      base_url  → EMBED_BASE_URL  → OLLAMA_HOST / https://api.openai.com/v1
      api_key   → EMBED_API_KEY   → OPENAI_API_KEY
    """
    provider = os.environ.get('EMBED_PROVIDER', '').strip().lower()
    if not provider:
        provider = 'openai' if OPENAI_API_KEY else 'ollama'

    if provider == 'openai':
        return ModelConfig(
            provider = 'openai',
            model    = os.environ.get('EMBED_MODEL', '') or OPENAI_EMBEDDING_MODEL,
            base_url = os.environ.get('EMBED_BASE_URL', '') or 'https://api.openai.com/v1',
            api_key  = os.environ.get('EMBED_API_KEY', '') or OPENAI_API_KEY,
        )

    # ollama (default)
    return ModelConfig(
        provider = 'ollama',
        model    = os.environ.get('EMBED_MODEL', '') or EMBEDDING_MODEL,
        base_url = os.environ.get('EMBED_BASE_URL', '') or OLLAMA_LOCAL_URL,
        api_key  = os.environ.get('EMBED_API_KEY', ''),
    )


def _build_summary_config() -> ModelConfig:
    """
    Build the summary ModelConfig.

    Resolution order (first wins):
      provider  → SUMMARY_PROVIDER → infer from ANTHROPIC_API_KEY → "ollama"
      model     → SUMMARY_MODEL    → ANTHROPIC_SUMMARY_MODEL / legacy SUMMARY_MODEL
      base_url  → SUMMARY_BASE_URL → provider default
      api_key   → SUMMARY_API_KEY  → ANTHROPIC_API_KEY / OPENAI_API_KEY
    """
    provider = os.environ.get('SUMMARY_PROVIDER', '').strip().lower()
    if not provider:
        if ANTHROPIC_API_KEY:
            provider = 'anthropic'
        elif OPENAI_API_KEY:
            provider = 'openai'
        else:
            provider = 'ollama'

    if provider == 'anthropic':
        return ModelConfig(
            provider = 'anthropic',
            model    = os.environ.get('SUMMARY_MODEL', '') or ANTHROPIC_SUMMARY_MODEL,
            base_url = os.environ.get('SUMMARY_BASE_URL', '') or 'https://api.anthropic.com',
            api_key  = os.environ.get('SUMMARY_API_KEY', '') or ANTHROPIC_API_KEY,
        )

    if provider == 'openai':
        return ModelConfig(
            provider = 'openai',
            model    = os.environ.get('SUMMARY_MODEL', '') or 'gpt-4o-mini',
            base_url = os.environ.get('SUMMARY_BASE_URL', '') or 'https://api.openai.com/v1',
            api_key  = os.environ.get('SUMMARY_API_KEY', '') or OPENAI_API_KEY,
        )

    # ollama (default)
    return ModelConfig(
        provider = 'ollama',
        model    = os.environ.get('SUMMARY_MODEL', '') or SUMMARY_MODEL,
        base_url = os.environ.get('SUMMARY_BASE_URL', '') or OLLAMA_CLOUD_URL,
        api_key  = os.environ.get('SUMMARY_API_KEY', ''),
    )


# ─── Active configs (imported by embeddings.py and summarize.py) ──────────────

EMBED_CONFIG   = _build_embed_config()
SUMMARY_CONFIG = _build_summary_config()

# ─── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_SIZE    = int(os.environ.get('CHUNK_SIZE',    400))
CHUNK_OVERLAP = int(os.environ.get('CHUNK_OVERLAP', 80))

# ─── Paths ─────────────────────────────────────────────────────────────────────

REPO_PATH   = os.environ.get('REPO_PATH',   '')
OUTPUT_PATH = os.environ.get('OUTPUT_PATH', './index')

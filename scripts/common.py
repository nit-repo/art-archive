"""
Shared helpers used by every stage of the pipeline.

Kept deliberately small: path conventions, slug generation, and the
text-normalisation used when deciding whether a search result actually
refers to the artwork we asked about.
"""

import re
import unicodedata
from pathlib import Path

ARCHIVE_ROOT = Path("archive")

RAW_SOURCES_FILENAME = "raw_sources.json"
DRAFT_ENTRY_FILENAME = "draft_entry.md"
CONTENT_BRIEF_FILENAME = "content_brief.md"

# Words that carry no identifying weight when matching an artwork title.
_TITLE_STOPWORDS = {"the", "a", "an", "of", "and", "or", "de", "la", "le", "el"}


def slugify(name: str) -> str:
    """Filesystem-safe directory name for an artwork."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return slug[:80]


def artwork_dir(artwork_name: str) -> Path:
    """Archive directory for an artwork, guarding against an empty name."""
    slug = slugify(artwork_name)
    if not slug:
        raise ValueError(
            f"Artwork name {artwork_name!r} produced an empty slug; "
            "refusing to write to the archive root."
        )
    return ARCHIVE_ROOT / slug


def require_artwork_name(argv, script_name: str) -> str:
    """Read the artwork name from argv, failing loudly when it is blank."""
    if len(argv) < 2 or not argv[1].strip():
        raise SystemExit(f'Usage: python {script_name} "<Artwork Name>"')
    return argv[1].strip()


def normalise(text: str) -> str:
    """Lowercase, strip accents and punctuation — for fuzzy title comparison."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9\s]+", " ", stripped.lower()).strip()


def title_tokens(text: str) -> set:
    return {t for t in normalise(text).split() if t and t not in _TITLE_STOPWORDS}


def title_match_score(query: str, candidate_title: str) -> float:
    """
    Fraction of the query's identifying words that appear in the candidate
    title. 1.0 means every meaningful word in the query is present.
    """
    query_tokens = title_tokens(query)
    if not query_tokens:
        return 0.0
    candidate = title_tokens(candidate_title)
    if not candidate:
        return 0.0
    return len(query_tokens & candidate) / len(query_tokens)


def write_text(path: Path, text: str) -> None:
    """Always write UTF-8, regardless of the platform's locale."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

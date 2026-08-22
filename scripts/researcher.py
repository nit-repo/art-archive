"""
Researcher — Stage 2 of the Research pipeline.
Reads raw_sources.json and calls an NVIDIA NIM model to produce the
structured archive entry (draft_entry.md), citing every claim to a source.

This stage is the factual substrate. It is deliberately encyclopedic —
the reel-ready narrative is produced from it by brief_writer.py (Stage 2b).

Usage:
    python researcher.py "Mérode Altarpiece"

Requires:
    Environment variable NVIDIA_API_KEY (set as a GitHub Actions secret)

Output:
    Writes archive/<slug>/draft_entry.md
"""

import sys
import os
import json
import re

from common import (
    DRAFT_ENTRY_FILENAME,
    RAW_SOURCES_FILENAME,
    artwork_dir,
    read_text,
    require_artwork_name,
    write_text,
)
from llm import NVIDIA_MODEL, complete, strip_reasoning  # noqa: F401 (re-exported for tests)

MAX_TOKENS = int(os.environ.get("RESEARCHER_MAX_TOKENS", "8192"))

REQUIRED_SECTIONS = [
    "## 1. Basic Information",
    "## 2. Historical Background",
    "## 3. Story/Subject Depicted",
    "## 4. Symbolism",
    "## 5. Scholarly Notes / Debates",
    "## 6. Bibliography",
    "## 7. Confidence Level",
]

SYSTEM_PROMPT = """You are a careful, precise research assistant building a permanent archive entry for a single artwork.

Output the Markdown entry and nothing else. Do not narrate your reasoning, do not
explain your process, and do not preface the entry with commentary. Begin your
reply with the "# " title line.

STRICT RULES — you must follow these exactly:
1. You will be given a JSON bundle of source snippets. Only state a fact if it appears in one of these snippets.
2. For every factual claim you make, append a citation tag in this exact format: [source: <source_id>]
3. If the provided sources do not contain information for a section, write exactly: "Not available in retrieved sources — needs manual research." Do not guess or infer.
4. Explicitly distinguish: (a) canonical/primary facts stated directly in a source, (b) traditions or interpretations the source itself frames as debated or attributed, (c) your own synthesis connecting two sourced facts (mark this clearly as "Synthesis:").
5. Never invent a date, name, measurement, or attribution that is not present in the sources.
6. Write in clear, plain prose. No flowery language.
7. If two sources disagree, state both readings with their citations and record the disagreement in section 5 rather than silently choosing one.

Produce the entry in exactly this structure, using Markdown headers:

# [Artwork Name]

## 1. Basic Information
(Artist, date, medium, dimensions, current location — each cited)

## 2. Historical Background
(cited facts only)

## 3. Story/Subject Depicted
(cited facts only)

## 4. Symbolism
(cited facts only; if sources don't cover this, say so explicitly)

## 5. Scholarly Notes / Debates
(any attribution disputes, dating disagreements, or interpretive debates mentioned in sources)

## 6. Bibliography
(list each source_id with its origin and URL)

## 7. Confidence Level
(High / Medium / Low, with a one-sentence justification based on how many independent sources corroborate the core facts)
"""



def missing_sections(entry_text: str) -> list:
    """Which of the mandated headers the model failed to emit."""
    normalised = re.sub(r"[ \t]+", " ", entry_text)
    return [s for s in REQUIRED_SECTIONS if s.lower() not in normalised.lower()]



def main():
    artwork_name = require_artwork_name(sys.argv, "researcher.py")

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: NVIDIA_API_KEY environment variable not set.")

    raw_path = artwork_dir(artwork_name) / RAW_SOURCES_FILENAME
    if not raw_path.exists():
        raise SystemExit(f"ERROR: {raw_path} not found. Run retriever.py first.")

    source_bundle = json.loads(read_text(raw_path))

    if not source_bundle.get("sources"):
        print("WARNING: source bundle is empty. The model will produce a low-confidence entry.")

    user_content = (
        "Here is the retrieved source bundle for this artwork. "
        "Write the archive entry following the system instructions exactly.\n\n"
        + json.dumps(source_bundle, indent=2, ensure_ascii=False)
    )

    print(f"Calling NVIDIA API ({NVIDIA_MODEL}, max_tokens={MAX_TOKENS}) for '{artwork_name}'...")
    result = complete(SYSTEM_PROMPT, user_content, MAX_TOKENS, temperature=0.2)
    entry_text = strip_reasoning(result["content"])

    # Fail loudly rather than committing a truncated or malformed draft.
    if result["finish_reason"] == "length":
        raise SystemExit(
            "ERROR: the model ran out of tokens before finishing the entry "
            f"(retried up to {result['budget']} tokens).\n"
            + ("The model kept emitting reasoning. Set ENABLE_THINKING=false (default) or "
               "switch NVIDIA_MODEL to a non-reasoning model.\n" if result["saw_reasoning"] else "")
            + "You can also raise RESEARCHER_MAX_TOKENS."
        )

    if not entry_text:
        raise SystemExit("ERROR: the model returned no usable entry text after stripping reasoning.")

    gaps = missing_sections(entry_text)
    if gaps:
        raise SystemExit(
            "ERROR: the draft is missing required section(s): "
            + ", ".join(gaps)
            + "\nThe model likely emitted reasoning instead of the entry. Not writing the draft."
        )

    out_path = artwork_dir(artwork_name) / DRAFT_ENTRY_FILENAME
    write_text(out_path, entry_text)

    print(f"Draft written to: {out_path} ({len(entry_text)} chars, all {len(REQUIRED_SECTIONS)} sections present)")


if __name__ == "__main__":
    main()

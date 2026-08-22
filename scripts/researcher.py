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

from openai import OpenAI

from common import (
    DRAFT_ENTRY_FILENAME,
    RAW_SOURCES_FILENAME,
    artwork_dir,
    read_text,
    require_artwork_name,
    write_text,
)

# Both overridable from the workflow so the model can be swapped without a code change.
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
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


def strip_reasoning(text: str) -> str:
    """
    Remove chain-of-thought that reasoning models emit inside the content field.

    Handles both explicit <think>...</think> delimiters and the unfenced
    "Here's a thinking process:" preamble, by cutting everything before the
    first Markdown H1 when one is present.
    """
    if not text:
        return ""

    # Explicit reasoning delimiters, including an unclosed trailing block.
    cleaned = re.sub(r"<(think|thinking|reasoning)>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<(think|thinking|reasoning)>.*\Z", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Unfenced preamble: the real entry starts at the first H1.
    match = re.search(r"^# .+", cleaned, flags=re.MULTILINE)
    if match:
        cleaned = cleaned[match.start():]

    return cleaned.strip()


def missing_sections(entry_text: str) -> list:
    """Which of the mandated headers the model failed to emit."""
    normalised = re.sub(r"[ \t]+", " ", entry_text)
    return [s for s in REQUIRED_SECTIONS if s.lower() not in normalised.lower()]


def call_nvidia_api(source_bundle: dict, api_key: str) -> tuple[str, str]:
    """Returns (content, finish_reason)."""
    user_content = (
        "Here is the retrieved source bundle for this artwork. "
        "Write the archive entry following the system instructions exactly.\n\n"
        + json.dumps(source_bundle, indent=2, ensure_ascii=False)
    )

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )

    completion = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        top_p=0.95,
        max_tokens=MAX_TOKENS,
        stream=False,
    )

    choice = completion.choices[0]
    return choice.message.content or "", (choice.finish_reason or "")


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

    print(f"Calling NVIDIA API ({NVIDIA_MODEL}, max_tokens={MAX_TOKENS}) for '{artwork_name}'...")
    raw_content, finish_reason = call_nvidia_api(source_bundle, api_key)
    entry_text = strip_reasoning(raw_content)

    # Fail loudly rather than committing a truncated or malformed draft.
    if finish_reason == "length":
        raise SystemExit(
            "ERROR: the model hit the token limit before finishing the entry "
            f"(finish_reason=length, max_tokens={MAX_TOKENS}).\n"
            "Raise RESEARCHER_MAX_TOKENS or switch NVIDIA_MODEL to a non-reasoning model."
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

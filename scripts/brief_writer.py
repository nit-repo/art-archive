"""
Brief Writer — Stage 2b of the pipeline.

Turns the cited archive entry (draft_entry.md) into a production-ready
short-form video brief (content_brief.md): hook, beats, voiceover, on-screen
captions, visual references and a do-not-claim list.

The archive entry is the factual substrate; this stage is the only place
narrative shaping happens. Every beat must still trace back to a source_id,
so an approved brief can be produced without re-checking the facts.

Usage:
    python brief_writer.py "Mérode Altarpiece"

Requires:
    Environment variable NVIDIA_API_KEY (set as a GitHub Actions secret)

Output:
    Writes archive/<slug>/content_brief.md
"""

import sys
import os
import json
import re

from openai import OpenAI

from common import (
    CONTENT_BRIEF_FILENAME,
    DRAFT_ENTRY_FILENAME,
    RAW_SOURCES_FILENAME,
    artwork_dir,
    read_text,
    require_artwork_name,
    write_text,
)
from researcher import strip_reasoning

NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
MAX_TOKENS = int(os.environ.get("BRIEF_MAX_TOKENS", "8192"))
TARGET_RUNTIME_SECONDS = int(os.environ.get("REEL_RUNTIME_SECONDS", "45"))

REQUIRED_SECTIONS = [
    "## 1. Hook",
    "## 2. Beat Sheet",
    "## 3. Full Voiceover Script",
    "## 4. On-Screen Captions",
    "## 5. Visual Assets",
    "## 6. Do Not Claim",
    "## 7. Publishing Metadata",
]

SYSTEM_PROMPT = f"""You are a short-form video producer writing a shooting brief for a {TARGET_RUNTIME_SECONDS}-second
vertical reel (9:16) about a single artwork. Your input is a fact-checked archive entry in which
every claim carries a citation tag of the form [source: <source_id>], plus a list of available
image assets.

Output the Markdown brief and nothing else. Do not narrate your reasoning and do not preface
the brief with commentary. Begin your reply with the "# " title line.

STRICT RULES:
1. Every factual statement in the voiceover and captions must be supported by the archive entry.
   Carry the [source: <source_id>] tag through into the beat sheet so each beat is traceable.
2. Never introduce a fact, date, name, or attribution that is not in the archive entry. If the
   entry says something is unavailable or disputed, either omit it or frame it explicitly as
   disputed ("scholars still argue about...") — never state a disputed claim as settled.
3. Narrative shaping is allowed and expected: choose an angle, order the beats for tension,
   and write in a spoken, engaging register. Shaping means selection and phrasing, never invention.
4. Write the voiceover to be spoken aloud. Roughly 2.5 words per second — budget about
   {TARGET_RUNTIME_SECONDS * 2.5:.0f} words total across all beats. Short sentences. No semicolons.
5. Reference only images that appear in the supplied asset list, by their URL.

Produce the brief in exactly this structure, using Markdown headers:

# [Artwork Name] — Reel Brief

## 1. Hook
(The first 3 seconds. One or two spoken lines that create a question the viewer needs answered.
Give two alternative hooks labelled A and B so the reviewer can choose.)

## 2. Beat Sheet
(A Markdown table with columns: Beat | Seconds | Voiceover | Visual | Citation.
Four to six beats covering the full runtime, including the hook beat and a closing beat.)

## 3. Full Voiceover Script
(The complete narration as continuous spoken text, no citation tags, ready to be read or
sent to a text-to-speech engine. Include a word count and the estimated runtime.)

## 4. On-Screen Captions
(The text overlays, one per beat, each under 8 words.)

## 5. Visual Assets
(Which supplied image URL to use for each beat, and what to do with it — the specific detail
to punch in on, pan direction, or hold. If the asset list is empty, write exactly:
"No image assets retrieved — needs manual sourcing.")

## 6. Do Not Claim
(A bulleted list of the specific things a producer must NOT say about this artwork, drawn from
gaps and disputes in the archive entry — unavailable facts, contested attributions, contested
dates. This is the guardrail that keeps the reel accurate.)

## 7. Publishing Metadata
(Suggested title under 60 characters, a 2-sentence description, and 5 to 8 hashtags.)
"""


def missing_sections(brief_text: str) -> list:
    normalised = re.sub(r"[ \t]+", " ", brief_text)
    return [s for s in REQUIRED_SECTIONS if s.lower() not in normalised.lower()]


def build_user_content(entry_text: str, images: list) -> str:
    asset_lines = (
        json.dumps(images, indent=2, ensure_ascii=False)
        if images
        else "[]  (no image assets were retrieved)"
    )
    return (
        "ARCHIVE ENTRY (the only permitted source of facts):\n\n"
        f"{entry_text}\n\n"
        "AVAILABLE IMAGE ASSETS:\n\n"
        f"{asset_lines}\n\n"
        f"Write the {TARGET_RUNTIME_SECONDS}-second reel brief following the system instructions exactly."
    )


def call_nvidia_api(user_content: str, api_key: str) -> tuple[str, str]:
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
    completion = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,  # higher than the researcher: this stage needs voice, not just recall
        top_p=0.95,
        max_tokens=MAX_TOKENS,
        stream=False,
    )
    choice = completion.choices[0]
    return choice.message.content or "", (choice.finish_reason or "")


def main():
    artwork_name = require_artwork_name(sys.argv, "brief_writer.py")

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: NVIDIA_API_KEY environment variable not set.")

    base = artwork_dir(artwork_name)
    entry_path = base / DRAFT_ENTRY_FILENAME
    if not entry_path.exists():
        raise SystemExit(f"ERROR: {entry_path} not found. Run researcher.py first.")

    entry_text = read_text(entry_path)

    images = []
    raw_path = base / RAW_SOURCES_FILENAME
    if raw_path.exists():
        images = json.loads(read_text(raw_path)).get("images", [])

    print(f"Calling NVIDIA API ({NVIDIA_MODEL}) for the reel brief on '{artwork_name}'...")
    print(f"  {len(images)} image asset(s) available, target runtime {TARGET_RUNTIME_SECONDS}s")

    raw_content, finish_reason = call_nvidia_api(build_user_content(entry_text, images), api_key)
    brief_text = strip_reasoning(raw_content)

    if finish_reason == "length":
        raise SystemExit(
            "ERROR: the model hit the token limit before finishing the brief "
            f"(finish_reason=length, max_tokens={MAX_TOKENS}). Raise BRIEF_MAX_TOKENS."
        )

    if not brief_text:
        raise SystemExit("ERROR: the model returned no usable brief text after stripping reasoning.")

    gaps = missing_sections(brief_text)
    if gaps:
        raise SystemExit(
            "ERROR: the brief is missing required section(s): "
            + ", ".join(gaps)
            + "\nNot writing the brief."
        )

    out_path = base / CONTENT_BRIEF_FILENAME
    write_text(out_path, brief_text)

    print(f"Brief written to: {out_path} ({len(brief_text)} chars, all {len(REQUIRED_SECTIONS)} sections present)")


if __name__ == "__main__":
    main()

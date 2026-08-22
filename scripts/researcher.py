"""
Researcher — Stage 2 of the Research pipeline.
Reads raw_sources.json and calls an NVIDIA NIM model to produce the
structured archive entry (draft_entry.md), citing every claim to a source.

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
from pathlib import Path
from openai import OpenAI

NVIDIA_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"

SYSTEM_PROMPT = """You are a careful, precise research assistant building a permanent archive entry for a single artwork.

STRICT RULES — you must follow these exactly:
1. You will be given a JSON bundle of source snippets. Only state a fact if it appears in one of these snippets.
2. For every factual claim you make, append a citation tag in this exact format: [source: <source_id>]
3. If the provided sources do not contain information for a section, write exactly: "Not available in retrieved sources — needs manual research." Do not guess or infer.
4. Explicitly distinguish: (a) canonical/primary facts stated directly in a source, (b) traditions or interpretations the source itself frames as debated or attributed, (c) your own synthesis connecting two sourced facts (mark this clearly as "Synthesis:").
5. Never invent a date, name, measurement, or attribution that is not present in the sources.
6. Write in clear, plain prose. No flowery language.

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


def call_nvidia_api(source_bundle: dict, api_key: str) -> str:
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
        max_tokens=4096,
        # Thinking mode is off by default for this task — our job is
        # citation-tagged formatting, not deep multi-step reasoning.
        # To test whether it improves citation accuracy, uncomment:
        # extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096},
        stream=False,
    )

    return completion.choices[0].message.content


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return slug[:80]


def main():
    if len(sys.argv) < 2:
        print("Usage: python researcher.py \"<Artwork Name>\"")
        sys.exit(1)

    artwork_name = sys.argv[1]
    slug = slugify(artwork_name)

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("ERROR: NVIDIA_API_KEY environment variable not set.")
        sys.exit(1)

    raw_path = Path("archive") / slug / "raw_sources.json"
    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Run retriever.py first.")
        sys.exit(1)

    source_bundle = json.loads(raw_path.read_text())

    if not source_bundle.get("sources"):
        print("WARNING: source bundle is empty. The model will produce a low-confidence entry.")

    print(f"Calling NVIDIA API ({NVIDIA_MODEL}) for '{artwork_name}'...")
    entry_text = call_nvidia_api(source_bundle, api_key)

    out_path = Path("archive") / slug / "draft_entry.md"
    out_path.write_text(entry_text, encoding="utf-8")

    print(f"Draft written to: {out_path}")


if __name__ == "__main__":
    main()

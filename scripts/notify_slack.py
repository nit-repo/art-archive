"""
Notify Slack — Stage 3 trigger.

Posts the reel brief to a Slack channel via an Incoming Webhook so you can
read it and approve/edit/reject. The brief is what actually gets produced,
so the brief is what goes in front of the reviewer — the cited archive entry
is linked underneath for anyone who wants to check the receipts.

Usage:
    python notify_slack.py "Mérode Altarpiece"

Requires:
    Environment variable SLACK_WEBHOOK_URL (set as a GitHub Actions secret)
"""

import sys
import os
import json

import requests

from common import (
    CONTENT_BRIEF_FILENAME,
    DRAFT_ENTRY_FILENAME,
    RAW_SOURCES_FILENAME,
    artwork_dir,
    read_text,
    require_artwork_name,
    slugify,
)

# Slack truncates individual section blocks at 3000 characters.
SLACK_BLOCK_CHAR_LIMIT = 2900


def repo_file_link(slug: str, filename: str) -> str:
    """Build a link to a file in the repo, honouring the actual branch."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return ""
    ref = os.environ.get("GITHUB_REF_NAME") or "main"
    return f"https://github.com/{repo}/blob/{ref}/archive/{slug}/{filename}"


def pick_hero_image(base) -> dict | None:
    """The highest-value image to show alongside the brief."""
    raw_path = base / RAW_SOURCES_FILENAME
    if not raw_path.exists():
        return None
    images = json.loads(read_text(raw_path)).get("images", [])
    for role in ("full_resolution", "thumbnail", "detail"):
        for image in images:
            if image.get("role") == role and image.get("url"):
                return image
    return images[0] if images else None


def build_blocks(artwork_name: str, brief_text: str, slug: str, hero: dict | None) -> list:
    preview = brief_text[:SLACK_BLOCK_CHAR_LIMIT]
    if len(brief_text) > SLACK_BLOCK_CHAR_LIMIT:
        preview += f"\n\n… (truncated — full brief in the repo)"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Reel brief ready: {artwork_name}"[:150]},
        }
    ]

    if hero and hero.get("url"):
        blocks.append(
            {
                "type": "image",
                "image_url": hero["url"],
                "alt_text": artwork_name[:150],
            }
        )

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": preview}})

    brief_link = repo_file_link(slug, CONTENT_BRIEF_FILENAME)
    entry_link = repo_file_link(slug, DRAFT_ENTRY_FILENAME)
    if brief_link:
        links = f"<{brief_link}|Full brief>"
        if entry_link:
            links += f"  ·  <{entry_link}|Cited archive entry>"
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})

    return blocks


def main():
    artwork_name = require_artwork_name(sys.argv, "notify_slack.py")
    slug = slugify(artwork_name)

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise SystemExit("ERROR: SLACK_WEBHOOK_URL environment variable not set.")

    base = artwork_dir(artwork_name)
    brief_path = base / CONTENT_BRIEF_FILENAME
    if not brief_path.exists():
        raise SystemExit(f"ERROR: {brief_path} not found. Run brief_writer.py first.")

    brief_text = read_text(brief_path)
    hero = pick_hero_image(base)

    message = {
        "text": f"Reel brief ready for review: {artwork_name}",  # notification fallback
        "blocks": build_blocks(artwork_name, brief_text, slug, hero),
    }

    resp = requests.post(webhook_url, json=message, timeout=20)
    resp.raise_for_status()
    print(f"Posted reel brief for '{artwork_name}' to Slack.")


if __name__ == "__main__":
    main()

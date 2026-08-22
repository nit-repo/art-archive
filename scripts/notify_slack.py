"""
Notify Slack — Stage 3 trigger.
Posts the draft entry to a Slack channel via an Incoming Webhook so you
can read it and approve/edit/reject.

Usage:
    python notify_slack.py "Mérode Altarpiece"

Requires:
    Environment variable SLACK_WEBHOOK_URL (set as a GitHub Actions secret)
"""

import sys
import os
import re
import requests
from pathlib import Path

SLACK_MESSAGE_CHAR_LIMIT = 3000  # Slack truncates long messages; keep it readable


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return slug[:80]


def main():
    if len(sys.argv) < 2:
        print("Usage: python notify_slack.py \"<Artwork Name>\"")
        sys.exit(1)

    artwork_name = sys.argv[1]
    slug = slugify(artwork_name)

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: SLACK_WEBHOOK_URL environment variable not set.")
        sys.exit(1)

    draft_path = Path("archive") / slug / "draft_entry.md"
    if not draft_path.exists():
        print(f"ERROR: {draft_path} not found. Run researcher.py first.")
        sys.exit(1)

    draft_text = draft_path.read_text(encoding="utf-8")
    preview = draft_text[:SLACK_MESSAGE_CHAR_LIMIT]
    if len(draft_text) > SLACK_MESSAGE_CHAR_LIMIT:
        preview += "\n\n... (truncated — see full file in repo: archive/{}/draft_entry.md)".format(slug)

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    repo_link = f"https://github.com/{repo}/blob/main/archive/{slug}/draft_entry.md" if repo else ""

    message = {
        "text": f"*New draft ready for review: {artwork_name}*\n\n"
                f"```{preview}```\n\n"
                + (f"Full file: {repo_link}" if repo_link else "")
    }

    resp = requests.post(webhook_url, json=message, timeout=20)
    resp.raise_for_status()
    print(f"Posted draft for '{artwork_name}' to Slack.")


if __name__ == "__main__":
    main()

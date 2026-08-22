"""
Queue manager — picks the next artwork to research and marks it done.

The queue previously never advanced: the workflow read the first row whose
status was not "done", but nothing ever wrote "done" back, so every scheduled
run re-researched the same first row forever.

Usage:
    python queue_manager.py next              # prints the next artwork name
    python queue_manager.py done "<Artwork>"  # marks that row done
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import normalise

QUEUE_PATH = Path("queue") / "queue.csv"
FIELDNAMES = ["artwork_name", "status", "completed_at"]


def load_rows() -> list:
    if not QUEUE_PATH.exists():
        raise SystemExit(f"ERROR: {QUEUE_PATH} not found.")
    with QUEUE_PATH.open(encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if (row.get("artwork_name") or "").strip()]


def save_rows(rows: list) -> None:
    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (row.get(key) or "") for key in FIELDNAMES})


def next_artwork(rows: list) -> str | None:
    for row in rows:
        if (row.get("status") or "").strip().lower() != "done":
            return row["artwork_name"].strip()
    return None


def mark_done(rows: list, artwork_name: str) -> bool:
    target = normalise(artwork_name)
    for row in rows:
        if normalise(row.get("artwork_name", "")) == target:
            row["status"] = "done"
            row["completed_at"] = datetime.now(timezone.utc).isoformat()
            return True
    return False


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"next", "done"}:
        raise SystemExit('Usage: python queue_manager.py next | done "<Artwork Name>"')

    command = sys.argv[1]
    rows = load_rows()

    if command == "next":
        artwork = next_artwork(rows)
        if not artwork:
            raise SystemExit("QUEUE_EMPTY: every row in queue/queue.csv is marked done.")
        print(artwork)
        return

    artwork_name = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    if not artwork_name:
        raise SystemExit('Usage: python queue_manager.py done "<Artwork Name>"')

    if mark_done(rows, artwork_name):
        save_rows(rows)
        print(f"Marked '{artwork_name}' as done in {QUEUE_PATH}")
    else:
        # A manual workflow_dispatch run can name an artwork that is not queued.
        # That is not an error — there is simply nothing to mark.
        print(f"'{artwork_name}' is not in {QUEUE_PATH}; nothing to mark.")


if __name__ == "__main__":
    main()

#!/usr/bin/env sh
# macOS/Linux equivalent of start.bat
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "Install ffmpeg first"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
python -m app

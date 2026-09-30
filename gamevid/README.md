# gamevid

A local tool for making faceless gaming videos. You give it gameplay footage,
your take on a topic, and a voice recording. It gives back a captioned 9:16
video and a 16:9 video.

It runs entirely on your PC at <http://localhost:8000>. No account or API key
is needed.

## Setup (Windows 10)

1. Install **Python 3.10+** from <https://www.python.org/downloads/>. During
   install, tick "Add python.exe to PATH".
2. Install **ffmpeg**: open PowerShell and run `winget install Gyan.FFmpeg`.
   Then close and reopen PowerShell.
3. Double-click **`start.bat`**.

   The first run creates a Python environment and installs packages, which
   takes a few minutes. After that, it opens your browser.

The first time you run captions, the Whisper model (about 500 MB for
`small`) downloads once. After that, captions work offline.

On macOS or Linux, run `./start.sh` instead.

## Status

| Build step | State |
|---|---|
| 1. Timing model, captions, assemble | ✅ done |
| 2. Script stage + gates (`llm.py`) | next |
| 3. Voice (TTS) | — |
| 4. UI polish | — |
| 5. Metadata and thumbnail export | — |

Until step 2 is built, you type script sections yourself, then:

1. **Narration**: upload one take of the whole script.
2. **Captions**: Whisper transcribes the take and matches it to your script.
   This finds where each section starts and makes word-level captions. The
   captions use your script's spelling, so game names come out right.
3. **Footage**: upload footage. On the preview player, press **I** to set the
   in point and **O** to set the out point, then add the clip to a section.
   - A bar shows how much footage a section needs against how much you've
     marked.
   - If you've marked less footage than the section's narration lasts, your
     clips loop in order and you get a warning.
4. **Render**: outputs 9:16 and/or 16:9 files.
   - Adds music from `music/`, ducked under your voice.
   - Burns in the captions, with the current word highlighted.
   - For 9:16 you can choose crop (with a per-clip position slider) or blur
     fill.

## Where things live

- **`projects/<id>/`**: one folder per video.
  - `project.json` is the single source of truth.
  - `footage/` holds your originals and `proxies/` holds browser preview
    copies.
  - `audio/`, `captions/` and `renders/` hold the stage outputs.
- **`music/`**: your royalty-free tracks. Add a `.license.txt` next to each
  one.
- **`fonts/`**: optional caption fonts.
- **`.env`**: settings. Copy `.env.example`; `start.bat` does this for you.

Cleanup: only the newest `KEEP_RENDERS` renders are kept per project (2 by
default). Cached clip pieces that the latest render didn't use are deleted.

## Development

```
pip install -r requirements-dev.txt
python -m pytest
```

The render test builds real videos with ffmpeg, so ffmpeg must be on PATH.

# gamevid — faceless gaming video tool

A local, single-user tool for making faceless gaming videos. Python backend
(FastAPI) plus a plain HTML frontend at `localhost:8000`, started with one
command. No hosting and no auth. API keys live in `.env`.

The target machine is **Windows 10**: one-command start via `start.bat`, and ffmpeg from
`winget install Gyan.FFmpeg`. Keep everything Windows-safe: no shell pipes,
`pathlib` everywhere, and ffmpeg filter paths relative to the project dir or
escaped with `ff.filter_path()`.

Formats: 9:16 is the priority (Shorts and Reels); 16:9 long-form comes later.
Both outputs are supported from day one.

## Inputs (from the user)

- Gameplay footage
- A topic
- 3–5 bullets giving the user's own take
- Optional: the user's own voice recording

## Hard rules

- **Never state a number without flagging it for verification.** Every
  number, date, stat, price, frame count, patch version or percentage in a
  script goes into `facts_to_verify.txt`. No exceptions, including numbers
  that look like common knowledge.
- The user's bullets are the substance of the video. The LLM organises and
  phrases the user's take. It does not invent opinions, leaks or claims.
- Music comes only from the local `music/` folder, and every track there must
  be royalty-free.
- No auto-upload. Export ends at a download.
- No keys are strictly required. With a free NVIDIA key or manual paste mode,
  plus local Whisper and edge-tts, everything runs at no cost.

## Channel voice

> TODO (user): fill in the channel name, the games covered, the target
> audience, the tone (e.g. dry, hype, analytical), words and phrases to avoid,
> and whether to swear.

Defaults until filled in: a conversational first-person voice from someone who
plays the game. Short sentences. No "In this video we will…" openers. No
clickbait promises that the video doesn't pay off.

## Script template

Every script is split into numbered sections that follow this template:

1. **Hook** (≤ 3 s for shorts, ≤ 15 s for long-form): the most surprising or
   contrarian point from the user's bullets. No greeting.
2. **Body** (one section per bullet, usually 3–5): each section covers a
   claim, then evidence or an example, then why it matters.
3. **Payoff**: answers the question or tension the hook set up.
4. **CTA**: one line and one ask (e.g. comment, follow). Never a list of asks.

## LLM provider

- All LLM calls go through a single `llm.py` wrapper.
- The provider is set in `.env` with `LLM_PROVIDER=nvidia|anthropic`.
- **Default:** NVIDIA build.nvidia.com, via the OpenAI-compatible endpoint
  `https://integrate.api.nvidia.com/v1`, with an `nvapi-` key and a model name
  read from `.env`.
- **Alternative:** the Anthropic API.
- Handle rate limits (about 40 RPM on the free tier) with backoff and retries.
- Ask the model for JSON output and validate it. Open models are less reliable
  at producing correct structure, so on a validation failure, retry with the
  validation error included in the prompt.
- Log token usage for every call so the UI can display cost.
- **Manual paste mode** is the fallback for the script stage: the tool shows
  the prompt, the user pastes it into any chat UI, then pastes the JSON back.

## Pipeline

There is one folder per project, and each stage can be re-run on its own.

1. **script**: the LLM turns the user's bullets into `script.txt` and
   `facts_to_verify.txt` (numbers, dates, patch versions). It includes a
   "patch version checked" field. The script is split into numbered sections.
2. **GATE 1**: the UI shows the editable script and the fact checklist.
   Approve stays locked until every fact is ticked.
3. **voice**: either an upload of the user's recording, or TTS (edge-tts by
   default, ElevenLabs optional) with a preview. Stores the audio duration of
   each section.
4. **captions**: word-level subtitles from Whisper. Defaults to local
   faster-whisper (small model, CPU-friendly), with an optional API mode.
5. **footage**: the user marks in/out timestamps for each script section in
   the UI. The tool only trims and orders clips. It does no automatic matching.
6. **assemble**: ffmpeg cuts the footage to each section's audio duration,
   ducks royalty-free music, burns in captions, and outputs both 9:16 and 16:9.
7. **GATE 2**: a video player for watching the full render. Approve unlocks
   export.
8. **export**: title, description, tags and thumbnail text ideas, then a
   download. File metadata is stripped. No auto-upload.

## Design rules

- **Timing model first.** A single `project.json` (sections, audio durations,
  clip in/out points, styles) is the only source of truth for both preview and
  render.
- A background job queue with progress, retries and resumable stages.
- Show the cost of each video (tokens and API usage). Free-tier calls show as
  $0.
- A cleanup rule for raw footage and old renders.

## Build order

1. Timing model, assemble and captions
2. Script stage and gates (with the `llm.py` wrapper)
3. Voice
4. UI polish
5. Metadata and thumbnail step

## Design decisions (confirmed)

### Timing model

- **Narration audio is the master clock.** Video bends to fit the audio,
  never the other way around.
- `project.json` stores inputs only: section text, the measured audio duration
  of each section (from ffprobe, never estimated once audio exists), clips as
  `{source, in, out, crop_x}` lists, and styles. Absolute times are
  **derived** by one pure function, `build_timeline(project)`. The preview
  API and the ffmpeg renderer both call this function, so they cannot
  disagree.
- Section boundaries are computed in integer frames from cumulative time at
  the output fps, which prevents rounding drift across sections.
- Every stage records a hash of its inputs. Editing upstream (for example,
  changing section 3's text) marks the downstream stages stale for that
  section only.
- **Voice:** there is one take for the whole script. The captions stage
  transcribes it, aligns it to the script, and derives each section's start
  (the midpoint of the pause between sections). The user can nudge a
  boundary manually; manual boundaries survive re-alignment.
- Before any voice exists, durations are estimated at about 150 wpm and marked
  `estimated: true` in the UI.
- Captions are word timestamps from each section's audio plus the section
  offset. The word text is aligned back to the script (difflib), so game
  names and jargon are spelled as they are in the script rather than as
  Whisper heard them.

### Clip matching (manual in/out)

- **9:16 framing:** both modes are supported, chosen per project:
  - `crop`, with a per-clip `crop_x` position
  - `blur` fill
- Browser scrubbing uses low-res H.264 proxies of the footage. Browsers can't
  play MKV/HEVC reliably, so the proxy is needed. The final render cuts from
  the originals.
- A section can have several clips. The UI shows the marked duration against
  the required duration as a green/amber/red bar.
- **Too long:** trim from the end.
- **Too short:** the marked clips loop in order until the section is filled.
  This is flagged as a warning in the UI and in the render output, never
  silently.
- **No clips:** black filler, with a warning.
- Cuts are frame-accurate: the footage is re-encoded, not stream-copied.

### Platform policy

- The goal is for the content to actually be original and transformative.
  The tool does not try to fool classifiers. It has **no** features whose
  purpose is evading detection, such as random jitter or fingerprint
  scrambling.
- The user's bullets are mandatory, and Gate 1 requires human edits and fact
  review.
- Footage provenance: each source file is tagged as "own capture" or "other
  (with licence note)". Export warns about untagged footage.
- The own voice option is prominent. The export checklist includes the
  AI-disclosure decision (whether the platform's synthetic-content label
  applies).
- No batch or bulk mode and no auto-upload. The tool makes one deliberate
  video at a time.
- Music: each track in `music/` needs a sidecar licence file. Export lists
  the track and its licence for the description.
- Per-game notes on the publisher's video and monetisation policy are
  checked at export.

## Code map

| File | Role |
|---|---|
| `app/models.py` | `project.json` schema (pydantic) |
| `app/timeline.py` | `build_timeline()`: the only place times, frames and pieces are derived |
| `app/align.py` | Whisper transcript ↔ script alignment and section starts |
| `app/captions.py` | Transcription (local or API) and `.ass` generation |
| `app/stages.py` | Stages, their input hashes (stale detection), render and cleanup |
| `app/jobs.py` | Background queue: one worker, persisted, retries, resumes on restart |
| `app/ff.py` | ffmpeg/ffprobe wrappers |
| `app/main.py` | FastAPI routes |
| `app/static/` | Plain HTML/JS UI |

Run the tests with `python -m pytest`. The render test needs ffmpeg.

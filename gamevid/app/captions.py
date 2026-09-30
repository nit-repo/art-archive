"""Word-level captions: transcribe the narration, then write styled .ass files.

Transcription is cached by narration hash + model, so restyling captions never
re-runs Whisper. The .ass files are regenerated at render time from words.json.
"""

import json
from pathlib import Path

from . import config
from .align import Word
from .models import CaptionStyle

_model_cache = {}


def transcribe(audio: Path) -> list[dict]:
    """Return [{'word', 'start', 'end'}] for the whole recording."""
    if config.WHISPER_MODE == "api":
        return _transcribe_api(audio)
    return _transcribe_local(audio)


def _transcribe_local(audio: Path) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper isn't installed: pip install faster-whisper") from e
    model = _model_cache.get(config.WHISPER_MODEL)
    if model is None:
        try:
            model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        except Exception as e:  # noqa: BLE001 — usually a failed first-time download
            raise RuntimeError(
                f"Couldn't load the Whisper '{config.WHISPER_MODEL}' model. The first run downloads it "
                f"from huggingface.co (~500 MB for 'small'), so check your internet connection. ({e})"
            ) from e
        _model_cache[config.WHISPER_MODEL] = model
    segments, _info = model.transcribe(str(audio), word_timestamps=True, vad_filter=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    return words


def _transcribe_api(audio: Path) -> list[dict]:
    import requests

    if not config.OPENAI_API_KEY:
        raise RuntimeError("WHISPER_MODE=api needs OPENAI_API_KEY in .env")
    with open(audio, "rb") as f:
        r = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            data={"model": "whisper-1", "response_format": "verbose_json",
                  "timestamp_granularities[]": "word"},
            files={"file": (audio.name, f)},
            timeout=600,
        )
    r.raise_for_status()
    return [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
            for w in r.json().get("words", [])]


# ---------------------------------------------------------------- .ass output

def _ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[Word], max_words: int, max_gap: float = 0.6) -> list[list[Word]]:
    """Group words into on-screen lines: break on count, punctuation, pauses and sections."""
    chunks, cur = [], []
    for w in words:
        if cur and (
            len(cur) >= max_words
            or w.section != cur[-1].section
            or w.start - cur[-1].end > max_gap
            or cur[-1].text[-1:] in ".!?;:,"
        ):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[Word], style: CaptionStyle, fmt: str, width: int, height: int) -> str:
    vertical = fmt == "vertical"
    size = style.size_vertical if vertical else style.size_horizontal
    max_words = style.max_words_vertical if vertical else style.max_words_horizontal
    margin = int(height * (style.margin_vertical if vertical else style.margin_horizontal))
    base, hi = _ass_color(style.color), _ass_color(style.highlight)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{style.font},{size},{base},{base},{_ass_color(style.outline_color)},&H80000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,1,{style.outline},2,2,{int(width * 0.08)},{int(width * 0.08)},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chunks = chunk_words(words, max_words)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else chunk[-1].end + 0.5
        chunk_end = min(next_start, chunk[-1].end + 0.5)
        texts = [_escape(w.text.upper() if style.uppercase else w.text) for w in chunk]
        # One event per word so the word being spoken is highlighted.
        for wi, w in enumerate(chunk):
            start = w.start if wi else chunk[0].start
            end = chunk[wi + 1].start if wi + 1 < len(chunk) else chunk_end
            if end <= start:
                continue
            body = " ".join(
                f"{{\\c{hi}}}{t}{{\\c{base}}}" if k == wi else t for k, t in enumerate(texts)
            )
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{body}")
    return header + "\n".join(lines) + "\n"


def load_words(path: Path) -> list[Word]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Word(**w) for w in data["words"]]

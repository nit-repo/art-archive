"""Align a Whisper transcript to the script.

Two jobs:
1. Split a one-take recording into sections: each section's start on the
   narration is found from where its words were spoken.
2. Caption text: captions use the script's spelling (game names, jargon) with
   Whisper's timing. Words that were spoken but aren't in the script (ad-libs)
   are kept; script words that were never spoken are dropped and reported.
"""

import difflib
import re
from dataclasses import asdict, dataclass

_NORM = re.compile(r"[^\w]+", re.UNICODE)


def norm(word: str) -> str:
    return _NORM.sub("", word.lower())


@dataclass
class Word:
    text: str
    start: float
    end: float
    section: int  # index into project.sections


@dataclass
class Alignment:
    words: list[Word]
    section_starts: list[float]
    match_ratio: float
    skipped: list[str]  # script words not found in the recording
    extra: list[str]    # spoken words not in the script

    def to_dict(self) -> dict:
        return asdict(self)


def script_tokens(section_texts: list[str]) -> list[tuple[str, int]]:
    return [(w, i) for i, text in enumerate(section_texts) for w in text.split()]


def align(section_texts: list[str], spoken: list[dict]) -> Alignment:
    """spoken: [{'word': str, 'start': float, 'end': float}, ...] from Whisper."""
    script = script_tokens(section_texts)
    spoken = [w for w in spoken if norm(w["word"])]
    a = [norm(w) for w, _ in script]
    b = [norm(w["word"]) for w in spoken]

    out: list[Word] = []
    skipped, extra, equal = [], [], 0
    last_section = 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                text, sec = script[i1 + k]
                w = spoken[j1 + k]
                out.append(Word(text, w["start"], w["end"], sec))
                last_section = sec
            equal += i2 - i1
        elif op == "replace":
            # Misheard words: keep the script's spelling, spread over the spoken span.
            t0, t1 = spoken[j1]["start"], spoken[j2 - 1]["end"]
            chunk = script[i1:i2]
            weights = [max(1, len(w)) for w, _ in chunk]
            total, acc = sum(weights), 0
            for (text, sec), wt in zip(chunk, weights):
                s = t0 + (t1 - t0) * acc / total
                acc += wt
                out.append(Word(text, s, t0 + (t1 - t0) * acc / total, sec))
                last_section = sec
        elif op == "delete":
            skipped.extend(w for w, _ in script[i1:i2])
            if i2 < len(script):
                last_section = script[i1][1]
        elif op == "insert":
            for w in spoken[j1:j2]:
                out.append(Word(w["word"].strip(), w["start"], w["end"], last_section))
                extra.append(w["word"].strip())

    starts = _section_starts(out, len(section_texts))
    ratio = equal / len(a) if a else 0.0
    return Alignment(out, starts, round(ratio, 3), skipped, extra)


def _section_starts(words: list[Word], n_sections: int) -> list[float]:
    """Cut between sections at the midpoint of the pause between them."""
    first, last = {}, {}
    for w in words:
        first.setdefault(w.section, w.start)
        last[w.section] = w.end
    missing = [i + 1 for i in range(n_sections) if i not in first]
    if missing:
        raise ValueError(
            f"Couldn't find section(s) {missing} in the recording. "
            "Check the recording matches the script, or set those boundaries manually."
        )
    starts = [0.0]
    for i in range(1, n_sections):
        prev_end, this_start = last[i - 1], first[i]
        starts.append(round((prev_end + this_start) / 2 if this_start > prev_end else this_start, 3))
    return starts

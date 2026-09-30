"""Derive the frame-exact timeline from project.json.

This is the only place that turns section timings and clip in/out points into
concrete video pieces. The preview UI and the renderer both call it.

Rules:
- Narration audio is the master clock; video bends to fit it.
- Section boundaries are computed in integer frames from absolute times, so
  rounding never accumulates across sections.
- If a section's marked footage is shorter than its audio, the clips loop in
  order until the section is filled (flagged as a warning).
- Without narration, durations are estimated at ~150 wpm and flagged.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional

from .models import Project

WORDS_PER_SECOND = 2.5  # ~150 wpm
MIN_ESTIMATED_SECONDS = 1.5


@dataclass
class Piece:
    source: Optional[str]  # None = black filler (no footage marked)
    t_in: float
    frames: int
    crop_x: float = 0.5
    looped: bool = False


@dataclass
class SectionSpan:
    id: str
    index: int
    start_frame: int
    end_frame: int
    start: float
    end: float
    estimated: bool
    marked_seconds: float
    pieces: list[Piece] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return self.end_frame - self.start_frame


@dataclass
class Timeline:
    fps: int
    total_frames: int
    duration: float
    estimated: bool
    sections: list[SectionSpan]

    def to_dict(self) -> dict:
        d = asdict(self)
        for s, span in zip(d["sections"], self.sections):
            s["frames"] = span.frames
            s["duration"] = span.frames / self.fps
        return d

    @property
    def warnings(self) -> list[str]:
        return [f"Section {s.index + 1}: {w}" for s in self.sections for w in s.warnings]


def estimate_seconds(text: str) -> float:
    return max(MIN_ESTIMATED_SECONDS, len(text.split()) / WORDS_PER_SECOND)


def section_starts(project: Project) -> tuple[list[float], float, bool]:
    """Start time of every section plus the total duration.

    Uses aligned/manual narration timings when narration exists and every
    section has one; otherwise falls back to word-count estimates.
    """
    secs = project.sections
    if project.narration and secs and all(s.audio for s in secs):
        starts = [0.0] + [s.audio.start for s in secs[1:]]
        total = project.narration.duration
        for a, b in zip(starts, starts[1:] + [total]):
            if b <= a:
                raise ValueError("Section timings must increase and stay inside the narration")
        return starts, total, False

    starts, t = [], 0.0
    for s in secs:
        starts.append(t)
        t += estimate_seconds(s.text)
    return starts, t, True


def _fill_pieces(section, frames: int, fps: int) -> tuple[list[Piece], float, list[str]]:
    usable = []
    for c in section.clips:
        n = int((c.t_out - c.t_in) * fps)
        if n >= 1:
            usable.append((c, n))
    marked = sum(n for _, n in usable) / fps

    if not usable:
        return [Piece(None, 0.0, frames)], 0.0, ["no footage marked (black filler)"]

    pieces, remaining, i, lap = [], frames, 0, 0
    while remaining > 0:
        clip, avail = usable[i]
        take = min(avail, remaining)
        pieces.append(Piece(clip.source, clip.t_in, take, clip.crop_x, looped=lap > 0))
        remaining -= take
        i += 1
        if i == len(usable):
            i, lap = 0, lap + 1

    warnings = []
    needed = frames / fps
    if marked + 1e-9 < needed:
        warnings.append(f"footage short by {needed - marked:.1f}s, looping clips")
    return pieces, marked, warnings


def build_timeline(project: Project) -> Timeline:
    fps = project.styles.fps
    starts, total, estimated = section_starts(project)
    total_frames = round(total * fps)
    bounds = [round(s * fps) for s in starts] + [total_frames]

    spans = []
    for i, sec in enumerate(project.sections):
        f0, f1 = bounds[i], bounds[i + 1]
        if f1 <= f0:
            f1 = f0 + 1  # a section always gets at least one frame
            bounds[i + 1] = f1
        pieces, marked, warnings = _fill_pieces(sec, f1 - f0, fps)
        spans.append(SectionSpan(
            id=sec.id, index=i, start_frame=f0, end_frame=f1,
            start=f0 / fps, end=f1 / fps, estimated=estimated,
            marked_seconds=round(marked, 3), pieces=pieces, warnings=warnings,
        ))

    total_frames = bounds[-1] if spans else 0
    return Timeline(fps, total_frames, total_frames / fps, estimated, spans)

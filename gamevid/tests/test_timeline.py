import pytest

from app.models import Clip, Narration, Project, Section, SectionAudio
from app.timeline import build_timeline


def project(sections, duration=None, fps=30):
    p = Project(id="t", title="t", sections=sections)
    p.styles.fps = fps
    if duration is not None:
        p.narration = Narration(file="audio/narration.wav", duration=duration, sha="x")
    return p


def sec(sid, start=None, clips=(), text="one two three"):
    return Section(id=sid, text=text, clips=list(clips),
                   audio=SectionAudio(start=start) if start is not None else None)


def test_sections_are_contiguous_and_frame_exact():
    p = project([sec("a", 0), sec("b", 3.333), sec("c", 7.01)], duration=10.0)
    tl = build_timeline(p)
    assert tl.total_frames == 300
    assert [s.start_frame for s in tl.sections] == [0, 100, 210]
    assert [s.end_frame for s in tl.sections] == [100, 210, 300]
    for s in tl.sections:
        assert sum(pc.frames for pc in s.pieces) == s.frames


def test_no_drift_over_many_sections():
    starts = [i * 1.0333 for i in range(40)]
    p = project([sec(f"s{i}", t) for i, t in enumerate(starts)], duration=41.4)
    tl = build_timeline(p)
    assert tl.sections[-1].end_frame == round(41.4 * 30)
    assert sum(s.frames for s in tl.sections) == tl.total_frames


def test_short_footage_loops_clips_in_order():
    clips = [Clip(source="a.mp4", t_in=10, t_out=11), Clip(source="b.mp4", t_in=0, t_out=0.5)]
    p = project([sec("a", 0, clips)], duration=4.0)
    s = build_timeline(p).sections[0]
    assert [(pc.source, pc.frames, pc.looped) for pc in s.pieces] == [
        ("a.mp4", 30, False), ("b.mp4", 15, False),
        ("a.mp4", 30, True), ("b.mp4", 15, True),
        ("a.mp4", 30, True),
    ]
    assert s.marked_seconds == 1.5
    assert "looping" in s.warnings[0]


def test_long_footage_is_trimmed_from_the_end():
    clips = [Clip(source="a.mp4", t_in=5, t_out=20), Clip(source="b.mp4", t_in=0, t_out=9)]
    s = build_timeline(project([sec("a", 0, clips)], duration=2.0)).sections[0]
    assert [(pc.source, pc.t_in, pc.frames) for pc in s.pieces] == [("a.mp4", 5, 60)]
    assert s.warnings == []


def test_no_clips_gives_black_filler():
    s = build_timeline(project([sec("a", 0)], duration=2.0)).sections[0]
    assert s.pieces[0].source is None and s.pieces[0].frames == 60


def test_estimates_without_narration():
    p = project([sec("a", text="w " * 25), sec("b", text="w " * 5)])
    tl = build_timeline(p)
    assert tl.estimated
    assert tl.sections[0].frames == 300  # 25 words at 2.5 words/s = 10 s
    assert tl.sections[1].start_frame == 300


def test_rejects_out_of_order_timings():
    p = project([sec("a", 0), sec("b", 5), sec("c", 4)], duration=10)
    with pytest.raises(ValueError):
        build_timeline(p)

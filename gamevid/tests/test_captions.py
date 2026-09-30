import pytest

from app.align import Word, align
from app.captions import build_ass, chunk_words
from app.models import CaptionStyle


def spoken(*items):
    return [{"word": w, "start": s, "end": e} for w, s, e in items]


def test_align_uses_script_spelling_and_splits_sections():
    texts = ["Elden Ring is back.", "Patch 1.12 nerfed bleed."]
    words = spoken(
        ("elden", 0.0, 0.3), ("ring", 0.3, 0.6), ("is", 0.6, 0.7), ("back.", 0.7, 1.0),
        ("patch", 2.0, 2.3), ("one", 2.3, 2.5), ("twelve", 2.5, 2.8),
        ("nerfed", 2.8, 3.1), ("bleed", 3.1, 3.5),
    )
    a = align(texts, words)
    assert [w.text for w in a.words] == ["Elden", "Ring", "is", "back.", "Patch", "1.12", "nerfed", "bleed."]
    assert a.section_starts == [0.0, 1.5]  # midpoint of the 1.0 → 2.0 pause
    one_twelve = a.words[5]
    assert (one_twelve.start, one_twelve.end) == (2.3, 2.8)
    assert a.skipped == [] and a.extra == []


def test_align_keeps_adlibs_and_reports_skipped_words():
    a = align(["this is the script text"],
              spoken(("this", 0, .2), ("is", .2, .4), ("uh", .4, .5), ("the", .5, .6), ("text", .8, 1)))
    assert [w.text for w in a.words] == ["this", "is", "uh", "the", "text"]
    assert a.extra == ["uh"] and a.skipped == ["script"]


def test_align_fails_clearly_when_a_section_is_missing():
    with pytest.raises(ValueError, match=r"\[2\]"):
        align(["hello there", "completely different words"], spoken(("hello", 0, .5), ("there", .5, 1)))


def test_chunks_break_on_punctuation_sections_and_count():
    ws = [Word("One,", 0, .2, 0), Word("two", .2, .4, 0), Word("three", .4, .6, 0),
          Word("four", .6, .8, 0), Word("five", .8, 1, 0), Word("six", 1, 1.2, 1)]
    assert [[w.text for w in c] for c in chunk_words(ws, 3)] == [
        ["One,"], ["two", "three", "four"], ["five"], ["six"]]


def test_ass_highlights_one_word_per_event():
    ws = [Word("hi", 0, .5, 0), Word("{there}", .5, 1, 0)]
    ass = build_ass(ws, CaptionStyle(), "vertical", 1080, 1920)
    events = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert len(events) == 2
    assert "PlayResY: 1920" in ass
    assert "(there)" in events[1]  # braces in text would be read as ASS override tags
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50")

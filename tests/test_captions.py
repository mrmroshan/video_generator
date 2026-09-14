import pytest
from renderer.captions import make_karaoke_ass, make_ass, _fmt_time, STYLES, KARAOKE_STYLES


def test_fmt_time_fp_rounding():
    """1.20s must not become 1.19s due to float precision."""
    assert _fmt_time(1.20) == "0:00:01.20"
    assert _fmt_time(0.40) == "0:00:00.40"
    assert _fmt_time(3.60) == "0:00:03.60"
    assert _fmt_time(0.0)  == "0:00:00.00"


def test_make_karaoke_ass_empty_words_no_crash():
    """Empty word list must return valid ASS, not raise IndexError."""
    result = make_karaoke_ass([], total_duration=5.0)
    assert isinstance(result, str)
    assert "[Script Info]" in result


def test_make_karaoke_ass_whitespace_words_no_crash():
    """All-whitespace words filter to empty — must not crash."""
    result = make_karaoke_ass([{"word": "  ", "start": 0.0, "end": 0.5}], total_duration=5.0)
    assert isinstance(result, str)


def test_make_karaoke_ass_gap_coverage():
    """Word display extends to next word start (no blank during speech pause)."""
    import re
    words = [
        {"word": "here.", "start": 1.04, "end": 1.30},
        {"word": "You",   "start": 1.70, "end": 1.82},
    ]
    ass = make_karaoke_ass(words, 5.0, audio_offset=0.0)
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    here_active = next(l for l in lines if re.search(r'\}here\.\{', l))
    end_time = here_active.split(",")[2]
    assert end_time == "0:00:01.70", f"Expected 0:00:01.70, got {end_time}"


def test_all_static_styles_produce_valid_ass():
    for style in STYLES:
        ass = make_ass("Test caption", 5.0, style)
        assert "[V4+ Styles]" in ass
        assert "Dialogue:" in ass


def test_all_karaoke_styles_valid_ass():
    words = [{"word": "hello", "start": 0.0, "end": 0.5},
             {"word": "world", "start": 0.5, "end": 1.0}]
    for style in KARAOKE_STYLES:
        ass = make_karaoke_ass(words, 2.0, style_name=style)
        assert "Dialogue:" in ass

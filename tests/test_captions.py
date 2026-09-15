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
    """Gaps <= MAX_HOLD bridge to next word; gaps > MAX_HOLD release early (no freeze)."""
    import re
    MAX_HOLD = 0.35

    # Short gap (0.26s) — should bridge to next word start
    words_short = [
        {"word": "here.", "start": 1.04, "end": 1.30},
        {"word": "You",   "start": 1.56, "end": 1.70},
    ]
    ass = make_karaoke_ass(words_short, 5.0, audio_offset=0.0)
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    here = next(l for l in lines if re.search(r'\}here\.\{', l))
    end_time = here.split(",")[2]
    assert end_time == "0:00:01.56", f"Short gap should bridge: expected 0:00:01.56, got {end_time}"

    # Long gap (0.40s > MAX_HOLD) — should release at word_end + MAX_HOLD, not freeze
    words_long = [
        {"word": "here.", "start": 1.04, "end": 1.30},
        {"word": "You",   "start": 1.70, "end": 1.82},
    ]
    ass = make_karaoke_ass(words_long, 5.0, audio_offset=0.0)
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    here = next(l for l in lines if re.search(r'\}here\.\{', l))
    end_time = here.split(",")[2]
    expected = f"0:00:01.{int((1.30 + MAX_HOLD) * 100) % 100:02d}"
    # disp_end = 1.30 + 0.35 = 1.65
    assert end_time == "0:00:01.65", f"Long gap should cap: expected 0:00:01.65, got {end_time}"
    assert end_time != "0:00:01.70", "Caption must NOT bridge full gap — that causes the freeze bug"


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


# ── parse_caption_edit tests ─────────────────────────────────────────────────

def _orig_words(n=4):
    return [{"word": f"w{i}", "start": i*0.5, "end": i*0.5+0.4} for i in range(n)]


def test_parse_caption_edit_one_to_one():
    """Same word count: timing preserved exactly, text replaced."""
    from renderer.captions import parse_caption_edit
    orig = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    result = parse_caption_edit("hi there", orig)
    assert len(result) == 2
    assert result[0]["word"] == "hi"    and result[0]["start"] == 0.0
    assert result[1]["word"] == "there" and result[1]["end"]   == 1.0


def test_parse_caption_edit_fewer_words_no_reversal():
    """Merging words: start <= end for every result word."""
    from renderer.captions import parse_caption_edit
    orig = _orig_words(5)
    result = parse_caption_edit("fewer words", orig)
    assert len(result) == 2
    for r in result:
        assert r["start"] <= r["end"], f"Reversed timestamp: {r}"


def test_parse_caption_edit_more_words_no_exceed_slot():
    """Splitting a word: end must not exceed original slot end."""
    from renderer.captions import parse_caption_edit
    orig = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    result = parse_caption_edit("hel lo world", orig)
    assert len(result) == 3
    for r in result:
        assert r["end"] <= 1.0,  f"Exceeds slot: {r}"
        assert r["start"] <= r["end"], f"Reversed: {r}"


def test_parse_caption_edit_phrase_break_flags():
    """Newlines produce phrase_break=True on first word of each subsequent line."""
    from renderer.captions import parse_caption_edit
    orig = [{"word": w, "start": i*0.3, "end": i*0.3+0.25}
            for i, w in enumerate(["did", "you", "know", "this", "fact"])]
    result = parse_caption_edit("did you know\nthis fact", orig)
    breaks = [r for r in result if r.get("phrase_break")]
    assert len(breaks) == 1
    assert breaks[0]["word"] == "this"


def test_make_ass_playres_matches_dimensions():
    """PlayResX/Y must match actual dimensions — not hardcoded 1920x1080."""
    ass = make_ass("test", 5.0, width=1280, height=720)
    assert "PlayResX: 1280" in ass
    assert "PlayResY: 720" in ass
    assert "1920" not in ass
    assert "1080" not in ass

    ass_v = make_ass("test", 5.0, width=720, height=1280)
    assert "PlayResX: 720" in ass_v
    assert "PlayResY: 1280" in ass_v

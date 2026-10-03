import pytest

from fileconverter.options import Options, applicable, encoder_quality, format_time, parse_time
from fileconverter.presets import BUILTIN_BY_ID


@pytest.mark.parametrize("pid,expected", [
    ("audio:mp3", 2), ("audio:aac", "192k"), ("audio:ogg", 5), ("audio:opus", "128k"),
    ("video:mp4", 20), ("video:mp4-small", 28), ("video:webm", 32),
    ("image:jpg", 90), ("image:webp", 90), ("image:avif", 70),
])
def test_builtin_defaults_reproduce_bash_settings(pid, expected):
    p = BUILTIN_BY_ID[pid]
    assert encoder_quality(p.format, Options.from_dict(p.options).quality) == expected


def test_quality_endpoints():
    assert encoder_quality("mp4", 100) == 16 and encoder_quality("mp4", 0) == 35
    assert encoder_quality("aac", 100) == "320k" and encoder_quality("jpg", 0) == 1


def test_lossless_and_remux_hide_quality_and_trim():
    assert "quality" not in applicable(BUILTIN_BY_ID["audio:flac"])
    a = applicable(BUILTIN_BY_ID["video:mkv"])
    assert {"quality", "trim_start", "max_height"}.isdisjoint(a) and "strip_metadata" in a
    assert applicable(BUILTIN_BY_ID["office:pdf"]) == frozenset()


def test_pdf_jpg_offers_quality():
    assert applicable(BUILTIN_BY_ID["pdf:jpg"]) == frozenset({"pdf_dpi", "quality"})


def test_pdf_pages_offer_dpi_only():
    assert applicable(BUILTIN_BY_ID["pdf:png"]) == frozenset({"pdf_dpi"})
    assert Options.from_dict(BUILTIN_BY_ID["pdf:png"].options).pdf_dpi == 150


@pytest.mark.parametrize("text,sec", [
    ("", None), ("90", 90), ("1:30", 90), ("1:00:05", 3605), ("0:01.5", 1.5),
])
def test_parse_time(text, sec):
    assert parse_time(text) == sec


@pytest.mark.parametrize("bad", ["1:xx", "1:2:3:4", "-5", "1:75"])
def test_parse_time_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_format_time():
    assert format_time(65) == "1:05" and format_time(3723) == "1:02:03"
    assert format_time(1.5) == "0:01.5" and format_time(0.9996) == "0:01"


def test_resize_validation():
    assert Options.from_dict({"resize": "50%"}).resize == "50%"
    assert Options.from_dict({"resize": "1600x1600"}).resize == "1600x1600"
    with pytest.raises(ValueError):
        Options.from_dict({"resize": "big"})


def test_to_dict_omits_defaults_and_ignores_unknown_keys():
    opts = Options.from_dict({"quality": 40, "bogus": 1})
    assert opts.to_dict() == {"quality": 40}

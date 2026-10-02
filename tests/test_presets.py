from dataclasses import replace
from pathlib import Path

import pytest

from fileconverter.filetypes import kind_of
from fileconverter.presets import BUILTIN_BY_ID, BUILTINS, Preset, for_kind


def test_builtin_ids_match_bash_script():
    assert [p.id for p in BUILTINS] == [
        "audio:mp3", "audio:aac", "audio:ogg", "audio:opus", "audio:flac", "audio:wav",
        "video:mp4", "video:mp4-small", "video:webm", "video:mkv", "video:gif",
        "image:png", "image:jpg", "image:webp", "image:avif", "image:gif", "image:ico",
        "image:pdf",
        "office:pdf", "office:docx", "office:odt", "office:xlsx", "office:ods",
        "office:csv", "office:pptx", "office:odp",
        "pdf:png", "pdf:jpg",
    ]


def test_ext_maps_aac_to_m4a():
    assert BUILTIN_BY_ID["audio:aac"].ext == "m4a"
    assert BUILTIN_BY_ID["video:mp4-small"].ext == "mp4"


@pytest.mark.parametrize("name,kind", [
    ("a.MP3", "audio"), ("b.mkv", "video"), ("c.HEIC", "image"), ("d.docx", "document"),
    ("e.rtf", "document"), ("f.csv", "spreadsheet"), ("g.pptx", "presentation"),
    ("h.pdf", "pdf"), ("notes.txt", None), ("noext", None),
])
def test_kind_of(name, kind):
    assert kind_of(Path(name)) == kind


def test_video_files_offer_audio_extraction():
    ids = [p.id for p in for_kind(BUILTINS, "video")]
    assert "video:mp4" in ids and "audio:mp3" in ids and "image:png" not in ids


def test_spreadsheet_does_not_offer_docx():
    ids = [p.id for p in for_kind(BUILTINS, "spreadsheet")]
    assert ids == ["office:pdf", "office:xlsx", "office:ods", "office:csv"]


def test_preset_round_trip():
    p = BUILTIN_BY_ID["video:webm"]
    assert Preset.from_dict(p.to_dict()) == replace(p, builtin=False)

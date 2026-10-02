from datetime import date

import pytest

from fileconverter.naming import render, resolve


def test_render_tokens():
    assert render("{name}-{preset} {date}", name="clip", preset_name="WhatsApp video",
                  today=date(2026, 10, 2)) == "clip-WhatsApp video 2026-10-02"


@pytest.mark.parametrize("bad", ["{nmae}", "", "{name", "{name!r}", "{name:>9}"])
def test_render_rejects_unknown_and_empty(bad):
    with pytest.raises(ValueError):
        render(bad, name="x", preset_name="p", today=date.today())


def test_render_strips_slashes():
    assert render("{preset}", name="x", preset_name="a/b", today=date.today()) == "a_b"


def test_resolve_rename(tmp_path):
    (tmp_path / "a.mp3").touch()
    (tmp_path / "a (1).mp3").touch()
    assert resolve(tmp_path, "a", "mp3", "rename") == tmp_path / "a (2).mp3"


def test_resolve_free_name_is_used_as_is(tmp_path):
    assert resolve(tmp_path, "a", "mp3", "rename") == tmp_path / "a.mp3"


def test_resolve_skip_and_overwrite(tmp_path):
    (tmp_path / "a.mp3").touch()
    assert resolve(tmp_path, "a", "mp3", "skip") is None
    assert resolve(tmp_path, "a", "mp3", "overwrite") == tmp_path / "a.mp3"

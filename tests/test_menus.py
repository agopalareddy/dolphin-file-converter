import re
import subprocess
import sys

from fileconverter.menus import render_menus, sync_user_menus, user_menu_dir
from fileconverter.presets import BUILTIN_BY_ID, BUILTINS
from fileconverter.store import load


def _actions(text):
    return re.search(r"^Actions=(.*)$", text, re.M).group(1).rstrip(";").split(";")


def test_open_entry_covers_all_kinds():
    text = render_menus(BUILTINS)["fileconverter-open.desktop"]
    assert "Exec=fileconverter %F" in text and "audio/*;" in text and "application/pdf;" in text
    assert "X-KDE-Submenu" not in text and "X-KDE-Priority=TopLevel" in text


def test_one_file_per_kind():
    assert set(render_menus(BUILTINS)) == {
        "fileconverter-open.desktop", "fileconverter-audio.desktop",
        "fileconverter-video.desktop", "fileconverter-image.desktop",
        "fileconverter-document.desktop", "fileconverter-spreadsheet.desktop",
        "fileconverter-presentation.desktop", "fileconverter-pdf.desktop"}


def test_video_menu_has_extraction_after_separator():
    text = render_menus(BUILTINS)["fileconverter-video.desktop"]
    actions = _actions(text)
    assert actions.index("_SEPARATOR_") < actions.index("audio-mp3")
    assert actions.index("video-gif") < actions.index("_SEPARATOR_")
    assert "Exec=fileconverter --preset video:mp4-small %F" in text
    assert "X-KDE-Submenu=Convert to" in text


def test_every_action_has_a_section():
    for text in render_menus(BUILTINS).values():
        for action in _actions(text):
            if action != "_SEPARATOR_":
                assert f"[Desktop Action {action}]" in text


def test_hidden_presets_left_out(tmp_path):
    st = load(tmp_path / "p.json")
    st.hidden_builtins.add("audio:wav")
    assert "audio:wav" not in render_menus(st.all_presets())["fileconverter-audio.desktop"]


def test_sync_writes_executable_files_then_cleans_up(tmp_path):
    st = load(tmp_path / "p.json")
    out = tmp_path / "menus"
    st.add_user_preset("Podcast", BUILTIN_BY_ID["audio:mp3"], {})
    sync_user_menus(st, out)
    f = out / "fileconverter-audio.desktop"
    assert "--preset user:podcast" in f.read_text() and f.stat().st_mode & 0o111
    st.user_presets.clear()
    sync_user_menus(st, out)
    assert not list(out.glob("fileconverter-*.desktop"))


def test_write_removes_stale_files(tmp_path):
    (tmp_path / "fileconverter-old.desktop").write_text("x")
    (tmp_path / "other.desktop").write_text("x")
    subprocess.run([sys.executable, "-m", "fileconverter.menus", str(tmp_path)], check=True)
    assert not (tmp_path / "fileconverter-old.desktop").exists()
    assert (tmp_path / "other.desktop").exists() and (tmp_path / "fileconverter-pdf.desktop").exists()


def test_user_menu_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert user_menu_dir() == tmp_path / "kio" / "servicemenus"

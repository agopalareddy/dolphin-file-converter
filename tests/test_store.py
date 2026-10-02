import json
import os

from fileconverter.presets import BUILTIN_BY_ID
from fileconverter.store import Settings, config_path, load, save


def test_missing_file_gives_defaults(tmp_path):
    st = load(tmp_path / "presets.json")
    assert st.user_presets == [] and st.settings.pattern == "{name}"
    assert len(st.all_presets()) == 28 and st.notice is None


def test_round_trip(tmp_path):
    path = tmp_path / "presets.json"
    st = load(path)
    p = st.add_user_preset("WhatsApp video!", BUILTIN_BY_ID["video:mp4"],
                           {"quality": 40, "max_height": 720})
    st.hidden_builtins.add("audio:wav")
    st.settings.clash = "skip"
    save(st, path)
    again = load(path)
    assert p.id == "user:whatsapp-video" and again.get(p.id).options["max_height"] == 720
    assert again.get(p.id).inputs == ("video",) and again.get(p.id).format == "mp4"
    assert again.get("audio:wav").in_menu is False and again.settings.clash == "skip"
    assert json.loads(path.read_text())["version"] == 1


def test_slug_dedupes(tmp_path):
    st = load(tmp_path / "p.json")
    base = BUILTIN_BY_ID["audio:mp3"]
    assert st.add_user_preset("Podcast", base, {}).id == "user:podcast"
    assert st.add_user_preset("Podcast", base, {}).id == "user:podcast-2"
    assert st.add_user_preset("Ünïcode ★", base, {}).id == "user:unicode"
    assert st.add_user_preset("★★", base, {}).id == "user:preset"


def test_remove_and_customized(tmp_path):
    st = load(tmp_path / "p.json")
    assert not st.is_customized()
    p = st.add_user_preset("Podcast", BUILTIN_BY_ID["audio:mp3"], {})
    assert st.is_customized()
    st.remove_user_preset(p.id)
    assert not st.is_customized()


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("{not json")
    st = load(path)
    assert st.notice and (tmp_path / "presets.json.bak").read_text() == "{not json"
    assert len(st.all_presets()) == 28


def test_wrong_shape_is_backed_up(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text('{"version": 1, "presets": [{"name": "no id"}]}')
    st = load(path)
    assert st.notice and st.user_presets == []


def test_workers_automatic():
    assert Settings().workers() == max(1, (os.cpu_count() or 2) // 2)
    assert Settings(parallel=3).workers() == 3


def test_config_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "dolphin-file-converter" / "presets.json"

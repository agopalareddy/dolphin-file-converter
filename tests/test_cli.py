import pytest

from fileconverter.cli import main
from fileconverter.presets import BUILTIN_BY_ID
from fileconverter.store import load, save


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def test_no_args_lists_presets(capsys):
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "Usage: fileconvert PRESET FILE..." in err and "video:mp4-small" in err


def test_unknown_preset(capsys, sample_wav):
    assert main(["audio:nope", str(sample_wav)]) == 2
    assert "Unknown preset: audio:nope" in capsys.readouterr().err


def test_converts_with_builtin_id(sample_wav, capsys):
    assert main(["audio:mp3", str(sample_wav)]) == 0
    assert sample_wav.with_suffix(".mp3").stat().st_size > 0
    err = capsys.readouterr().err
    assert "Converting 1 of 1 to MP3: tone.wav" in err and "Done" in err


def test_user_preset_id_works(sample_wav):
    st = load()
    st.add_user_preset("Podcast", BUILTIN_BY_ID["audio:mp3"], {"quality": 10})
    save(st)
    assert main(["user:podcast", str(sample_wav)]) == 0
    assert sample_wav.with_suffix(".mp3").exists()


def test_settings_apply(sample_wav):
    st = load()
    st.settings.pattern = "{name}-cli"
    save(st)
    assert main(["audio:flac", str(sample_wav)]) == 0
    assert sample_wav.with_name("tone-cli.flac").exists()


def test_wrong_kind_fails(sample_png, capsys):
    assert main(["audio:mp3", str(sample_png)]) == 1
    assert "Failed: MP3 can't convert pic.png" in capsys.readouterr().err


def test_missing_tool(monkeypatch, sample_wav, capsys):
    monkeypatch.setattr("fileconverter.cli.detect_tools",
                        lambda: {"ffmpeg": False, "ffprobe": True})
    assert main(["audio:mp3", str(sample_wav)]) == 1
    assert "ffmpeg is not installed" in capsys.readouterr().err

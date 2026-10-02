from dataclasses import replace
from pathlib import Path

from fileconverter.commands import (build, detect_tools, parse_duration, parse_progress,
                                    required_tools)
from fileconverter.presets import BUILTIN_BY_ID


def _flag(argv, name):
    return argv[argv.index(name) + 1]


def test_mp4_default_argv_matches_bash(tmp_path):
    argv = build(BUILTIN_BY_ID["video:mp4"], Path("/in.mov"), tmp_path, lo_profile=tmp_path)
    assert argv[0] == "ffmpeg"
    for name, value in (("-crf", "20"), ("-preset", "medium"), ("-c:a", "aac"),
                        ("-b:a", "160k"), ("-movflags", "+faststart")):
        assert _flag(argv, name) == value
    assert argv[-1] == str(tmp_path / "out.mp4")


def test_mp4_small_argv_matches_bash(tmp_path):
    argv = build(BUILTIN_BY_ID["video:mp4-small"], Path("/in.mov"), tmp_path, lo_profile=tmp_path)
    assert (_flag(argv, "-crf"), _flag(argv, "-preset"), _flag(argv, "-b:a")) == ("28", "slow", "96k")


def test_ffmpeg_reports_progress_on_stdout(tmp_path):
    argv = build(BUILTIN_BY_ID["audio:mp3"], Path("/a.wav"), tmp_path, lo_profile=tmp_path)
    assert _flag(argv, "-progress") == "pipe:1" and "-nostdin" in argv and "-nostats" in argv


def test_trim_and_strip(tmp_path):
    p = replace(BUILTIN_BY_ID["audio:mp3"],
                options={"quality": 78, "trim_start": 5, "trim_end": 15, "strip_metadata": True})
    argv = build(p, Path("/a.wav"), tmp_path, lo_profile=tmp_path)
    assert argv.index("-ss") < argv.index("-i") < argv.index("-to")
    assert _flag(argv, "-to") == "10" and _flag(argv, "-map_metadata") == "-1"


def test_max_height_filter_keeps_even_height(tmp_path):
    p = replace(BUILTIN_BY_ID["video:mp4"], options={"quality": 79, "max_height": 720})
    argv = build(p, Path("/a.mp4"), tmp_path, lo_profile=tmp_path)
    assert _flag(argv, "-vf") == "scale=-2:'2*trunc(min(ih,720)/2)'"


def test_magick_reads_through_hidden_link(tmp_path):
    src = tmp_path / "-odd [1].png"
    src.touch()
    work = tmp_path / "work"
    work.mkdir()
    argv = build(BUILTIN_BY_ID["image:png"], src, work, lo_profile=tmp_path)
    link = work / ".in.png"
    assert link.is_symlink() and link.resolve() == src.resolve()
    assert f"{link}[0]" in argv and str(src) not in argv


def test_office_uses_lock_and_profile(tmp_path):
    argv = build(BUILTIN_BY_ID["office:docx"], Path("/a.odt"), tmp_path,
                 lo_profile=tmp_path / "lo")
    assert argv[:3] == ["flock", f"{tmp_path / 'lo'}.lock", "soffice"]
    assert f"-env:UserInstallation={(tmp_path / 'lo').as_uri()}" in argv


def test_pdf_pages_pattern_and_dpi(tmp_path):
    p = replace(BUILTIN_BY_ID["pdf:jpg"], options={"pdf_dpi": 300, "quality": 90})
    argv = build(p, Path("/a.pdf"), tmp_path, lo_profile=tmp_path)
    assert _flag(argv, "-density") == "300" and argv[-1] == str(tmp_path / "page-%d.jpg")


def test_parse_progress_and_duration():
    assert parse_progress("out_time_us=1000000\nprogress=continue\nout_time_us=2500000\n") == 2.5
    assert parse_progress("progress=continue\n") is None
    assert parse_duration("N/A\n") is None and parse_duration("3.5\n") == 3.5


def test_required_tools():
    assert required_tools(BUILTIN_BY_ID["pdf:png"]) == ("magick", "gs")
    assert required_tools(BUILTIN_BY_ID["audio:mp3"]) == ("ffmpeg", "ffprobe")


def test_detect_tools_uses_which():
    found = detect_tools(which=lambda t: "/usr/bin/x" if t == "ffmpeg" else None)
    assert found["ffmpeg"] and not found["soffice"] and set(found) >= {"gs", "magick"}

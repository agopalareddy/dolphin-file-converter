"""Run every built-in preset through the real tools."""

import json
import subprocess
from dataclasses import replace

import pytest

from fileconverter.commands import build
from fileconverter.presets import BUILTIN_BY_ID, BUILTINS


def _outputs(workdir, ext):
    return sorted(p for p in workdir.iterdir()
                  if not p.name.startswith(".") and p.suffix == f".{ext}" and p.stat().st_size)


def _size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


def _convert(preset, src, tmp_path, lo_profile):
    work = tmp_path / f"work-{preset.id.replace(':', '-')}"
    work.mkdir()
    subprocess.run(build(preset, src, work, lo_profile=lo_profile),
                   cwd=work, check=True, capture_output=True)
    return _outputs(work, preset.ext)


@pytest.mark.parametrize("preset", BUILTINS, ids=lambda p: p.id)
def test_builtin_preset_converts(preset, samples, tmp_path, lo_profile):
    outs = _convert(preset, samples(preset.inputs[0]), tmp_path, lo_profile)
    assert outs
    if preset.id == "video:mp4":
        assert _size(outs[0]) == (320, 240)
    if preset.id.startswith("pdf:"):
        assert len(outs) == 2


def test_max_height_on_odd_sized_video(sample_mp4, tmp_path, lo_profile):
    p = replace(BUILTIN_BY_ID["video:mp4"], options={"quality": 79, "max_height": 1080})
    assert _size(_convert(p, sample_mp4, tmp_path, lo_profile)[0]) == (320, 240)


@pytest.mark.parametrize("pid,kind", [("video:mp4", "video"), ("image:webp", "image"),
                                      ("audio:mp3", "audio"), ("image:png", "image")])
def test_odd_names_convert(pid, kind, odd_names, tmp_path, lo_profile):
    assert _convert(BUILTIN_BY_ID[pid], odd_names[kind], tmp_path, lo_profile)

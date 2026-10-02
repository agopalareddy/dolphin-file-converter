"""Build the ffmpeg / ImageMagick / LibreOffice command for a conversion.

Every command writes into a work directory: ``out.<ext>`` for single
outputs, ``page-N.<ext>`` for PDF pages, or LibreOffice's own name. The
caller moves results into place.
"""

import re
import shutil
from collections.abc import Callable
from pathlib import Path

from .options import Options, encoder_quality
from .presets import Preset

TOOLS = ("ffmpeg", "ffprobe", "magick", "gs", "soffice")

_FIRST_FRAME = {"png", "jpg", "avif", "ico"}


def detect_tools(which: Callable[[str], str | None] = shutil.which) -> dict[str, bool]:
    return {tool: which(tool) is not None for tool in TOOLS}


def required_tools(preset: Preset) -> tuple[str, ...]:
    return {
        "audio": ("ffmpeg", "ffprobe"),
        "video": ("ffmpeg", "ffprobe"),
        "image": ("magick",),
        "pdf": ("magick", "gs"),
        "office": ("soffice",),
    }[preset.category]


def build(preset: Preset, src: Path, workdir: Path, *, lo_profile: Path) -> list[str]:
    opts = Options.from_dict(preset.options)
    if preset.category in ("audio", "video"):
        return _ffmpeg(preset, opts, src, workdir / f"out.{preset.ext}")
    if preset.category == "image":
        return _image(preset, opts, _link(src, workdir), workdir / f"out.{preset.ext}")
    if preset.category == "pdf":
        return _pdf_pages(preset, opts, _link(src, workdir), workdir)
    return ["flock", f"{lo_profile}.lock", "soffice",
            f"-env:UserInstallation={lo_profile.as_uri()}", "--headless",
            "--convert-to", preset.ext, "--outdir", str(workdir), str(src)]


def probe_argv(src: Path) -> list[str]:
    return ["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(src)]


def parse_duration(text: str) -> float | None:
    try:
        return float(text.strip())
    except ValueError:
        return None


def parse_progress(text: str) -> float | None:
    """Seconds encoded so far, from ffmpeg ``-progress`` output."""
    found = re.findall(r"out_time_us=(\d+)", text)
    return int(found[-1]) / 1_000_000 if found else None


def _link(src: Path, workdir: Path) -> Path:
    # ImageMagick parses "[..]" and "%" in file names; a plain link name
    # keeps odd user file names away from it.
    link = workdir / f".in{src.suffix.lower()}"
    link.unlink(missing_ok=True)
    link.symlink_to(src.resolve())
    return link


def _even_height(h: int) -> str:
    return f"scale=-2:'2*trunc(min(ih,{h})/2)'"


def _num(x: float) -> str:
    return f"{x:g}"


def _ffmpeg(preset: Preset, o: Options, src: Path, out: Path) -> list[str]:
    argv = ["ffmpeg", "-hide_banner", "-nostdin", "-y"]
    if o.trim_start:
        argv += ["-ss", _num(o.trim_start)]
    argv += ["-i", str(src)]
    if o.trim_end:
        argv += ["-to", _num(o.trim_end - (o.trim_start or 0))]
    argv += _codec_args(preset, o)
    if o.strip_metadata:
        argv += ["-map_metadata", "-1"]
        if preset.format == "mkv":
            argv += ["-map_chapters", "-1"]
    return argv + ["-progress", "pipe:1", "-nostats", str(out)]


def _codec_args(preset: Preset, o: Options) -> list[str]:
    fmt = preset.format
    q = encoder_quality(fmt, o.quality) if o.quality is not None else None
    if preset.category == "audio":
        return ["-vn"] + {
            "mp3": ["-c:a", "libmp3lame", "-q:a", str(q)],
            "aac": ["-c:a", "aac", "-b:a", str(q)],
            "ogg": ["-c:a", "libvorbis", "-q:a", str(q)],
            "opus": ["-c:a", "libopus", "-b:a", str(q)],
            "flac": ["-c:a", "flac"],
            "wav": ["-c:a", "pcm_s16le"],
        }[fmt]
    if fmt == "mp4":
        # Lower quality means "smaller file": spend more encode time and
        # less audio bitrate, as the bash script's mp4-small did.
        small = o.quality < 50
        vf = _even_height(o.max_height) if o.max_height else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        return ["-c:v", "libx264", "-preset", "slow" if small else "medium", "-crf", str(q),
                "-pix_fmt", "yuv420p", "-vf", vf, "-c:a", "aac",
                "-b:a", "96k" if small else "160k", "-movflags", "+faststart"]
    if fmt == "webm":
        vf = ["-vf", _even_height(o.max_height)] if o.max_height else []
        return ["-c:v", "libvpx-vp9", "-crf", str(q), "-b:v", "0", "-row-mt", "1",
                "-deadline", "good", "-cpu-used", "4", *vf, "-c:a", "libopus", "-b:a", "128k"]
    if fmt == "mkv":
        return ["-map", "0:v", "-map", "0:a?", "-map", "0:s?", "-c", "copy"]
    # gif
    pre = _even_height(o.max_height) + "," if o.max_height else ""
    return ["-an", "-loop", "0", "-vf",
            pre + "fps=12,scale='min(iw,640)':-2:flags=lanczos,"
            "split[a][b];[a]palettegen[p];[b][p]paletteuse"]


def _image(preset: Preset, o: Options, link: Path, out: Path) -> list[str]:
    fmt = preset.format
    src = f"{link}[0]" if fmt in _FIRST_FRAME else str(link)
    argv = ["magick", "-background", "none", src, "-auto-orient"]
    if o.resize:
        argv += ["-resize", o.resize + (">" if "x" in o.resize else "")]
    if fmt == "jpg":
        argv += ["-background", "white", "-flatten"]
    if fmt in ("jpg", "webp", "avif"):
        argv += ["-quality", str(encoder_quality(fmt, o.quality))]
    if fmt == "ico":
        argv += ["-resize", "256x256", "-gravity", "center", "-extent", "256x256",
                 "-define", "icon:auto-resize=256,128,64,48,32,16"]
    if o.strip_metadata:
        argv.append("-strip")
    return argv + [str(out)]


def _pdf_pages(preset: Preset, o: Options, link: Path, workdir: Path) -> list[str]:
    argv = ["magick", "-density", str(o.pdf_dpi), str(link),
            "-background", "white", "-alpha", "remove", "-alpha", "off"]
    if preset.format == "jpg":
        argv += ["-quality", str(encoder_quality("jpg", o.quality or 90))]
    return argv + ["-scene", "1", str(workdir / f"page-%d.{preset.ext}")]

"""Per-conversion options and how the quality slider maps onto each encoder."""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .presets import Preset

MAX_HEIGHTS = (None, 2160, 1440, 1080, 720, 480)
PDF_DPIS = (72, 150, 300)

_RESIZE = re.compile(r"\d+%|\d+x\d+")


@dataclass(frozen=True)
class Options:
    quality: int | None = None
    max_height: int | None = None
    resize: str | None = None
    trim_start: float | None = None
    trim_end: float | None = None
    strip_metadata: bool = False
    pdf_dpi: int = 150

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Options":
        known = {f.name for f in fields(cls)}
        opts = cls(**{k: v for k, v in d.items() if k in known})
        if opts.resize is not None and not _RESIZE.fullmatch(opts.resize):
            raise ValueError(f"Invalid resize value: {opts.resize!r}")
        return opts

    def to_dict(self) -> dict[str, Any]:
        defaults = Options()
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) != getattr(defaults, f.name)}


def _round(x: float) -> int:
    return math.floor(x + 0.5)


def _kbps(low: int, high: int, q: int) -> str:
    return f"{8 * _round((low + q * (high - low) / 100) / 8)}k"


def encoder_quality(fmt: str, quality: int) -> int | str:
    """Map a 0–100 quality value onto the encoder setting for ``fmt``."""
    q = quality
    match fmt:
        case "mp4":
            return _round(35 - q * 19 / 100)
        case "webm":
            return _round(45 - q * 25 / 100)
        case "mp3":
            return _round(9 - q * 9 / 100)
        case "ogg":
            return _round(q * 10 / 100)
        case "aac":
            return _kbps(64, 320, q)
        case "opus":
            return _kbps(48, 256, q)
        case "jpg" | "webp" | "avif":
            return max(1, q)
    raise ValueError(f"No quality setting for {fmt}")


_QUALITY = {
    "audio": {"mp3", "aac", "ogg", "opus"},
    "video": {"mp4", "webm"},
    "image": {"jpg", "webp", "avif"},
}


def applicable(preset: Preset) -> frozenset[str]:
    """Names of the options that make sense for ``preset``."""
    cat, fmt = preset.category, preset.format
    names = set()
    if fmt in _QUALITY.get(cat, ()):
        names.add("quality")
    if cat == "video" and fmt != "mkv":
        names.add("max_height")
    if cat == "audio" or (cat == "video" and fmt != "mkv"):
        names |= {"trim_start", "trim_end"}
    if cat == "image":
        names.add("resize")
    if cat in ("audio", "video", "image"):
        names.add("strip_metadata")
    if cat == "pdf":
        names.add("pdf_dpi")
    return frozenset(names)


def parse_time(text: str) -> float | None:
    """Parse ``ss``, ``mm:ss`` or ``hh:mm:ss`` (decimals allowed) into seconds."""
    text = text.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise ValueError(f"Not a time: {text!r}")
    values = [float(p) for p in parts]
    if any(v >= 60 for v in values[1:]):
        raise ValueError(f"Not a time: {text!r}")
    seconds = 0.0
    for v in values:
        seconds = seconds * 60 + v
    return seconds


def format_time(seconds: float) -> str:
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""
    seconds = round(seconds, 3)
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    sec = f"{seconds - h * 3600 - m * 60:06.3f}".rstrip("0").rstrip(".")
    return f"{h}:{m:02d}:{sec}" if h else f"{m}:{sec}"

"""Preset model and the built-in presets."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_EXT_FOR_FORMAT = {"aac": "m4a"}


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    category: str
    format: str
    inputs: tuple[str, ...]
    options: Mapping[str, Any] = field(default_factory=dict)
    in_menu: bool = True
    builtin: bool = False

    @property
    def ext(self) -> str:
        return _EXT_FOR_FORMAT.get(self.format, self.format)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "format": self.format,
            "inputs": list(self.inputs),
            "options": dict(self.options),
            "in_menu": self.in_menu,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Preset":
        return cls(
            id=d["id"],
            name=d["name"],
            category=d["category"],
            format=d["format"],
            inputs=tuple(d["inputs"]),
            options=dict(d.get("options", {})),
            in_menu=bool(d.get("in_menu", True)),
        )


_MEDIA = ("audio", "video")
_DOC, _SHEET, _SLIDES = ("document",), ("spreadsheet",), ("presentation",)


def _p(pid: str, name: str, inputs: tuple[str, ...], fmt: str | None = None,
       **options: Any) -> Preset:
    category, fmt_from_id = pid.split(":")
    return Preset(pid, name, category, fmt or fmt_from_id, inputs, options, builtin=True)


BUILTINS: tuple[Preset, ...] = (
    _p("audio:mp3", "MP3", _MEDIA),
    _p("audio:aac", "AAC (M4A)", _MEDIA),
    _p("audio:ogg", "OGG Vorbis", _MEDIA),
    _p("audio:opus", "Opus", _MEDIA),
    _p("audio:flac", "FLAC", _MEDIA),
    _p("audio:wav", "WAV", _MEDIA),
    _p("video:mp4", "MP4 (H.264)", ("video",)),
    _p("video:mp4-small", "MP4 (smaller file)", ("video",), "mp4"),
    _p("video:webm", "WebM (VP9)", ("video",)),
    _p("video:mkv", "MKV (no re-encode)", ("video",)),
    _p("video:gif", "Animated GIF", ("video",)),
    _p("image:png", "PNG", ("image",)),
    _p("image:jpg", "JPG", ("image",)),
    _p("image:webp", "WebP", ("image",)),
    _p("image:avif", "AVIF", ("image",)),
    _p("image:gif", "GIF", ("image",)),
    _p("image:ico", "ICO (icon)", ("image",)),
    _p("image:pdf", "PDF", ("image",)),
    _p("office:pdf", "PDF", _DOC + _SHEET + _SLIDES),
    _p("office:docx", "Word (DOCX)", _DOC),
    _p("office:odt", "OpenDocument (ODT)", _DOC),
    _p("office:xlsx", "Excel (XLSX)", _SHEET),
    _p("office:ods", "OpenDocument (ODS)", _SHEET),
    _p("office:csv", "CSV (first sheet)", _SHEET),
    _p("office:pptx", "PowerPoint (PPTX)", _SLIDES),
    _p("office:odp", "OpenDocument (ODP)", _SLIDES),
    _p("pdf:png", "PNG (one per page)", ("pdf",)),
    _p("pdf:jpg", "JPG (one per page)", ("pdf",)),
)

BUILTIN_BY_ID: dict[str, Preset] = {p.id: p for p in BUILTINS}

DEFAULT_FOR_KIND = {
    "audio": "audio:mp3",
    "video": "video:mp4",
    "image": "image:webp",
    "document": "office:pdf",
    "spreadsheet": "office:pdf",
    "presentation": "office:pdf",
    "pdf": "pdf:png",
}


def for_kind(presets: Iterable[Preset], kind: str) -> list[Preset]:
    """Presets that accept files of ``kind``, in their original order."""
    return [p for p in presets if kind in p.inputs]

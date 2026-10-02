"""Which kind of input a file is, and the MIME types each kind covers."""

import mimetypes
from pathlib import Path

KINDS = ("audio", "video", "image", "document", "spreadsheet", "presentation", "pdf")

# Checked before mimetypes: office formats have no common MIME prefix, and
# some media types are missing from Python's table on some systems.
_EXTENSIONS = {
    **dict.fromkeys(("doc", "docx", "odt", "rtf"), "document"),
    **dict.fromkeys(("xls", "xlsx", "ods", "csv"), "spreadsheet"),
    **dict.fromkeys(("ppt", "pptx", "odp"), "presentation"),
    "pdf": "pdf",
    **dict.fromkeys(("mp3", "m4a", "aac", "ogg", "oga", "opus", "flac", "wav",
                     "wma", "aiff", "aif", "ape", "wv"), "audio"),
    **dict.fromkeys(("mp4", "mkv", "webm", "mov", "avi", "m4v", "wmv", "flv",
                     "mpg", "mpeg", "ts", "mts", "m2ts", "3gp", "ogv"), "video"),
    **dict.fromkeys(("png", "jpg", "jpeg", "webp", "avif", "heic", "heif", "gif",
                     "bmp", "tif", "tiff", "ico", "svg", "jxl"), "image"),
}

MIME_TYPES = {
    "audio": ["audio/*"],
    "video": ["video/*"],
    "image": ["image/*"],
    "document": [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/rtf",
        "text/rtf",
    ],
    "spreadsheet": [
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.spreadsheet",
        "text/csv",
    ],
    "presentation": [
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.presentation",
    ],
    "pdf": ["application/pdf"],
}


def kind_of(path: Path) -> str | None:
    """Return the input kind of ``path`` from its name, or None if unsupported."""
    kind = _EXTENSIONS.get(path.suffix.lower().lstrip("."))
    if kind:
        return kind
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        prefix = mime.split("/", 1)[0]
        if prefix in ("audio", "video", "image"):
            return prefix
    return None

"""Which kind of input a file is, and the MIME types each kind covers."""

from pathlib import Path

from PySide6.QtCore import QMimeDatabase, QMimeType

KINDS = ("audio", "video", "image", "document", "spreadsheet", "presentation", "pdf")

# Common extensions, checked before the MIME database for speed and so the
# usual formats work even where shared-mime-info is incomplete.
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


# audio/* to shared-mime-info, but lists of links rather than audio.
_PLAYLISTS = {"audio/x-mpegurl", "audio/x-scpls", "application/vnd.apple.mpegurl",
              "application/x-mpegurl"}


def _matches(mime: QMimeType, pattern: str) -> bool:
    names = [mime.name(), *mime.allAncestors()]
    if pattern.endswith("/*"):
        return any(n.startswith(pattern[:-1]) for n in names)
    return pattern in names


def kind_of(path: Path) -> str | None:
    """Return the input kind of ``path``, or None if unsupported."""
    kind = _EXTENSIONS.get(path.suffix.lower().lstrip("."))
    if kind:
        return kind
    # The same shared-mime-info database Dolphin uses to pick the menus, so
    # anything it offers to convert (.m4b, camera RAW, ...) is accepted.
    mode = QMimeDatabase.MatchDefault if path.is_file() else QMimeDatabase.MatchExtension
    mime = QMimeDatabase().mimeTypeForFile(str(path), mode)
    if _PLAYLISTS & {mime.name(), *mime.allAncestors()}:
        return None
    for kind in KINDS:
        if any(_matches(mime, pattern) for pattern in MIME_TYPES[kind]):
            return kind
    return None

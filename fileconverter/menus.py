"""Dolphin right-click menus, generated from the preset list.

Run ``python -m fileconverter.menus OUTDIR`` to write the built-in menus
(used at package build time and by install.sh).
"""

import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .filetypes import KINDS, MIME_TYPES
from .presets import BUILTINS, Preset, for_kind
from .store import Store

_ICONS = {
    "audio": "audio-x-generic", "video": "video-x-generic", "image": "image-x-generic",
    "pdf": "application-pdf", "gif": "image-gif", "docx": "x-office-document",
    "odt": "x-office-document", "xlsx": "x-office-spreadsheet",
    "ods": "x-office-spreadsheet", "csv": "text-csv", "pptx": "x-office-presentation",
    "odp": "x-office-presentation",
}


def _icon(p: Preset) -> str:
    if p.format in ("pdf", "gif") or p.category == "office":
        return _ICONS[p.format]
    return _ICONS["image" if p.category == "pdf" else p.category]


def _action_id(p: Preset) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", p.id)


def _entry(mimes: Sequence[str], actions: Sequence[str], submenu: bool) -> str:
    lines = ["[Desktop Entry]", "Type=Service", f"MimeType={';'.join(mimes)};",
             f"Actions={';'.join(actions)};"]
    if submenu:
        lines.append("X-KDE-Submenu=Convert to")
    lines += ["X-KDE-Priority=TopLevel", "Icon=document-export", ""]
    return "\n".join(lines)


def _action(aid: str, name: str, icon: str, exec_: str) -> str:
    name = name.replace("\n", " ")
    return f"\n[Desktop Action {aid}]\nName={name}\nIcon={icon}\nExec={exec_}\n"


def render_menus(presets: Sequence[Preset]) -> dict[str, str]:
    """Map ``.desktop`` file names to their contents."""
    all_mimes = [m for kind in KINDS for m in MIME_TYPES[kind]]
    files = {"fileconverter-open.desktop":
             _entry(all_mimes, ["open"], submenu=False)
             + _action("open", "Convert…", "document-export", "fileconverter %F")}
    shown = [p for p in presets if p.in_menu]
    for kind in KINDS:
        entries = for_kind(shown, kind)
        if kind == "video":
            # Video formats first, then audio extraction.
            entries = ([p for p in entries if p.category == "video"] + [None]
                       + [p for p in entries if p.category != "video"])
            if entries[-1] is None:
                entries.pop()
        if not [p for p in entries if p]:
            # Still written: an empty file shadows the packaged menu, which
            # would otherwise show presets the user hid.
            files[f"fileconverter-{kind}.desktop"] = _entry(MIME_TYPES[kind], [], True)
            continue
        ids = [_action_id(p) if p else "_SEPARATOR_" for p in entries]
        body = "".join(
            _action(_action_id(p),
                    p.name + (" (audio only)" if kind == "video" and p.category == "audio" else ""),
                    _icon(p), f"fileconverter --preset {p.id} %F")
            for p in entries if p)
        files[f"fileconverter-{kind}.desktop"] = _entry(MIME_TYPES[kind], ids, True) + body
    return files


def write_menus(directory: Path, files: Mapping[str, str]) -> None:
    """Write ``files`` and drop any other fileconverter-*.desktop in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("fileconverter-*.desktop"):
        if stale.name not in files:
            stale.unlink()
    for name, text in files.items():
        path = directory / name
        path.write_text(text)
        # Plasma ignores service menus in the home directory unless executable.
        path.chmod(0o755)


def user_menu_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "kio" / "servicemenus"


def _system_menus_installed() -> bool:
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return any((Path(d) / "kio" / "servicemenus" / "fileconverter-open.desktop").exists()
               for d in dirs.split(":") if d)


def sync_user_menus(st: Store, directory: Path | None = None) -> None:
    """Write the user's menus, or drop them when the packaged ones suffice.

    With a system-wide install (the AUR package) user copies only exist to
    shadow it with custom presets. A per-user install (install.sh) has no
    system copy, so the user directory must always hold the full set.
    """
    directory = directory or user_menu_dir()
    if st.is_customized() or not _system_menus_installed():
        write_menus(directory, render_menus(st.all_presets()))
    else:
        for path in directory.glob("fileconverter-*.desktop"):
            path.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m fileconverter.menus OUTDIR")
    write_menus(Path(sys.argv[1]), render_menus(BUILTINS))

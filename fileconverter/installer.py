"""How to install missing conversion tools on the user's distro.

Nothing here runs a package manager: it works out the command, and the app
offers to open a terminal where the user runs it with their own password.
"""

import os
import shlex
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .commands import TOOLS

TOOL_INFO = {
    "ffmpeg": ("FFmpeg", "audio and video"),
    "ffprobe": ("FFmpeg", "audio and video"),
    "magick": ("ImageMagick 7", "images"),
    "gs": ("Ghostscript", "PDF pages"),
    "soffice": ("LibreOffice", "documents"),
}

_PACKAGES = {
    "arch": {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "magick": "imagemagick",
             "gs": "ghostscript", "soffice": "libreoffice-fresh"},
    "debian": {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "gs": "ghostscript",
               "soffice": "libreoffice"},
    # Fedora's own build is ffmpeg-free; plain "ffmpeg" exists only in RPM Fusion.
    "fedora": {"ffmpeg": "ffmpeg-free", "ffprobe": "ffmpeg-free", "magick": "ImageMagick",
               "gs": "ghostscript", "soffice": "libreoffice"},
}

_INSTALL = {
    "arch": ("sudo", "pacman", "-S", "--needed"),
    # Stale package lists make apt fail with 404s, so refresh them first.
    "debian": ("sudo", "apt", "update", "&&", "sudo", "apt", "install"),
    "fedora": ("sudo", "dnf", "install"),
}

_FAMILY_OF = {"arch": "arch", "debian": "debian", "ubuntu": "debian", "fedora": "fedora"}
# RHEL and its clones list "fedora" in ID_LIKE but have no ffmpeg or
# ImageMagick 7 packages, so a dnf command would only fail.
_NO_COMMAND = {"rhel", "centos"}

DEBIAN_MAGICK_NOTE = ('This release ships ImageMagick 6, which has no "magick" command. '
                      "Install ImageMagick 7 from its website to convert images.")
FEDORA_FFMPEG_NOTE = ("Fedora's ffmpeg can't encode H.264 (MP4). Enable RPM Fusion and "
                      "install its ffmpeg for MP4 output.")
IMMUTABLE_NOTE = ("This system's base is read-only, so its package manager can't add these "
                  "tools. Install them the way your system recommends, for example in a "
                  "toolbox or distrobox container.")

_TERMINALS = (
    ("konsole", ["-e"]), ("gnome-terminal", ["--"]), ("kgx", ["--"]), ("ptyxis", ["--"]),
    ("xfce4-terminal", ["-x"]), ("alacritty", ["-e"]), ("ghostty", ["-e"]),
    ("wezterm", ["start", "--"]), ("kitty", []), ("foot", []), ("xterm", ["-e"]),
)


@dataclass(frozen=True)
class InstallPlan:
    tools: tuple[str, ...]
    packages: tuple[str, ...]
    command: str | None  # a shell command line
    notes: tuple[str, ...]
    rows: tuple[tuple[str, str, str | None], ...] = ()  # (tool, what it converts, package)


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    result = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and not key.startswith("#"):
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def family(os_release: Mapping[str, str]) -> str | None:
    """The package-manager family: "arch", "debian", "fedora", or None."""
    names = [os_release.get("ID", ""), *os_release.get("ID_LIKE", "").split()]
    if _NO_COMMAND & set(names):
        return None
    for name in names:
        if name in _FAMILY_OF:
            return _FAMILY_OF[name]
    return None


def _has_imagemagick7(os_release: Mapping[str, str]) -> bool:
    # Debian 13 ships ImageMagick 7 with "magick" via update-alternatives;
    # testing/sid have no VERSION_ID. Ubuntu-based releases still ship 6.
    if os_release.get("ID") != "debian":
        return False
    version = os_release.get("VERSION_ID", "")
    return not version or (version.isdigit() and int(version) >= 13)


def is_immutable(os_release: Mapping[str, str],
                 ostree_marker: Path = Path("/run/ostree-booted")) -> bool:
    """Read-only base systems (Fedora Atomic, Bazzite, SteamOS)."""
    return ostree_marker.exists() or os_release.get("ID") == "steamos"


def plan_install(missing: Iterable[str], os_release: Mapping[str, str],
                 immutable: bool = False) -> InstallPlan:
    wanted = [t for t in TOOLS if t in set(missing)]
    fam = family(os_release)
    table = dict(_PACKAGES.get(fam, {}))
    if fam == "debian" and _has_imagemagick7(os_release):
        table["magick"] = "imagemagick"
    rows = tuple(dict.fromkeys((*TOOL_INFO[t], table.get(t)) for t in wanted))
    tools = tuple(name for name, _, _ in rows)
    packages = tuple(dict.fromkeys(pkg for _, _, pkg in rows if pkg))
    notes = []
    if fam == "debian" and "magick" in wanted and "magick" not in table:
        notes.append(DEBIAN_MAGICK_NOTE)
    if fam == "fedora" and {"ffmpeg", "ffprobe"} & set(wanted):
        notes.append(FEDORA_FFMPEG_NOTE)
    command = " ".join(_INSTALL[fam] + packages) if fam and packages else None
    if immutable:
        command = None
        notes.append(IMMUTABLE_NOTE)
    return InstallPlan(tools, packages, command, tuple(notes), rows)


def plan_for_this_system(missing: Iterable[str]) -> InstallPlan:
    os_release = read_os_release()
    return plan_install(missing, os_release, immutable=is_immutable(os_release))


def find_terminal(which: Callable[[str], str | None] = shutil.which,
                  env: Mapping[str, str] = os.environ) -> list[str] | None:
    """Argv prefix that opens a terminal running the command appended to it."""
    value = env.get("TERMINAL", "").strip()
    if value:
        # A path that exists as-is (it may contain spaces), else a command
        # with arguments such as "kitty --single-instance".
        try:
            words = [value] if which(value) else shlex.split(value)
        except ValueError:
            words = []
        if words and which(words[0]):
            # Known terminals need their own flag (gnome-terminal's -e takes
            # a single string); unknown ones get the common -e.
            return [*words, *dict(_TERMINALS).get(os.path.basename(words[0]), ["-e"])]
    for name, args in _TERMINALS:
        if which(name):
            return [name, *args]
    return None


def terminal_argv(prefix: list[str], command: str) -> list[str]:
    # The command line is built only from the fixed tables above.
    script = f"{command}; echo; printf 'Press Enter to close. '; read _"
    return [*prefix, "sh", "-c", script]

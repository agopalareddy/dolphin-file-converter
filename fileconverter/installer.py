"""How to install missing conversion tools on the user's distro.

Nothing here runs a package manager: it works out the command, and the app
offers to open a terminal where the user runs it with their own password.
"""

import os
import shlex
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    "fedora": {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "magick": "ImageMagick",
               "gs": "ghostscript", "soffice": "libreoffice"},
}

_INSTALL = {
    "arch": ("sudo", "pacman", "-S", "--needed"),
    "debian": ("sudo", "apt", "install"),
    "fedora": ("sudo", "dnf", "install"),
}

_FAMILY_OF = {"arch": "arch", "debian": "debian", "ubuntu": "debian", "fedora": "fedora",
              "rhel": "fedora", "centos": "fedora"}

DEBIAN_MAGICK_NOTE = ('Debian and Ubuntu ship ImageMagick 6, which has no "magick" command. '
                      "Install ImageMagick 7 from its website to convert images.")
FEDORA_FFMPEG_NOTE = ("Fedora's ffmpeg can't encode H.264 (MP4). Enable RPM Fusion and "
                      "install its ffmpeg for MP4 output.")

_TERMINALS = (
    ("konsole", ["-e"]), ("gnome-terminal", ["--"]), ("kgx", ["--"]),
    ("xfce4-terminal", ["-x"]), ("alacritty", ["-e"]), ("kitty", []), ("foot", []),
    ("xterm", ["-e"]),
)


@dataclass(frozen=True)
class InstallPlan:
    tools: tuple[str, ...]
    packages: tuple[str, ...]
    command: tuple[str, ...] | None
    notes: tuple[str, ...]


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
    for name in [os_release.get("ID", ""), *os_release.get("ID_LIKE", "").split()]:
        if name in _FAMILY_OF:
            return _FAMILY_OF[name]
    return None


def plan_install(missing: Iterable[str], os_release: Mapping[str, str]) -> InstallPlan:
    wanted = [t for t in TOOLS if t in set(missing)]
    fam = family(os_release)
    tools = tuple(dict.fromkeys(TOOL_INFO[t][0] for t in wanted))
    packages = tuple(dict.fromkeys(
        _PACKAGES[fam][t] for t in wanted if fam and t in _PACKAGES[fam]))
    notes = []
    if fam == "debian" and "magick" in wanted:
        notes.append(DEBIAN_MAGICK_NOTE)
    if fam == "fedora" and {"ffmpeg", "ffprobe"} & set(wanted):
        notes.append(FEDORA_FFMPEG_NOTE)
    command = _INSTALL[fam] + packages if fam and packages else None
    return InstallPlan(tools, packages, command, tuple(notes))


def find_terminal(which: Callable[[str], str | None] = shutil.which,
                  env: Mapping[str, str] = os.environ) -> list[str] | None:
    """Argv prefix that opens a terminal running the command appended to it."""
    if env.get("TERMINAL"):
        return [env["TERMINAL"], "-e"]
    for name, args in _TERMINALS:
        if which(name):
            return [name, *args]
    return None


def terminal_argv(prefix: list[str], command: Sequence[str]) -> list[str]:
    script = f"{shlex.join(command)}; echo; printf 'Press Enter to close. '; read _"
    return [*prefix, "sh", "-c", script]

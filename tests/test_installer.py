import pytest

from fileconverter.installer import (family, find_terminal, is_immutable, plan_install,
                                     read_os_release, terminal_argv)

ARCH = {"ID": "cachyos", "ID_LIKE": "arch"}
MINT = {"ID": "linuxmint", "ID_LIKE": "ubuntu debian"}
FEDORA = {"ID": "fedora"}


def test_read_os_release(tmp_path):
    p = tmp_path / "os-release"
    p.write_text('ID=cachyos\nID_LIKE="arch"\n# comment\n\nNAME="CachyOS Linux"\n')
    assert read_os_release(p) == {"ID": "cachyos", "ID_LIKE": "arch", "NAME": "CachyOS Linux"}
    assert read_os_release(tmp_path / "missing") == {}


@pytest.mark.parametrize("osr,fam", [
    (ARCH, "arch"), (MINT, "debian"), (FEDORA, "fedora"), ({"ID": "ubuntu"}, "debian"),
    # RHEL clones lack ffmpeg and ImageMagick 7 in their repos: no command.
    ({"ID": "rocky", "ID_LIKE": "rhel centos fedora"}, None), ({"ID": "rhel"}, None),
    ({"ID": "nixos"}, None), ({}, None),
])
def test_family(osr, fam):
    assert family(osr) == fam


def test_arch_plan_dedupes_ffmpeg():
    plan = plan_install(["ffmpeg", "ffprobe", "soffice"], ARCH)
    assert plan.packages == ("ffmpeg", "libreoffice-fresh")
    assert plan.command == "sudo pacman -S --needed ffmpeg libreoffice-fresh"
    assert plan.tools == ("FFmpeg", "LibreOffice") and plan.notes == ()
    assert plan.rows == (("FFmpeg", "audio and video", "ffmpeg"),
                         ("LibreOffice", "documents", "libreoffice-fresh"))


def test_apt_updates_package_lists_first():
    plan = plan_install(["magick", "gs"], MINT)
    assert plan.command == "sudo apt update && sudo apt install ghostscript"
    assert any("ImageMagick 6" in n for n in plan.notes)
    assert plan.rows[0] == ("ImageMagick 7", "images", None)


def test_debian_only_magick_has_no_command():
    assert plan_install(["magick"], MINT).command is None


@pytest.mark.parametrize("osr", [
    {"ID": "debian", "VERSION_ID": "13"}, {"ID": "debian", "VERSION_ID": "14"},
    {"ID": "debian", "VERSION_CODENAME": "forky"},  # testing/sid have no VERSION_ID
])
def test_debian_13_and_later_ship_imagemagick7(osr):
    plan = plan_install(["magick"], osr)
    assert plan.command == "sudo apt update && sudo apt install imagemagick"
    assert plan.notes == ()


def test_debian_12_still_lacks_imagemagick7():
    assert plan_install(["magick"], {"ID": "debian", "VERSION_ID": "12"}).command is None


def test_fedora_ffmpeg_note():
    # Stock Fedora has no "ffmpeg" package; dnf would abort the whole command.
    plan = plan_install(["ffmpeg", "soffice"], FEDORA)
    assert plan.command == "sudo dnf install ffmpeg-free libreoffice"
    assert "RPM Fusion" in plan.notes[0]


def test_unknown_distro_lists_tools_without_command():
    plan = plan_install(["gs"], {"ID": "nixos"})
    assert plan.command is None and plan.tools == ("Ghostscript",)


def test_immutable_system_gets_no_command():
    plan = plan_install(["gs"], {"ID": "fedora"}, immutable=True)
    assert plan.command is None and "read-only" in plan.notes[-1]


@pytest.mark.parametrize("osr,marker,expected", [
    ({"ID": "fedora"}, True, True),  # Fedora Atomic / Kinoite / Bazzite
    ({"ID": "steamos", "ID_LIKE": "arch"}, False, True),
    ({"ID": "cachyos", "ID_LIKE": "arch"}, False, False),
])
def test_is_immutable(tmp_path, osr, marker, expected):
    flag = tmp_path / "ostree-booted"
    if marker:
        flag.touch()
    assert is_immutable(osr, flag) is expected


def test_find_terminal_prefers_env_then_konsole():
    installed = {"konsole", "xterm", "kitty", "gnome-terminal", "/opt/My Term/term"}

    def which(t):
        return t if t in installed else None
    assert find_terminal(which, {}) == ["konsole", "-e"]
    assert find_terminal(which, {"TERMINAL": "/opt/My Term/term"}) == ["/opt/My Term/term", "-e"]
    assert find_terminal(lambda t: None, {}) is None


@pytest.mark.parametrize("value,expected", [
    ("kitty --single-instance", ["kitty", "--single-instance"]),  # arguments kept
    ("gnome-terminal", ["gnome-terminal", "--"]),  # its -e takes one string
    ("not-installed", ["konsole", "-e"]),  # stale value falls back
])
def test_find_terminal_handles_odd_env(value, expected):
    def which(t):
        return t if t in {"konsole", "kitty", "gnome-terminal"} else None
    assert find_terminal(which, {"TERMINAL": value}) == expected


def test_terminal_argv_keeps_window_open():
    argv = terminal_argv(["konsole", "-e"], "sudo apt update && sudo apt install gs")
    assert argv[:4] == ["konsole", "-e", "sh", "-c"]
    assert argv[4].startswith("sudo apt update && sudo apt install gs;")
    assert "read _" in argv[4] and len(argv) == 5


@pytest.mark.parametrize("name,expected", [
    ("ptyxis", ["ptyxis", "--"]), ("ghostty", ["ghostty", "-e"]),
    ("wezterm", ["wezterm", "start", "--"]),
])
def test_newer_terminals_detected(name, expected):
    assert find_terminal(lambda t: t if t == name else None, {}) == expected

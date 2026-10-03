import pytest

from fileconverter.installer import (family, find_terminal, plan_install, read_os_release,
                                     terminal_argv)

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
    assert plan.command == ("sudo", "pacman", "-S", "--needed", "ffmpeg", "libreoffice-fresh")
    assert plan.tools == ("FFmpeg", "LibreOffice") and plan.notes == ()


def test_debian_has_no_imagemagick7():
    plan = plan_install(["magick", "gs"], MINT)
    assert plan.command == ("sudo", "apt", "install", "ghostscript")
    assert any("ImageMagick 6" in n for n in plan.notes)


def test_debian_only_magick_has_no_command():
    assert plan_install(["magick"], MINT).command is None


def test_fedora_ffmpeg_note():
    # Stock Fedora has no "ffmpeg" package; dnf would abort the whole command.
    plan = plan_install(["ffmpeg", "soffice"], FEDORA)
    assert plan.command == ("sudo", "dnf", "install", "ffmpeg-free", "libreoffice")
    assert "RPM Fusion" in plan.notes[0]


def test_unknown_distro_lists_tools_without_command():
    plan = plan_install(["gs"], {"ID": "nixos"})
    assert plan.command is None and plan.tools == ("Ghostscript",)


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
    argv = terminal_argv(["konsole", "-e"], ("sudo", "pacman", "-S", "ffmpeg"))
    assert argv[:4] == ["konsole", "-e", "sh", "-c"]
    assert argv[4].startswith("sudo pacman -S ffmpeg;") and "read _" in argv[4]
    assert len(argv) == 5

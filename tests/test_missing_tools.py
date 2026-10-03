from PySide6.QtCore import QProcess
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QToolButton

from fileconverter.commands import TOOLS
from fileconverter.gui import main_window as main_window_mod
from fileconverter.gui import missing_tools as missing_tools_mod
from fileconverter.gui.missing_tools import MissingToolsBar, MissingToolsDialog
from fileconverter.installer import plan_install

ALL = dict.fromkeys(TOOLS, True)


def bar_of(win):
    return win.findChild(MissingToolsBar)


def test_bar_shows_missing_names(make_window):
    win = make_window(tools={**ALL, "ffmpeg": False, "ffprobe": False, "soffice": False})
    assert bar_of(win).isVisibleTo(win)
    assert win.missing_tools() == ["ffmpeg", "soffice"]
    assert bar_of(win).findChild(QLabel, "missing_text").text() == (
        "Some formats are unavailable because FFmpeg and LibreOffice aren't installed.")


def test_bar_singular_wording(make_window):
    win = make_window(tools={**ALL, "gs": False})
    assert bar_of(win).findChild(QLabel, "missing_text").text() == (
        "Some formats are unavailable because Ghostscript isn't installed.")


def test_bar_hidden_when_all_present(window):
    assert not bar_of(window).isVisibleTo(window)


def test_dismiss_hides_for_session(make_window, monkeypatch):
    win = make_window(tools={**ALL, "gs": False})
    bar_of(win).findChild(QToolButton, "dismiss").click()
    assert not bar_of(win).isVisibleTo(win)
    monkeypatch.setattr(main_window_mod, "detect_tools", lambda: {**ALL, "gs": False})
    win.recheck_tools()
    assert not bar_of(win).isVisibleTo(win)


def test_check_again_enables_formats(make_window, monkeypatch, sample_mp4):
    win = make_window(tools={**ALL, "ffmpeg": False})
    [jid] = win.add_files([sample_mp4])
    monkeypatch.setattr(main_window_mod, "detect_tools", lambda: dict(ALL))
    win.recheck_tools()
    assert dict((p.id, tip) for p, tip in win.preset_choices(jid))["video:mp4"] is None
    assert not bar_of(win).isVisibleTo(win)


def test_dialog_command_copy_and_install(qtbot, monkeypatch):
    started = []
    monkeypatch.setattr(missing_tools_mod, "_start_process",
                        lambda argv: started.append(argv) or QProcess())
    plan = plan_install(["ffmpeg"], {"ID": "arch"})
    dlg = MissingToolsDialog(["ffmpeg"], plan, ["konsole", "-e"])
    qtbot.addWidget(dlg)
    assert dlg.findChild(QLineEdit, "command").text() == "sudo pacman -S --needed ffmpeg"
    dlg.findChild(QPushButton, "copy").click()
    assert QGuiApplication.clipboard().text() == "sudo pacman -S --needed ffmpeg"
    with qtbot.waitSignal(dlg.install_started):
        dlg.findChild(QPushButton, "install").click()
    assert started[0][:4] == ["konsole", "-e", "sh", "-c"]


def test_dialog_check_again_signal(qtbot):
    dlg = MissingToolsDialog(["gs"], plan_install(["gs"], {"ID": "arch"}), ["xterm", "-e"])
    qtbot.addWidget(dlg)
    with qtbot.waitSignal(dlg.check_requested):
        dlg.findChild(QPushButton, "check").click()


def test_dialog_without_terminal_or_command(qtbot):
    no_terminal = MissingToolsDialog(["gs"], plan_install(["gs"], {"ID": "arch"}), None)
    qtbot.addWidget(no_terminal)
    install = no_terminal.findChild(QPushButton, "install")
    assert not install.isEnabled()
    assert install.toolTip() == "No terminal found — copy the command instead"

    debian = MissingToolsDialog(["magick"], plan_install(["magick"], {"ID": "debian"}),
                                ["konsole", "-e"])
    qtbot.addWidget(debian)
    assert not debian.findChild(QPushButton, "install").isEnabled()
    assert "ImageMagick 6" in debian.findChild(QLabel, "notes").text()


def test_convert_message_points_to_bar(make_window, sample_mp4):
    win = make_window(tools={**ALL, "ffmpeg": False})
    win.add_files([sample_mp4])
    win.convert()
    message = win.statusBar().currentMessage()
    assert "Install ffmpeg" in message and "click Install…" in message

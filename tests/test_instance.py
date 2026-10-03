import os
import subprocess
import sys
from uuid import uuid4

from PySide6.QtNetwork import QLocalServer

from fileconverter.instance import InstanceServer, send_to_running, server_name


def _name():
    return f"fc-test-{uuid4()}"


def test_server_name_in_runtime_dir(monkeypatch, tmp_path):
    # $XDG_RUNTIME_DIR is private to the user, unlike /tmp.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert server_name() == str(tmp_path / "dolphin-file-converter.sock")


def test_server_name_without_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr("fileconverter.instance.QStandardPaths.writableLocation", lambda _: "")
    assert server_name() == f"dolphin-file-converter-{os.getuid()}"


def test_busy_server_still_counts_as_delivered(qtbot):
    # A running window that is too busy to answer must not get a twin.
    name = _name()
    busy = QLocalServer()
    assert busy.listen(name)
    assert send_to_running(["/a"], None, name=name, timeout_ms=300) is True


def test_no_server_returns_false(qtbot):
    assert send_to_running(["/a"], None, name=_name()) is False


def test_handoff_delivers_files_and_preset(qtbot):
    # The sender is a second process, as when Dolphin launches the app again.
    name = _name()
    server = InstanceServer()
    assert server.listen(name)
    code = ("import sys; from fileconverter.instance import send_to_running; "
            f"sys.exit(0 if send_to_running(['/a b.mp4'], 'video:mp4', name={name!r}, "
            "timeout_ms=5000) else 1)")
    with qtbot.waitSignal(server.received, timeout=5000) as blocker:
        sender = subprocess.Popen([sys.executable, "-c", code])
    qtbot.waitUntil(lambda: sender.poll() is not None, timeout=5000)
    assert blocker.args == [["/a b.mp4"], "video:mp4"] and sender.returncode == 0


def test_stale_socket_does_not_block(qtbot):
    name = _name()
    crashed = QLocalServer()
    assert crashed.listen(name)
    # A crashed instance leaves its socket file behind.
    socket_path = crashed.fullServerName()
    crashed.close()
    open(socket_path, "w").close()
    assert InstanceServer().listen(name)

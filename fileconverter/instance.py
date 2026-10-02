"""One window per user: a second launch hands its files to the first."""

import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name() -> str:
    return f"dolphin-file-converter-{os.getuid()}"


def send_to_running(files: list[str], preset: str | None, name: str | None = None,
                    timeout_ms: int = 1000) -> bool:
    """Pass ``files`` to a running instance; False if none answered."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(json.dumps({"files": files, "preset": preset}).encode() + b"\n")
    sock.waitForBytesWritten(timeout_ms)
    reply = b""
    while not reply.endswith(b"\n") and sock.waitForReadyRead(timeout_ms):
        reply += bytes(sock.readAll())
    sock.disconnectFromServer()
    return reply == b"ok\n"


class InstanceServer(QObject):
    received = Signal(list, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        self._buffers: dict[QLocalSocket, bytes] = {}

    def listen(self, name: str | None = None) -> bool:
        name = name or server_name()
        QLocalServer.removeServer(name)  # left behind if the last instance crashed
        return self._server.listen(name)

    def _accept(self) -> None:
        while (sock := self._server.nextPendingConnection()) is not None:
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._buffers.pop(s, None))
            sock.disconnected.connect(sock.deleteLater)

    def _read(self, sock: QLocalSocket) -> None:
        data = self._buffers.get(sock, b"") + bytes(sock.readAll())
        self._buffers[sock] = data
        if not data.endswith(b"\n"):
            return
        try:
            msg = json.loads(data)
            files, preset = msg["files"], msg["preset"]
            if not all(isinstance(f, str) for f in files) or not isinstance(preset, (str, type(None))):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            sock.write(b"error\n")
            return
        sock.write(b"ok\n")
        sock.flush()
        self.received.emit(files, preset)

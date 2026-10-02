"""Desktop notifications and "show in folder", best effort."""

import shutil
from pathlib import Path

from PySide6.QtCore import QProcess, QUrl
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtGui import QDesktopServices


def notify(title: str, body: str) -> None:
    """Show a desktop notification; does nothing if notify-send is missing."""
    if shutil.which("notify-send"):
        QProcess.startDetached("notify-send", ["-a", "File Converter", "-i", "fileconverter",
                                               title, body])


def show_in_folder(path: Path) -> None:
    """Open the file manager with ``path`` selected, or just its folder."""
    iface = QDBusInterface("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                           "org.freedesktop.FileManager1", QDBusConnection.sessionBus())
    if iface.isValid():
        reply = iface.call("ShowItems", [QUrl.fromLocalFile(str(path)).toString()], "")
        if reply.type() != QDBusMessage.ErrorMessage:
            return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

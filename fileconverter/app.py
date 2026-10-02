"""``fileconverter [--preset ID] [FILE...]``: the File Converter window."""

import argparse
import sys
from pathlib import Path

from .instance import InstanceServer, send_to_running


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fileconverter",
                                     description="Convert audio, video, images and documents.")
    parser.add_argument("--preset", help="convert straight away with this preset id")
    parser.add_argument("files", nargs="*", help="files or folders to add")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    files = [str(Path(f).absolute()) for f in args.files]
    if send_to_running(files, args.preset):
        return 0

    # Qt and the window are only loaded when this process becomes the window.
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .commands import detect_tools
    from .gui.main_window import MainWindow
    from .menus import sync_user_menus
    from .queue import JobQueue
    from .store import load, lo_profile_path

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    qapp.setApplicationName("fileconverter")
    qapp.setApplicationDisplayName("File Converter")
    qapp.setDesktopFileName("fileconverter")
    qapp.setWindowIcon(QIcon.fromTheme("fileconverter", QIcon.fromTheme("document-export")))

    st = load()
    queue = JobQueue(st.settings.workers(), lo_profile_path())
    window = MainWindow(queue, st, detect_tools())
    # Logging out quits without closing the window; still stop the tools.
    qapp.aboutToQuit.connect(queue.shutdown)
    server = InstanceServer(window)
    server.listen()

    def received(paths: list[str], preset: str | None) -> None:
        window.add_files([Path(p) for p in paths], preset, start=preset is not None)
        window.raise_()
        window.activateWindow()
    server.received.connect(received)

    try:
        sync_user_menus(st)
    except OSError:
        pass
    window.show()
    if files:
        window.add_files([Path(f) for f in files], args.preset, start=args.preset is not None)
    if st.notice:
        QTimer.singleShot(0, lambda: QMessageBox.information(window, "File Converter",
                                                             st.notice))
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

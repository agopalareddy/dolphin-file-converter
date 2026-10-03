"""Warning bar and install dialog for missing conversion tools."""

import shlex
from collections.abc import Iterable

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..installer import TOOL_INFO, InstallPlan, terminal_argv


def _start_process(argv: list[str]) -> QProcess:
    proc = QProcess()
    proc.start(argv[0], argv[1:])
    return proc


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def tool_names(tools: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(TOOL_INFO[t][0] for t in tools))


class MissingToolsBar(QFrame):
    install_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dismissed = False
        self.setObjectName("missing_bar")
        self.setStyleSheet("#missing_bar { background: rgba(246, 116, 0, 0.15); "
                           "border: 1px solid #f67400; border-radius: 4px; }")
        icon = QLabel()
        icon.setPixmap(QIcon.fromTheme("dialog-warning").pixmap(22, 22))
        self.text = QLabel(objectName="missing_text", wordWrap=True)
        install = QPushButton("Install…", objectName="install")
        install.clicked.connect(self.install_requested)
        dismiss = QToolButton(objectName="dismiss", text="✕", autoRaise=True,
                              toolTip="Hide until next start")
        dismiss.clicked.connect(self._dismiss)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 4, 4)
        row.addWidget(icon)
        row.addWidget(self.text, 1)
        row.addWidget(install)
        row.addWidget(dismiss)
        self.hide()

    def set_missing(self, tools: Iterable[str]) -> None:
        names = tool_names(tools)
        if names:
            verb = "isn't" if len(names) == 1 else "aren't"
            self.text.setText(
                f"Some formats are unavailable because {_join(names)} {verb} installed.")
        self.setVisible(bool(names) and not self._dismissed)

    def _dismiss(self) -> None:
        self._dismissed = True
        self.hide()


class MissingToolsDialog(QDialog):
    install_started = Signal(QProcess)
    check_requested = Signal()

    def __init__(self, missing: list[str], plan: InstallPlan, terminal: list[str] | None,
                 parent: QWidget | None = None):
        super().__init__(parent, windowTitle="Install missing tools")
        self._plan, self._terminal = plan, terminal
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("These tools aren't installed:"))
        uses: dict[str, list[str]] = {}
        for tool in missing:
            name, use = TOOL_INFO[tool]
            uses.setdefault(name, []).append(use)
        for name, use in uses.items():
            layout.addWidget(QLabel(f"• <b>{name}</b>: converts {use[0]}"))

        command = shlex.join(plan.command) if plan.command else ""
        if plan.command:
            layout.addWidget(QLabel("Install them with this command:"))
        elif plan.tools:
            layout.addWidget(QLabel("Install them with your system's package manager."))
        row = QHBoxLayout()
        self.command = QLineEdit(command, objectName="command", readOnly=True)
        self.command.setVisible(bool(command))
        copy = QPushButton(QIcon.fromTheme("edit-copy"), "Copy", objectName="copy")
        copy.setVisible(bool(command))
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(command))
        row.addWidget(self.command, 1)
        row.addWidget(copy)
        layout.addLayout(row)

        notes = QLabel("\n\n".join(plan.notes), objectName="notes", wordWrap=True)
        notes.setVisible(bool(plan.notes))
        layout.addWidget(notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        install = QPushButton(QIcon.fromTheme("utilities-terminal"), "Install in terminal",
                              objectName="install")
        install.setEnabled(bool(plan.command and terminal))
        if plan.command and not terminal:
            install.setToolTip("No terminal found — copy the command instead")
        else:
            install.setToolTip("Opens a terminal; it asks for your password before installing")
        install.clicked.connect(self._install)
        check = QPushButton(QIcon.fromTheme("view-refresh"), "Check again", objectName="check")
        check.clicked.connect(self.check_requested)
        buttons.addButton(install, QDialogButtonBox.ActionRole)
        buttons.addButton(check, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(520)

    def _install(self) -> None:
        proc = _start_process(terminal_argv(self._terminal, self._plan.command))
        self.install_started.emit(proc)

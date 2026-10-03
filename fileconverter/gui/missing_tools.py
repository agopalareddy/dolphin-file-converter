"""Warning bar and install dialog for missing conversion tools."""

from collections.abc import Iterable

from PySide6.QtCore import QProcess, Qt, Signal  # noqa: F401 (QProcess: _start_detached)
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..installer import TOOL_INFO, InstallPlan, terminal_argv


def _start_detached(argv: list[str]) -> bool:
    # Detached: closing File Converter must never kill a package manager
    # halfway through an install.
    result = QProcess.startDetached(argv[0], argv[1:])
    return bool(result[0] if isinstance(result, tuple) else result)


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

    def reveal(self, tools: Iterable[str]) -> None:
        """Show again even if dismissed, e.g. when a conversion needs a tool."""
        self._dismissed = False
        self.set_missing(tools)


class MissingToolsDialog(QDialog):
    check_requested = Signal()

    def __init__(self, missing: list[str], plan: InstallPlan, terminal: list[str] | None,
                 parent: QWidget | None = None):
        super().__init__(parent, windowTitle="Install missing tools")
        self._terminal = terminal
        self._plan = plan
        layout = QVBoxLayout(self)
        self.tools = QLabel(objectName="tools", textFormat=Qt.RichText)
        self.how = QLabel()
        self.done = QLabel("All tools are installed. You can close this window.",
                           objectName="done")
        row = QHBoxLayout()
        self.command = QLineEdit(objectName="command", readOnly=True)
        self.copy = QPushButton(QIcon.fromTheme("edit-copy"), "Copy", objectName="copy")
        self.copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.command.text()))
        row.addWidget(self.command, 1)
        row.addWidget(self.copy)
        self.notes = QLabel(objectName="notes", wordWrap=True)
        self.status = QLabel(objectName="status", wordWrap=True)
        self.status.hide()
        for widget in (self.tools, self.how, self.done):
            layout.addWidget(widget)
        layout.addLayout(row)
        layout.addWidget(self.notes)
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.install = QPushButton(QIcon.fromTheme("utilities-terminal"), "Install in terminal",
                                   objectName="install")
        self.install.clicked.connect(self._install)
        check = QPushButton(QIcon.fromTheme("view-refresh"), "Check again", objectName="check")
        check.clicked.connect(self.check_requested)
        buttons.addButton(self.install, QDialogButtonBox.ActionRole)
        buttons.addButton(check, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(520)
        self.refresh(missing, plan)

    def refresh(self, missing: list[str], plan: InstallPlan) -> None:
        """Show the current state, e.g. after tools were installed."""
        self._plan = plan
        self.tools.setText("These tools aren't installed:<br>" + "<br>".join(
            f"• <b>{name}</b>: converts {use}"
            + (f" (package <code>{package}</code>)" if package else "")
            for name, use, package in plan.rows))
        command = plan.command or ""
        self.how.setText("Install them with this command:" if command else
                         "Install them with your system's package manager.")
        self.command.setText(command)
        self.notes.setText("\n\n".join(plan.notes))

        nothing_missing = not missing
        self.done.setVisible(nothing_missing)
        for widget in (self.tools, self.how):
            widget.setVisible(not nothing_missing)
        self.command.setVisible(bool(command))
        self.copy.setVisible(bool(command))
        self.notes.setVisible(bool(plan.notes) and not nothing_missing)
        self.install.setVisible(not nothing_missing)
        self.install.setEnabled(bool(plan.command and self._terminal))
        if not plan.command:
            self.install.setToolTip(
                "There's no install command for this system — see the note" if plan.notes
                else "Install the tools with your system's package manager")
        elif not self._terminal:
            self.install.setToolTip("No terminal found — copy the command instead")
        else:
            self.install.setToolTip("Opens a terminal; it asks for your password before installing")

    def _install(self) -> None:
        if _start_detached(terminal_argv(self._terminal, self._plan.command)):
            self.status.setText("Installing in the terminal. When it finishes, click "
                                "Check again or come back to this window.")
        else:
            self.status.setText(f"Couldn't open the terminal ({self._terminal[0]}). "
                                "Copy the command and run it yourself.")
        self.status.show()

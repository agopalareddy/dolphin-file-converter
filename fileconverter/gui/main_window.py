"""The File Converter window: queue table, options and output settings."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox,
                               QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QRadioButton, QSizePolicy,
                               QStackedWidget, QStyle, QStyledItemDelegate,
                               QStyleOptionProgressBar, QTableView, QToolBar, QToolTip,
                               QVBoxLayout, QWidget)

from .. import installer, naming
from ..commands import TOOLS, detect_tools, required_tools
from ..filetypes import kind_of
from ..menus import sync_user_menus
from ..notify import notify, show_in_folder
from ..options import Options
from ..presets import DEFAULT_FOR_KIND, Preset, for_kind
from ..queue import FINISHED, JobQueue, JobState, OutputSettings
from ..store import Store, save
from .missing_tools import MissingToolsBar, MissingToolsDialog
from .options_panel import OptionsPanel
from .queue_model import COL_ACTIONS, COL_FILE, COL_PRESET, COL_STATUS, QueueModel
from .settings_dialog import SettingsDialog

_CLASH_LABELS = (("Add a number", "rename"), ("Replace it", "overwrite"), ("Skip it", "skip"))
_EDITABLE = (JobState.PENDING, JobState.WAITING, *FINISHED)


class _PresetDelegate(QStyledItemDelegate):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        model = QStandardItemModel(combo)
        jid = self.window.model.job_id(index.row())
        for preset, tip in self.window.preset_choices(jid):
            item = QStandardItem(preset.name)
            item.setData(preset.id, Qt.UserRole)
            if tip:
                item.setEnabled(False)
                item.setToolTip(tip)
            model.appendRow(item)
        combo.setModel(model)
        combo.activated.connect(lambda: (self.commitData.emit(combo),
                                         self.closeEditor.emit(combo)))
        return combo

    def setEditorData(self, editor, index):
        job = self.window.queue.job(self.window.model.job_id(index.row()))
        editor.setCurrentIndex(max(0, editor.findData(job.preset.id, Qt.UserRole)))
        editor.showPopup()

    def setModelData(self, editor, model, index):
        preset = self.window.store.get(editor.currentData(Qt.UserRole))
        jid = self.window.model.job_id(index.row())
        if jid in self.window.selected_job_ids():
            self.window.set_preset_for_selected(preset)
        else:
            self.window.queue.set_preset(jid, preset)


class _ProgressDelegate(QStyledItemDelegate):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window

    def paint(self, painter, option, index):
        job = self.window.queue.job(self.window.model.job_id(index.row()))
        if job.state is not JobState.RUNNING:
            return super().paint(painter, option, index)
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(2, 4, -2, -4)
        bar.minimum, bar.maximum = 0, 0 if job.progress is None else 100
        bar.progress = int((job.progress or 0) * 100)
        bar.text = index.data()
        bar.textVisible = True
        # Qt 6 takes the orientation from this flag; without it Breeze
        # draws a vertical bar.
        bar.state = option.state | QStyle.State_Horizontal
        QApplication.style().drawControl(QStyle.CE_ProgressBar, bar, painter)


class _ActionsDelegate(QStyledItemDelegate):
    """Row buttons drawn by the delegate. Real widgets per row made every
    insert re-lay out all rows, so big folders took minutes to add."""

    SIZE = 28

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window

    def _buttons(self, rect: QRect, index: QModelIndex):
        actions = self.window.row_actions(self.window.model.job_id(index.row()))
        right = rect.right() - 4
        for n, action in enumerate(reversed(actions)):
            x = right - (n + 1) * self.SIZE
            yield QRect(x, rect.center().y() - self.SIZE // 2, self.SIZE, self.SIZE), action

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        for rect, (_, icon, _) in self._buttons(option.rect, index):
            QIcon.fromTheme(icon).paint(painter, rect.adjusted(6, 6, -6, -6))

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            for rect, (_, _, slot) in self._buttons(option.rect, index):
                if rect.contains(event.position().toPoint()):
                    slot()
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip:
            for rect, (tip, _, _) in self._buttons(option.rect, index):
                if rect.contains(event.pos()):
                    QToolTip.showText(event.globalPos(), tip, view)
                    return True
        return super().helpEvent(event, view, option, index)


class MainWindow(QMainWindow):
    def __init__(self, queue: JobQueue, store: Store, tools: dict[str, bool],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.queue, self.store, self.tools = queue, store, tools
        self._shown_state: dict[int, JobState] = {}
        self.setWindowTitle("File Converter")
        self.setWindowIcon(QIcon.fromTheme("fileconverter", QIcon.fromTheme("document-export")))
        self.setAcceptDrops(True)
        self.resize(920, 640)

        toolbar = QToolBar("Main", movable=False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        add = QAction(QIcon.fromTheme("list-add"), "Add files…", self)
        add.triggered.connect(self._browse_files)
        clear = QAction(QIcon.fromTheme("edit-clear-history"), "Clear finished", self)
        clear.triggered.connect(self.queue.clear_finished)
        toolbar.addAction(add)
        toolbar.addAction(clear)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        settings = QAction(QIcon.fromTheme("configure"), "Settings", self)
        settings.triggered.connect(self.open_settings)
        toolbar.addAction(settings)
        self.toolbar = toolbar

        self.model = QueueModel(queue, self)
        self.table = QTableView(selectionBehavior=QAbstractItemView.SelectRows,
                                selectionMode=QAbstractItemView.ExtendedSelection)
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.SelectedClicked
                                   | QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.EditKeyPressed)
        self.table.setItemDelegateForColumn(COL_PRESET, _PresetDelegate(self))
        self.table.setItemDelegateForColumn(COL_STATUS, _ProgressDelegate(self))
        self.table.setItemDelegateForColumn(COL_ACTIONS, _ActionsDelegate(self))
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        # Fixed widths: ResizeToContents re-measures every row on each insert,
        # which froze the window for minutes on folders of thousands of files.
        for col, width in ((COL_PRESET, 190), (COL_STATUS, 170), (COL_ACTIONS, 110)):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        self.table.setMinimumHeight(220)

        hint = QLabel("Drop files or folders here, or click “Add files…”",
                      alignment=Qt.AlignCenter)
        hint.setEnabled(False)
        self.stack = QStackedWidget()
        self.stack.addWidget(hint)
        self.stack.addWidget(self.table)

        self.options_panel = OptionsPanel()
        self.options_panel.changed.connect(self._apply_options)
        self.options_panel.save_requested.connect(self._save_preset)
        self.options_box = QGroupBox("Options")
        QVBoxLayout(self.options_box).addWidget(self.options_panel)

        self.convert_button = QPushButton(QIcon.fromTheme("media-playback-start"), "Convert")
        self.convert_button.setDefault(True)
        self.convert_button.clicked.connect(self.convert)

        self.missing_bar = MissingToolsBar()
        self.missing_bar.install_requested.connect(self.show_install_dialog)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.missing_bar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.options_box)
        layout.addWidget(self._build_output_box())
        layout.addWidget(self.convert_button, 0, Qt.AlignRight)
        self.setCentralWidget(central)

        queue.job_added.connect(self._job_added)
        queue.job_changed.connect(self._job_changed)
        queue.job_removed.connect(lambda _: self._refresh())
        queue.drained.connect(self._drained)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._sync_panel())
        self.missing_bar.set_missing(self.missing_tools())
        self._refresh()
        self._sync_panel()

    # Missing tools

    def missing_tools(self) -> list[str]:
        """Missing tool keys in TOOLS order, ffprobe folded into ffmpeg."""
        missing = ("ffmpeg" if t == "ffprobe" else t for t in TOOLS if not self.tools.get(t))
        return list(dict.fromkeys(missing))

    def recheck_tools(self) -> None:
        self.tools = detect_tools()
        self.missing_bar.set_missing(self.missing_tools())
        self._refresh()
        self._sync_panel()

    def show_install_dialog(self) -> None:
        missing = self.missing_tools()
        plan = installer.plan_install(missing, installer.read_os_release())
        dialog = MissingToolsDialog(missing, plan, installer.find_terminal(), self)
        dialog.check_requested.connect(self.recheck_tools)
        dialog.install_started.connect(self._watch_install)
        dialog.exec()
        self.recheck_tools()

    def _watch_install(self, proc) -> None:
        proc.setParent(self)
        proc.finished.connect(self.recheck_tools)
        proc.errorOccurred.connect(
            lambda _: self.statusBar().showMessage("Couldn't open a terminal."))

    def changeEvent(self, event) -> None:
        # Tools may have been installed while the window was in the background.
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.recheck_tools()
        super().changeEvent(event)

    # Output settings

    def _build_output_box(self) -> QGroupBox:
        s = self.store.settings
        box = QGroupBox("Output")
        self.same_folder = QRadioButton("Same folder as original", objectName="same_folder")
        self.custom_folder = QRadioButton("Folder:", objectName="custom_folder")
        group = QButtonGroup(box)
        group.addButton(self.same_folder)
        group.addButton(self.custom_folder)
        self.folder = QLineEdit(s.output_dir or "", objectName="folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        (self.custom_folder if s.output_dir else self.same_folder).setChecked(True)
        self.pattern = QLineEdit(s.pattern, objectName="pattern",
                                 toolTip="Tokens: {name}, {preset}, {date}")
        self.clash = QComboBox(objectName="clash")
        for label, rule in _CLASH_LABELS:
            self.clash.addItem(label, rule)
        self.clash.setCurrentIndex(self.clash.findData(s.clash))

        where = QHBoxLayout()
        where.addWidget(self.same_folder)
        where.addSpacing(12)
        where.addWidget(self.custom_folder)
        where.addWidget(self.folder, 1)
        where.addWidget(browse)
        form = QFormLayout(box)
        form.addRow("Save to:", where)
        names = QHBoxLayout()
        names.addWidget(self.pattern, 1)
        names.addWidget(QLabel("If the file exists:"))
        names.addWidget(self.clash)
        form.addRow("Name:", names)

        self.same_folder.toggled.connect(self._output_changed)
        self.folder.textChanged.connect(self._output_changed)
        self.pattern.textChanged.connect(self._output_changed)
        self.clash.currentIndexChanged.connect(self._output_changed)
        return box

    def output_settings(self) -> OutputSettings:
        folder = self.folder.text().strip()
        return OutputSettings(
            folder=Path(folder).expanduser() if self.custom_folder.isChecked() and folder else None,
            pattern=self.store.settings.pattern, clash=self.clash.currentData(),
            trash_originals=self.store.settings.trash_originals)

    def _pattern_ok(self) -> bool:
        try:
            naming.render(self.pattern.text(), name="x", preset_name="p", today=date.today())
            return True
        except ValueError:
            return False

    def _output_changed(self) -> None:
        ok = self._pattern_ok()
        self.pattern.setStyleSheet("" if ok else "border: 1px solid #da4453;")
        s = self.store.settings
        if ok:
            s.pattern = self.pattern.text()
        folder = self.folder.text().strip()
        s.output_dir = folder if self.custom_folder.isChecked() and folder else None
        s.clash = self.clash.currentData()
        save(self.store)
        output = self.output_settings()
        for job in self.queue.jobs():
            if job.state in (JobState.PENDING, JobState.WAITING):
                self.queue.set_output(job.id, output)
        self._refresh()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save converted files to",
                                                  self.folder.text() or str(Path.home()))
        if folder:
            self.folder.setText(folder)
            self.custom_folder.setChecked(True)

    # Adding files

    def _browse_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", str(Path.home()))
        self.add_files([Path(f) for f in files])

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        self.add_files(paths)
        event.acceptProposedAction()

    def add_files(self, paths: Sequence[Path], preset_id: str | None = None,
                  start: bool = False) -> list[int]:
        files, skipped, messages = [], [], []
        for path in (Path(p).absolute() for p in paths):
            if path.is_dir():
                found = self._folder_files(path)
                if not found:
                    messages.append(f"No convertible files in {path.name}")
                files += found
            elif kind_of(path):
                files.append(path)
            else:
                skipped.append(path.name)
        if preset_id and preset_id not in {p.id for p in self.store.all_presets()}:
            messages.append(f"Unknown preset: {preset_id}")
            start = False  # don't convert to something the user didn't ask for
        ids = []
        output = self.output_settings()
        for src in files:
            kind = kind_of(src)
            ids.append(self.queue.add(src, kind, self._initial_preset(kind, preset_id), output))
        if skipped:
            s = "" if len(skipped) == 1 else "s"
            shown = ", ".join(skipped[:5]) + ("…" if len(skipped) > 5 else "")
            messages.append(f"Skipped {len(skipped)} unsupported file{s}: {shown}")
        if messages:
            self.statusBar().showMessage("  ·  ".join(messages))
        if start and ids:
            self._start(ids)
        return ids

    @staticmethod
    def _folder_files(folder: Path) -> list[Path]:
        # Unsupported files are skipped quietly; hidden folders (thumbnail
        # caches, leftover work dirs) are not descended into.
        return [p for p in sorted(folder.rglob("*"))
                if p.is_file() and kind_of(p)
                and not any(part.startswith(".") for part in p.relative_to(folder).parts[:-1])]

    def _initial_preset(self, kind: str, preset_id: str | None) -> Preset:
        choices = for_kind(self.store.all_presets(), kind)
        by_id = {p.id: p for p in choices}
        chosen = by_id.get(preset_id) or by_id[DEFAULT_FOR_KIND[kind]]
        if self._missing(chosen):
            chosen = next((p for p in choices if not self._missing(p)), chosen)
        return chosen

    def _missing(self, preset: Preset) -> list[str]:
        return [t for t in required_tools(preset) if not self.tools.get(t)]

    def preset_choices(self, job_id: int) -> list[tuple[Preset, str | None]]:
        """Presets offered for a job, with a tooltip when one can't be used."""
        job = self.queue.job(job_id)
        result = []
        for p in for_kind(self.store.all_presets(), job.kind):
            missing = self._missing(p)
            result.append((p, f"Install {missing[0]} to enable" if missing else None))
        return result

    # Selection, presets, options

    def selected_job_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.job_id(r) for r in rows]

    def set_preset_for_selected(self, preset: Preset) -> None:
        for jid in self.selected_job_ids():
            job = self.queue.job(jid)
            if job.kind in preset.inputs and job.state in _EDITABLE:
                self.queue.set_preset(jid, preset)
        self._sync_panel()

    def _sync_panel(self) -> None:
        ids = self.selected_job_ids()
        preset = self.queue.job(ids[0]).preset if ids else None
        self.options_panel.set_preset(preset)
        self.options_box.setTitle(f"Options for: {preset.name}" if preset else "Options")

    def _base(self, preset: Preset) -> Preset:
        """The stored preset a job's preset came from, or the job's own copy
        if that preset has since been deleted."""
        try:
            return self.store.get(preset.id)
        except KeyError:
            return replace(preset, name=preset.name.removesuffix(" (custom)"))

    def _apply_options(self, opts: dict) -> None:
        ids = self.selected_job_ids()
        if not ids:
            return
        ref = self.queue.job(ids[0]).preset.id
        base = self._base(self.queue.job(ids[0]).preset)
        same = Options.from_dict(base.options).to_dict() == opts
        name = base.name if same else f"{base.name} (custom)"
        for jid in ids:
            job = self.queue.job(jid)
            if job.preset.id == ref and job.state in _EDITABLE:
                self.queue.set_preset(jid, replace(job.preset, options=opts, name=name))
        self.options_box.setTitle(f"Options for: {name}")

    def _save_preset(self) -> None:
        ids = self.selected_job_ids()
        if not ids:
            return
        name, ok = QInputDialog.getText(self, "Save as preset", "Preset name:")
        if not ok or not name.strip():
            return
        ref = self.queue.job(ids[0]).preset.id
        preset = self.store.add_user_preset(name, self._base(self.queue.job(ids[0]).preset),
                                            self.options_panel.options())
        save(self.store)
        try:
            sync_user_menus(self.store)
        except OSError as e:
            self.statusBar().showMessage(f"Couldn't update the right-click menu: {e}")
        for jid in ids:
            if self.queue.job(jid).preset.id == ref:
                self.queue.set_preset(jid, preset)
        self._sync_panel()

    # Running

    def convert(self) -> None:
        self._start([j.id for j in self.queue.jobs() if j.state is JobState.PENDING])

    def _start(self, ids: list[int]) -> None:
        ready, blocked = [], {}
        for jid in ids:
            missing = self._missing(self.queue.job(jid).preset)
            if missing:
                blocked.setdefault(missing[0], []).append(jid)
            else:
                ready.append(jid)
        self.queue.start(ready)
        if blocked:
            tool, jobs = next(iter(blocked.items()))
            s = "" if len(jobs) == 1 else "s"
            self.statusBar().showMessage(f"Install {tool} to convert {len(jobs)} file{s} — "
                                         "click Install… at the top of the window.")
        self._refresh()

    def retry_selected(self) -> None:
        for jid in self.selected_job_ids():
            self.queue.retry(jid)

    def cancel_selected(self) -> None:
        for jid in self.selected_job_ids():
            self.queue.cancel(jid)

    def remove_selected(self) -> None:
        for jid in self.selected_job_ids():
            self.queue.remove(jid)

    def show_log(self, job_id: int) -> None:
        job = self.queue.job(job_id)
        dialog = QDialog(self, windowTitle=f"Conversion log: {job.src.name}")
        text = QPlainTextEdit(job.log or job.error, readOnly=True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy = buttons.addButton("Copy", QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(text.toPlainText()))
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(job.error))
        layout.addWidget(text)
        layout.addWidget(buttons)
        dialog.resize(640, 400)
        dialog.exec()

    def open_settings(self) -> None:
        if SettingsDialog(self.store, self).exec():
            self.queue.workers = self.store.settings.workers()
            self._output_changed()  # pending jobs pick up the Trash setting
            self._sync_panel()

    def closeEvent(self, event) -> None:
        active = self.queue.active_count()
        if active and not self.isVisible():  # nobody to ask
            self.queue.shutdown()
        elif active:
            s = "" if active == 1 else "s"
            answer = QMessageBox.question(
                self, "Stop converting?",
                f"{active} conversion{s} still running. Stop and quit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.queue.shutdown()
        event.accept()

    # Queue events

    def _job_added(self, job_id: int) -> None:
        self._shown_state[job_id] = self.queue.job(job_id).state
        self._refresh()

    def _job_changed(self, job_id: int) -> None:
        state = self.queue.job(job_id).state
        if state is not self._shown_state.get(job_id):
            self._shown_state[job_id] = state
            self._refresh()

    def row_actions(self, job_id: int) -> list[tuple[str, str, Callable[[], None]]]:
        """Buttons for a row as (tooltip, icon name, action), left to right."""
        job = self.queue.job(job_id)
        actions = []
        if job.state is JobState.DONE:
            actions.append(("Show in folder", "document-open-folder",
                            lambda: show_in_folder(job.outputs[0])))
        elif job.state is JobState.FAILED:
            actions.append(("Retry", "view-refresh", lambda: self.queue.retry(job_id)))
            actions.append(("Show error details", "help-about",
                            lambda: self.show_log(job_id)))
        if job.state in (JobState.WAITING, JobState.RUNNING):
            actions.append(("Cancel", "process-stop", lambda: self.queue.cancel(job_id)))
        else:
            actions.append(("Remove", "list-remove", lambda: self.queue.remove(job_id)))
        return actions

    def _refresh(self) -> None:
        self.stack.setCurrentIndex(1 if self.model.rowCount() else 0)
        pending = sum(j.state is JobState.PENDING for j in self.queue.jobs())
        self.convert_button.setText(f"Convert {pending} file{'' if pending == 1 else 's'}"
                                    if pending else "Convert")
        self.convert_button.setEnabled(bool(pending) and self._pattern_ok())

    def _drained(self) -> None:
        self._refresh()
        if self.isActiveWindow():
            return
        jobs = [j for j in self.queue.jobs() if j.state in FINISHED]
        done = sum(j.state is JobState.DONE for j in jobs)
        failed = sum(j.state is JobState.FAILED for j in jobs)
        s = "" if len(jobs) == 1 else "s"
        notify("Some conversions failed" if failed else "Conversion finished",
               f"Converted {done} of {len(jobs)} file{s}.")

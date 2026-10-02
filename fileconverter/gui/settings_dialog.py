"""Settings: parallel conversions, Trash originals, and the preset manager.

Output folder, name pattern and clash rule are edited in the main window,
which saves them as the defaults.
"""

import os
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..menus import sync_user_menus
from ..store import Store, save

_CATEGORY = {"audio": "Audio", "video": "Video", "image": "Image", "office": "Documents",
             "pdf": "PDF pages"}


class SettingsDialog(QDialog):
    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent, windowTitle="Settings")
        self.store = store
        # Edits go to a copy; Cancel leaves the real store untouched.
        self.work = Store(list(store.user_presets), set(store.hidden_builtins),
                          replace(store.settings))

        self.parallel = QSpinBox(objectName="parallel", minimum=0,
                                 maximum=os.cpu_count() or 8, specialValueText="Automatic")
        self.parallel.setValue(self.work.settings.parallel or 0)
        self.trash = QCheckBox("Move originals to the Trash after converting",
                               objectName="trash_originals")
        self.trash.setChecked(self.work.settings.trash_originals)
        self.trash.toggled.connect(self._confirm_trash)

        general = QGroupBox("General")
        form = QFormLayout(general)
        form.addRow("Parallel conversions:", self.parallel)
        form.addRow("", self.trash)

        self.list = QListWidget(objectName="preset_list")
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.duplicate = QPushButton("Duplicate", objectName="duplicate")
        self.rename = QPushButton("Rename…", objectName="rename")
        self.delete = QPushButton("Delete", objectName="delete")
        self.duplicate.clicked.connect(self._duplicate)
        self.rename.clicked.connect(self._rename)
        self.delete.clicked.connect(self._delete)
        side = QVBoxLayout()
        for b in (self.duplicate, self.rename, self.delete):
            side.addWidget(b)
        side.addStretch()
        presets = QGroupBox("Presets")
        pv = QVBoxLayout(presets)
        pv.addWidget(QLabel("Checked presets appear in Dolphin's right-click menu."))
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addLayout(side)
        pv.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(general)
        layout.addWidget(presets, 1)
        layout.addWidget(buttons)
        self.resize(520, 560)
        self._fill(select=None)

    def _fill(self, select: str | None) -> None:
        checks = {self.list.item(i).data(Qt.UserRole): self.list.item(i).checkState()
                  for i in range(self.list.count())}
        self.list.clear()
        for p in self.work.all_presets():
            item = QListWidgetItem(f"{p.name}  ·  {_CATEGORY[p.category]}")
            item.setData(Qt.UserRole, p.id)
            item.setData(Qt.UserRole + 1, p.builtin)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(checks.get(p.id, Qt.Checked if p.in_menu else Qt.Unchecked))
            item.setToolTip(p.id)
            self.list.addItem(item)
            if p.id == select:
                self.list.setCurrentItem(item)
        self._update_buttons()

    def _current(self):
        item = self.list.currentItem()
        return self.work.get(item.data(Qt.UserRole)) if item else None

    def _update_buttons(self) -> None:
        p = self._current()
        self.duplicate.setEnabled(p is not None)
        self.rename.setEnabled(p is not None and not p.builtin)
        self.delete.setEnabled(p is not None and not p.builtin)

    def _duplicate(self) -> None:
        p = self._current()
        copy = self.work.add_user_preset(f"{p.name} copy", p, p.options)
        self._fill(select=copy.id)

    def _rename(self) -> None:
        p = self._current()
        name, ok = QInputDialog.getText(self, "Rename preset", "Preset name:", text=p.name)
        if ok and name.strip():
            self.work.user_presets = [replace(u, name=name.strip()) if u.id == p.id else u
                                      for u in self.work.user_presets]
            self._fill(select=p.id)

    def _delete(self) -> None:
        p = self._current()
        answer = QMessageBox.question(self, "Delete preset", f"Delete the preset “{p.name}”?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.work.remove_user_preset(p.id)
            self._fill(select=None)

    def _confirm_trash(self, checked: bool) -> None:
        if not checked:
            return
        answer = QMessageBox.question(
            self, "Move originals to the Trash",
            "Originals will be moved to the Trash after each successful conversion. "
            "Turn this on?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            self.trash.blockSignals(True)
            self.trash.setChecked(False)
            self.trash.blockSignals(False)

    def accept(self) -> None:
        shown = {self.list.item(i).data(Qt.UserRole):
                 self.list.item(i).checkState() == Qt.Checked for i in range(self.list.count())}
        st = self.store
        st.user_presets = [replace(p, in_menu=shown.get(p.id, True))
                           for p in self.work.user_presets]
        st.hidden_builtins = {pid for pid, on in shown.items()
                              if not on and not pid.startswith("user:")}
        st.settings.parallel = self.parallel.value() or None
        st.settings.trash_originals = self.trash.isChecked()
        save(st)
        try:
            sync_user_menus(st)
        except OSError as e:
            QMessageBox.warning(self, "Settings", f"Couldn't update the right-click menu: {e}")
        super().accept()

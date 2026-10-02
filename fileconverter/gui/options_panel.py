"""Option widgets for the selected preset, showing only what applies."""

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget)

from ..options import MAX_HEIGHTS, PDF_DPIS, applicable, format_time, parse_time
from ..options import Options
from ..presets import Preset

_RESIZES = (("Original size", None), ("75%", "75%"), ("50%", "50%"), ("25%", "25%"),
            ("Max 3840px", "3840x3840"), ("Max 1920px", "1920x1920"),
            ("Max 1280px", "1280x1280"))


class OptionsPanel(QWidget):
    changed = Signal(dict)
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._preset: Preset | None = None
        self._loading = False
        self.setStyleSheet('QLineEdit[invalid="true"] { border: 1px solid #da4453; }')

        self.quality = QSlider(Qt.Horizontal, objectName="quality", minimum=0, maximum=100)
        quality_row = QWidget()
        q = QHBoxLayout(quality_row)
        q.setContentsMargins(0, 0, 0, 0)
        q.addWidget(QLabel("Smaller file"))
        q.addWidget(self.quality, 1)
        q.addWidget(QLabel("Better quality"))

        self.max_height = QComboBox(objectName="max_height")
        for h in MAX_HEIGHTS:
            self.max_height.addItem("Original" if h is None else f"{h}p", h)

        self.trim_start = QLineEdit(objectName="trim_start", placeholderText="0:00")
        self.trim_end = QLineEdit(objectName="trim_end", placeholderText="end")
        trim_row = QWidget()
        t = QHBoxLayout(trim_row)
        t.setContentsMargins(0, 0, 0, 0)
        t.addWidget(self.trim_start)
        t.addWidget(QLabel("to"))
        t.addWidget(self.trim_end)

        self.resize_combo = QComboBox(objectName="resize")
        for label, value in _RESIZES:
            self.resize_combo.addItem(label, value)

        self.strip_metadata = QCheckBox("Remove metadata (location, camera, dates)",
                                        objectName="strip_metadata")
        self.pdf_dpi = QComboBox(objectName="pdf_dpi")
        for dpi in PDF_DPIS:
            self.pdf_dpi.addItem(f"{dpi} DPI", dpi)

        self.empty = QLabel("No options for this format", objectName="empty")
        self.save = QPushButton("Save as preset…", objectName="save")
        self.save.clicked.connect(self.save_requested)

        self.form = QFormLayout()
        self._rows = {
            "quality": quality_row, "max_height": self.max_height, "trim_start": trim_row,
            "resize": self.resize_combo, "strip_metadata": self.strip_metadata,
            "pdf_dpi": self.pdf_dpi,
        }
        labels = {"quality": "Quality", "max_height": "Max size", "trim_start": "Trim",
                  "resize": "Resize", "strip_metadata": "", "pdf_dpi": "Resolution"}
        for name, widget in self._rows.items():
            self.form.addRow(labels[name], widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.form)
        layout.addWidget(self.empty)
        layout.addWidget(self.save, 0, Qt.AlignRight)

        self.quality.valueChanged.connect(self._edited)
        for combo in (self.max_height, self.resize_combo, self.pdf_dpi):
            combo.currentIndexChanged.connect(self._edited)
        self.strip_metadata.toggled.connect(self._edited)
        self.trim_start.textChanged.connect(self._edited)
        self.trim_end.textChanged.connect(self._edited)
        self.set_preset(None)

    def set_preset(self, preset: Preset | None) -> None:
        self._preset = preset
        shown = applicable(preset) if preset else frozenset()
        for name, widget in self._rows.items():
            self.form.setRowVisible(widget, name in shown)
        self.empty.setVisible(not shown)
        self.save.setEnabled(preset is not None)
        if preset is None:
            return
        o = Options.from_dict(preset.options)
        self._loading = True
        try:
            self.quality.setValue(o.quality if o.quality is not None else 50)
            self.max_height.setCurrentIndex(max(0, self.max_height.findData(o.max_height)))
            idx = self.resize_combo.findData(o.resize)
            if idx < 0:
                self.resize_combo.addItem(o.resize, o.resize)
                idx = self.resize_combo.count() - 1
            self.resize_combo.setCurrentIndex(idx)
            self.trim_start.setText(format_time(o.trim_start) if o.trim_start else "")
            self.trim_end.setText(format_time(o.trim_end) if o.trim_end else "")
            self.strip_metadata.setChecked(o.strip_metadata)
            self.pdf_dpi.setCurrentIndex(max(0, self.pdf_dpi.findData(o.pdf_dpi)))
        finally:
            self._loading = False
        self._validate_trim()

    def options(self) -> dict[str, Any]:
        if self._preset is None:
            return {}
        values = dict(self._preset.options)
        shown = applicable(self._preset)
        if "quality" in shown:
            values["quality"] = self.quality.value()
        if "max_height" in shown:
            values["max_height"] = self.max_height.currentData()
        if "resize" in shown:
            values["resize"] = self.resize_combo.currentData()
        if "strip_metadata" in shown:
            values["strip_metadata"] = self.strip_metadata.isChecked()
        if "pdf_dpi" in shown:
            values["pdf_dpi"] = self.pdf_dpi.currentData()
        if "trim_start" in shown:
            for name, edit in (("trim_start", self.trim_start), ("trim_end", self.trim_end)):
                try:
                    values[name] = parse_time(edit.text())
                except ValueError:
                    values.pop(name, None)
        return Options.from_dict(values).to_dict()

    def _validate_trim(self) -> bool:
        ok = True
        for edit in (self.trim_start, self.trim_end):
            try:
                parse_time(edit.text())
                invalid = False
            except ValueError:
                invalid, ok = True, False
            if edit.property("invalid") is not invalid:
                edit.setProperty("invalid", invalid)
                edit.style().unpolish(edit)
                edit.style().polish(edit)
        return ok

    def _edited(self) -> None:
        if self._loading or self._preset is None:
            return
        if self._validate_trim():
            self.changed.emit(self.options())

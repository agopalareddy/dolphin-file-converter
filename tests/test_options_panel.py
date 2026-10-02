from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QSlider

from fileconverter.gui.options_panel import OptionsPanel
from fileconverter.presets import BUILTIN_BY_ID


def panel_for(qtbot, pid):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_preset(BUILTIN_BY_ID[pid] if pid else None)
    return panel


def shown(panel, cls, name):
    return panel.findChild(cls, name).isVisibleTo(panel)


def test_shows_only_applicable(qtbot):
    panel = panel_for(qtbot, "audio:flac")
    assert not shown(panel, QSlider, "quality") and not shown(panel, QComboBox, "resize")
    assert shown(panel, QLineEdit, "trim_start") and shown(panel, QCheckBox, "strip_metadata")


def test_switching_preset_updates_rows(qtbot):
    panel = panel_for(qtbot, "audio:flac")
    panel.set_preset(BUILTIN_BY_ID["image:jpg"])
    assert shown(panel, QSlider, "quality") and not shown(panel, QLineEdit, "trim_start")


def test_loads_and_emits_options(qtbot):
    panel = panel_for(qtbot, "video:mp4")
    assert panel.findChild(QSlider, "quality").value() == 79
    with qtbot.waitSignal(panel.changed) as sig:
        panel.findChild(QComboBox, "max_height").setCurrentText("720p")
    assert sig.args[0]["max_height"] == 720 and sig.args[0]["quality"] == 79


def test_trim_round_trip(qtbot):
    panel = panel_for(qtbot, "audio:mp3")
    with qtbot.waitSignal(panel.changed) as sig:
        panel.findChild(QLineEdit, "trim_start").setText("1:30")
    assert sig.args[0]["trim_start"] == 90


def test_invalid_trim_not_emitted(qtbot):
    panel = panel_for(qtbot, "audio:mp3")
    edit = panel.findChild(QLineEdit, "trim_start")
    with qtbot.assertNotEmitted(panel.changed):
        edit.setText("1:xx")
    assert edit.property("invalid") is True and "trim_start" not in panel.options()
    edit.setText("5")
    assert edit.property("invalid") is False and panel.options()["trim_start"] == 5


def test_resize_and_strip(qtbot):
    panel = panel_for(qtbot, "image:webp")
    panel.findChild(QComboBox, "resize").setCurrentText("Max 1920px")
    panel.findChild(QCheckBox, "strip_metadata").setChecked(True)
    assert panel.options() == {"quality": 90, "resize": "1920x1920", "strip_metadata": True}


def test_pdf_dpi(qtbot):
    panel = panel_for(qtbot, "pdf:png")
    panel.findChild(QComboBox, "pdf_dpi").setCurrentText("300 DPI")
    assert panel.options()["pdf_dpi"] == 300


def test_office_has_no_options(qtbot):
    panel = panel_for(qtbot, "office:pdf")
    assert shown(panel, QLabel, "empty") and not shown(panel, QSlider, "quality")


def test_none_disables_save(qtbot):
    panel = panel_for(qtbot, None)
    assert not panel.findChild(QPushButton, "save").isEnabled()


def test_save_button_emits(qtbot):
    panel = panel_for(qtbot, "video:mp4")
    with qtbot.waitSignal(panel.save_requested):
        panel.findChild(QPushButton, "save").click()

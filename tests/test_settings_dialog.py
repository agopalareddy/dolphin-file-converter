import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QInputDialog, QListWidget, QMessageBox, QPushButton,
                               QSpinBox)

from fileconverter.gui.settings_dialog import SettingsDialog
from fileconverter.presets import BUILTIN_BY_ID
from fileconverter.store import config_path, load


@pytest.fixture
def dialog(qtbot, isolated_home):
    st = load()
    dlg = SettingsDialog(st)
    qtbot.addWidget(dlg)
    return dlg, st


def item_for(dlg, preset_id):
    lst = dlg.findChild(QListWidget, "preset_list")
    for row in range(lst.count()):
        if lst.item(row).data(Qt.UserRole) == preset_id:
            return lst.item(row)
    raise KeyError(preset_id)


def select(dlg, preset_id):
    dlg.findChild(QListWidget, "preset_list").setCurrentItem(item_for(dlg, preset_id))


def button(dlg, name):
    return dlg.findChild(QPushButton, name)


def test_hide_builtin_from_menu(dialog, isolated_home):
    dlg, st = dialog
    item_for(dlg, "audio:wav").setCheckState(Qt.Unchecked)
    dlg.accept()
    assert "audio:wav" in st.hidden_builtins
    assert json.loads(config_path().read_text())["hidden_builtins"] == ["audio:wav"]
    menu = isolated_home / "data" / "kio" / "servicemenus" / "fileconverter-audio.desktop"
    assert "audio:mp3" in menu.read_text() and "audio:wav" not in menu.read_text()


def test_builtin_cannot_be_renamed_or_deleted(dialog):
    dlg, st = dialog
    select(dlg, "video:mp4")
    assert not button(dlg, "rename").isEnabled() and not button(dlg, "delete").isEnabled()
    button(dlg, "duplicate").click()
    dlg.accept()
    copy = st.get("user:mp4-h-264-copy")
    assert copy.name == "MP4 (H.264) copy" and copy.options == BUILTIN_BY_ID["video:mp4"].options


def test_rename_and_delete_user_preset(dialog, monkeypatch):
    dlg, st = dialog
    select(dlg, "audio:mp3")
    button(dlg, "duplicate").click()
    select(dlg, "user:mp3-copy")
    assert button(dlg, "rename").isEnabled()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Podcast", True))
    button(dlg, "rename").click()
    assert item_for(dlg, "user:mp3-copy").text().startswith("Podcast")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    button(dlg, "delete").click()
    with pytest.raises(KeyError):
        item_for(dlg, "user:mp3-copy")


def test_cancel_discards_changes(dialog):
    dlg, st = dialog
    select(dlg, "audio:mp3")
    button(dlg, "duplicate").click()
    item_for(dlg, "audio:wav").setCheckState(Qt.Unchecked)
    dlg.reject()
    assert st.user_presets == [] and st.hidden_builtins == set()


def test_trash_toggle_requires_confirmation(dialog, monkeypatch):
    dlg, st = dialog
    box = dlg.findChild(QCheckBox, "trash_originals")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    box.setChecked(True)
    assert not box.isChecked()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    box.setChecked(True)
    dlg.accept()
    assert st.settings.trash_originals is True


def test_parallel_automatic(dialog):
    dlg, st = dialog
    spin = dlg.findChild(QSpinBox, "parallel")
    spin.setValue(3)
    spin.setValue(0)
    assert spin.text() == "Automatic"
    dlg.accept()
    assert st.settings.parallel is None


def test_window_applies_settings(window, monkeypatch, sample_wav):
    [jid] = window.add_files([sample_wav])

    def fake_exec(dlg):
        dlg.findChild(QSpinBox, "parallel").setValue(3)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        dlg.findChild(QCheckBox, "trash_originals").setChecked(True)
        dlg.accept()
        return 1
    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window.open_settings()
    assert window.queue.workers == 3
    assert window.queue.job(jid).output.trash_originals is True

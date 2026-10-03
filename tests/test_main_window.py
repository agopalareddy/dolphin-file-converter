import json
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QInputDialog, QLineEdit, QMessageBox, QRadioButton

from fileconverter import app
from fileconverter.commands import TOOLS
from fileconverter.queue import JobState
from fileconverter.store import config_path


def ids_of(window, job_ids):
    return [window.queue.job(i).preset.id for i in job_ids]


def test_add_files_picks_defaults_and_skips_unsupported(window, sample_mp4, sample_png, tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    ids = window.add_files([sample_mp4, sample_png, tmp_path / "notes.txt"])
    assert ids_of(window, ids) == ["video:mp4", "image:webp"]
    assert "Skipped 1 unsupported file: notes.txt" in window.statusBar().currentMessage()
    assert window.model.rowCount() == 2


def test_folder_expands_recursively(window, tmp_path, _png):
    (tmp_path / "pics" / "sub").mkdir(parents=True)
    shutil.copy2(_png, tmp_path / "pics" / "sub" / "x.png")
    (tmp_path / "pics" / "y.txt").write_text("x")
    ids = window.add_files([tmp_path / "pics"])
    assert [window.queue.job(i).src.name for i in ids] == ["x.png"]


def test_large_folder_adds_quickly(window, tmp_path):
    import time
    folder = tmp_path / "many"
    folder.mkdir()
    for n in range(800):
        (folder / f"img{n:04d}.png").touch()
    window.show()
    started = time.monotonic()
    ids = window.add_files([folder])
    elapsed = time.monotonic() - started
    assert len(ids) == 800 and elapsed < 4, f"took {elapsed:.1f} s"


def test_hidden_dirs_skipped_and_empty_folder_reported(window, tmp_path, _png):
    pics = tmp_path / "pics"
    for sub in (".thumbnails", ".fileconverter-abc", "keep"):
        (pics / sub).mkdir(parents=True)
        shutil.copy2(_png, pics / sub / "x.png")
    ids = window.add_files([pics])
    assert [window.queue.job(i).src.parent.name for i in ids] == ["keep"]
    empty = tmp_path / "notes"
    empty.mkdir()
    (empty / "y.txt").write_text("x")
    assert window.add_files([empty]) == []
    assert window.statusBar().currentMessage() == "No convertible files in notes"


def test_unknown_preset_reported_and_not_started(window, sample_wav):
    [jid] = window.add_files([sample_wav], "audio:nope", start=True)
    assert window.queue.job(jid).state is JobState.PENDING
    assert window.statusBar().currentMessage() == "Unknown preset: audio:nope"


def test_options_after_preset_deleted(window, sample_mp4):
    from fileconverter.presets import BUILTIN_BY_ID
    preset = window.store.add_user_preset("Clip", BUILTIN_BY_ID["video:mp4"], {"quality": 40})
    [jid] = window.add_files([sample_mp4], preset.id)
    window.store.remove_user_preset(preset.id)
    window.table.selectRow(0)
    window.options_panel.findChild(QComboBox, "max_height").setCurrentText("720p")
    assert window.queue.job(jid).preset.options["max_height"] == 720


def test_preset_argument_starts_immediately(qtbot, window, sample_wav):
    with qtbot.waitSignal(window.queue.drained, timeout=30_000):
        [jid] = window.add_files([sample_wav], "audio:flac", start=True)
    assert window.queue.job(jid).state is JobState.DONE
    assert sample_wav.with_suffix(".flac").exists()
    assert window.model.data(window.model.index(0, 2)) == "Done"


def test_preset_argument_ignored_when_it_does_not_fit(window, sample_png):
    [jid] = window.add_files([sample_png], "audio:mp3")
    assert window.queue.job(jid).preset.id == "image:webp"


def test_missing_tool_disables_choice_and_blocks_convert(make_window, sample_mp4):
    win = make_window(tools={**dict.fromkeys(TOOLS, True), "ffmpeg": False})
    [jid] = win.add_files([sample_mp4])
    choices = dict((p.id, tip) for p, tip in win.preset_choices(jid))
    assert choices["video:mp4"] == "Install ffmpeg to enable"
    win.convert()
    assert win.queue.job(jid).state is JobState.PENDING
    assert "Install ffmpeg" in win.statusBar().currentMessage()


def test_options_edit_applies_to_selected(window, sample_mp4, sample_png):
    vid, img = window.add_files([sample_mp4, sample_png])
    window.table.selectRow(0)
    window.options_panel.findChild(QComboBox, "max_height").setCurrentText("720p")
    job = window.queue.job(vid)
    assert job.preset.options["max_height"] == 720 and job.preset.name == "MP4 (H.264) (custom)"
    assert window.queue.job(img).preset.id == "image:webp"


def test_tool_recheck_keeps_half_typed_options(window, sample_wav):
    window.add_files([sample_wav])
    window.table.selectRow(0)
    trim = window.options_panel.findChild(QLineEdit, "trim_start")
    trim.setText("1:")  # mid-typing, not valid yet
    window.recheck_tools()  # e.g. the user switched back to the window
    assert trim.text() == "1:"


def test_change_format_for_selected(window, sample_wav, _wav, tmp_path):
    other = shutil.copy2(_wav, tmp_path / "b.wav")
    a, b = window.add_files([sample_wav, other])
    window.table.selectAll()
    window.set_preset_for_selected(window.store.get("audio:opus"))
    assert ids_of(window, [a, b]) == ["audio:opus", "audio:opus"]


def test_save_as_preset_updates_store_and_menus(window, sample_mp4, monkeypatch, isolated_home):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("WhatsApp video", True))
    [jid] = window.add_files([sample_mp4])
    window.table.selectRow(0)
    window.options_panel.findChild(QComboBox, "max_height").setCurrentText("720p")
    window.options_panel.save_requested.emit()
    assert window.queue.job(jid).preset.id == "user:whatsapp-video"
    saved = json.loads(config_path().read_text())["presets"]
    assert saved[0]["options"]["max_height"] == 720
    menu = isolated_home / "data" / "kio" / "servicemenus" / "fileconverter-video.desktop"
    assert "user:whatsapp-video" in menu.read_text()


def test_format_change_on_done_row_requeues(qtbot, window, sample_wav):
    with qtbot.waitSignal(window.queue.drained, timeout=30_000):
        [jid] = window.add_files([sample_wav], "audio:mp3", start=True)
    window.table.selectRow(0)
    window.set_preset_for_selected(window.store.get("audio:flac"))
    assert window.queue.job(jid).state is JobState.PENDING
    assert window.convert_button.text() == "Convert 1 file"
    with qtbot.waitSignal(window.queue.drained, timeout=30_000):
        window.convert()
    assert window.queue.job(jid).state is JobState.DONE
    assert sample_wav.with_suffix(".flac").exists()


def test_convert_button_counts_pending(qtbot, window, sample_wav, sample_png):
    window.add_files([sample_wav, sample_png])
    assert window.convert_button.text() == "Convert 2 files" and window.convert_button.isEnabled()
    with qtbot.waitSignal(window.queue.drained, timeout=30_000):
        window.convert()
    assert not window.convert_button.isEnabled()


def test_output_settings_apply_to_pending_and_persist(window, sample_wav, tmp_path):
    [jid] = window.add_files([sample_wav])
    window.findChild(QComboBox, "clash").setCurrentText("Skip it")
    window.findChild(QRadioButton, "custom_folder").setChecked(True)
    window.findChild(QLineEdit, "folder").setText(str(tmp_path))
    assert window.queue.job(jid).output.clash == "skip"
    assert window.queue.job(jid).output.folder == tmp_path
    settings = json.loads(config_path().read_text())["settings"]
    assert settings["clash"] == "skip" and settings["output_dir"] == str(tmp_path)


def test_invalid_pattern_blocks_convert(window, sample_wav):
    window.add_files([sample_wav])
    window.findChild(QLineEdit, "pattern").setText("{oops}")
    assert not window.convert_button.isEnabled()
    window.findChild(QLineEdit, "pattern").setText("{name}-x")
    assert window.convert_button.isEnabled()


def test_status_column_wide_enough_for_progress_bar(window, sample_wav):
    window.add_files([sample_wav])
    window.show()
    assert window.table.columnWidth(2) >= 150


@pytest.mark.parametrize("style", ["Fusion", "Breeze"])
def test_progress_bar_is_drawn_horizontally(window, sample_wav, style, qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QStyleFactory, QStyleOptionViewItem

    if style not in QStyleFactory.keys():
        pytest.skip(f"{style} style not installed")
    previous = qapp.style().name()
    qapp.setStyle(style)
    [jid] = window.add_files([sample_wav])
    job = window.queue.job(jid)
    job.state, job.progress = JobState.RUNNING, 0.5
    image = QImage(170, 30, QImage.Format_RGB32)
    image.fill(QColor("white"))
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 170, 30)
    painter = QPainter(image)
    window.table.itemDelegateForColumn(2).paint(painter, option, window.model.index(0, 2))
    painter.end()
    job.state = JobState.PENDING  # faked state; closing must not ask to stop it
    qapp.setStyle(previous)
    row = [image.pixelColor(x, 15) != QColor("white") for x in range(170)]
    assert sum(row) > 60  # a horizontal bar half filled, not a ~6 px vertical sliver


def test_failed_job_shows_retry(qtbot, window, tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"junk")
    with qtbot.waitSignal(window.queue.drained, timeout=30_000):
        [jid] = window.add_files([bad], "video:mp4", start=True)
    assert window.model.data(window.model.index(0, 2)) == "Failed"
    assert window.model.data(window.model.index(0, 2), Qt.ToolTipRole)
    assert [name for name, _, _ in window.row_actions(jid)] == ["Retry", "Show error details",
                                                               "Remove"]


def test_row_buttons_respond_to_clicks(qtbot, window, sample_wav):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    [jid] = window.add_files([sample_wav])
    window.show()
    assert [name for name, _, _ in window.row_actions(jid)] == ["Remove"]
    rect = window.table.visualRect(window.model.index(0, 3))
    target = QPoint(rect.right() - 10, rect.center().y())  # rightmost button: Remove
    QTest.mouseClick(window.table.viewport(), Qt.LeftButton, pos=target)
    assert window.queue.jobs() == []


def test_close_while_converting_asks_then_stops(qtbot, window, long_mp4, monkeypatch):
    answers = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: answers.pop(0))
    window.show()
    [jid] = window.add_files([long_mp4], "video:webm", start=True)
    qtbot.waitUntil(lambda: window.queue.job(jid).state is JobState.RUNNING, timeout=10_000)
    answers.append(QMessageBox.No)
    assert not window.close() and window.queue.job(jid).state is JobState.RUNNING
    answers.append(QMessageBox.Yes)
    assert window.close() and window.queue.job(jid).state is JobState.CANCELLED
    assert not list(long_mp4.parent.glob(".fileconverter-*"))


def test_closing_hidden_window_stops_jobs_without_asking(qtbot, window, long_mp4, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked"))
    [jid] = window.add_files([long_mp4], "video:webm", start=True)
    qtbot.waitUntil(lambda: window.queue.job(jid).state is JobState.RUNNING, timeout=10_000)
    assert window.close() and window.queue.job(jid).state is JobState.CANCELLED


def test_close_when_idle_does_not_ask(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked"))
    assert window.close()


def test_app_hands_off_to_running_instance(monkeypatch, isolated_home):
    sent = []
    monkeypatch.setattr(app, "send_to_running",
                        lambda files, preset: sent.append((files, preset)) or True)
    assert app.main(["--preset", "audio:mp3", "x.wav"]) == 0
    assert sent and sent[0][0][0].endswith("/x.wav") and sent[0][1] == "audio:mp3"

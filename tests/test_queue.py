import shutil
import subprocess
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt

from fileconverter import queue as queue_mod
from fileconverter.presets import BUILTIN_BY_ID
from fileconverter.queue import FINISHED, JobQueue, JobState, OutputSettings

SAME_FOLDER = OutputSettings(folder=None, pattern="{name}", clash="rename",
                             trash_originals=False)


@pytest.fixture
def make_queue(tmp_path, lo_profile):
    def make(workers=2):
        return JobQueue(workers, lo_profile)
    return make


@pytest.fixture
def trashed(monkeypatch):
    calls = []
    monkeypatch.setattr(queue_mod, "_trash", lambda path: calls.append(path))
    return calls


def add(q, src, pid, kind, **output):
    return q.add(src, kind, BUILTIN_BY_ID[pid], replace(SAME_FOLDER, **output))


def run_all(q, qtbot, timeout=90_000):
    with qtbot.waitSignal(q.drained, timeout=timeout):
        q.start()


def leftovers(folder):
    return list(folder.glob(".fileconverter-*"))


def test_converts_and_reports_progress(qtbot, make_queue, long_mp4):
    q = make_queue()
    preset = replace(BUILTIN_BY_ID["video:mp4"], options={"quality": 79, "max_height": 480})
    jid = q.add(long_mp4, "video", preset, SAME_FOLDER)
    seen = []
    q.job_changed.connect(lambda i: seen.append(q.job(i).progress))
    run_all(q, qtbot)
    job = q.job(jid)
    assert job.state is JobState.DONE and job.outputs == [long_mp4.with_name("long (1).mp4")]
    assert any(p is not None and 0 < p < 1 for p in seen)
    assert not leftovers(long_mp4.parent)


def test_rename_clash_never_overwrites(qtbot, make_queue, sample_wav):
    before = sample_wav.read_bytes()
    q = make_queue()
    jid = add(q, sample_wav, "audio:wav", "audio")
    run_all(q, qtbot)
    assert q.job(jid).outputs == [sample_wav.with_name("tone (1).wav")]
    assert sample_wav.read_bytes() == before


def test_skip_clash(qtbot, make_queue, sample_wav):
    existing = sample_wav.with_suffix(".mp3")
    existing.write_bytes(b"")
    q = make_queue()
    jid = add(q, sample_wav, "audio:mp3", "audio", clash="skip")
    run_all(q, qtbot)
    assert q.job(jid).state is JobState.SKIPPED and existing.read_bytes() == b""


def test_output_folder_and_pattern(qtbot, make_queue, sample_wav, tmp_path):
    out = tmp_path / "converted"
    out.mkdir()
    q = make_queue()
    jid = add(q, sample_wav, "audio:mp3", "audio", folder=out, pattern="{name}-{preset}")
    run_all(q, qtbot)
    assert q.job(jid).outputs == [out / "tone-MP3.mp3"]


def test_overwrite_onto_source_with_trash_keeps_output(qtbot, make_queue, sample_png, trashed):
    q = make_queue()
    jid = add(q, sample_png, "image:png", "image", clash="overwrite", trash_originals=True)
    run_all(q, qtbot)
    assert q.job(jid).state is JobState.DONE and q.job(jid).outputs == [sample_png]
    assert sample_png.read_bytes()[:4] == b"\x89PNG" and trashed == []


def test_trash_originals_after_success(qtbot, make_queue, sample_wav, tmp_path, trashed):
    q = make_queue()
    add(q, sample_wav, "audio:mp3", "audio", trash_originals=True)
    add(q, tmp_path / "missing.wav", "audio:mp3", "audio", trash_originals=True)
    run_all(q, qtbot)
    assert trashed == [sample_wav]


def test_trim_past_end_fails_and_keeps_original(qtbot, make_queue, sample_wav, trashed):
    q = make_queue()
    preset = replace(BUILTIN_BY_ID["audio:mp3"], options={"quality": 78, "trim_start": 600})
    jid = q.add(sample_wav, "audio", preset, replace(SAME_FOLDER, trash_originals=True))
    run_all(q, qtbot)
    job = q.job(jid)
    assert job.state is JobState.FAILED and "past the end" in job.error
    assert trashed == [] and not sample_wav.with_suffix(".mp3").exists()


def test_unwritable_folder_fails_cleanly(qtbot, make_queue, sample_wav, tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        q = make_queue()
        bad = add(q, sample_wav, "audio:mp3", "audio", folder=ro)
        good = add(q, sample_wav, "audio:flac", "audio")
        run_all(q, qtbot)
        assert q.job(bad).state is JobState.FAILED
        assert q.job(bad).error.startswith("Can't write to")
        assert q.job(good).state is JobState.DONE
    finally:
        ro.chmod(0o700)


def test_cancel_ffmpeg_leaves_nothing(qtbot, make_queue, long_mp4):
    q = make_queue()
    jid = add(q, long_mp4, "video:webm", "video")
    q.start()
    qtbot.waitUntil(lambda: q.job(jid).state is JobState.RUNNING and q.job(jid).progress,
                    timeout=30_000)
    with qtbot.waitSignal(q.drained, timeout=10_000):
        q.cancel(jid)
    assert q.job(jid).state is JobState.CANCELLED
    assert not leftovers(long_mp4.parent) and not long_mp4.with_suffix(".webm").exists()


def test_cancel_libreoffice_leaves_nothing(qtbot, make_queue, sample_odt, lo_profile):
    q = make_queue()
    jid = add(q, sample_odt, "office:pdf", "document")
    q.start()
    qtbot.waitUntil(lambda: q.job(jid).state is JobState.RUNNING, timeout=10_000)
    qtbot.wait(300)
    with qtbot.waitSignal(q.drained, timeout=10_000):
        q.cancel(jid)
    assert q.job(jid).state is JobState.CANCELLED and not leftovers(sample_odt.parent)

    def no_soffice():
        found = subprocess.run(["pgrep", "-f", lo_profile.as_uri()], capture_output=True)
        return found.returncode == 1
    qtbot.waitUntil(no_soffice, timeout=5_000)


def test_shutdown_stops_everything(qtbot, make_queue, sample_odt, long_mp4, lo_profile):
    q = make_queue()
    office = add(q, sample_odt, "office:pdf", "document")
    video = add(q, long_mp4, "video:webm", "video")
    later = add(q, long_mp4, "audio:mp3", "audio")
    q.workers = 2
    q.start()
    qtbot.waitUntil(lambda: q.job(office).state is JobState.RUNNING
                    and q.job(video).state is JobState.RUNNING, timeout=10_000)
    q.shutdown()
    assert {q.job(i).state for i in (office, video, later)} == {JobState.CANCELLED}
    assert not leftovers(sample_odt.parent) and not leftovers(long_mp4.parent)
    found = subprocess.run(["pgrep", "-f", lo_profile.as_uri()], capture_output=True)
    assert found.returncode == 1


def test_bad_input_fails_with_log(qtbot, make_queue, tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"junk")
    q = make_queue()
    jid = add(q, bad, "video:mp4", "video")
    run_all(q, qtbot)
    job = q.job(jid)
    assert job.state is JobState.FAILED and job.error and "Invalid data" in job.log
    assert not leftovers(tmp_path)


def test_workers_limit_and_single_office(qtbot, make_queue, tmp_path, _wav, sample_odt,
                                         sample_xlsx):
    q = make_queue(workers=2)
    peak = {"all": 0, "office": 0}

    def track(_):
        running = [j for j in q.jobs() if j.state is JobState.RUNNING]
        peak["all"] = max(peak["all"], len(running))
        peak["office"] = max(peak["office"],
                             sum(j.preset.category == "office" for j in running))
    q.job_changed.connect(track)
    for n in range(4):
        add(q, shutil.copy2(_wav, tmp_path / f"t{n}.wav"), "audio:flac", "audio")
    add(q, sample_odt, "office:pdf", "document")
    add(q, sample_xlsx, "office:pdf", "spreadsheet")
    run_all(q, qtbot)
    assert all(j.state is JobState.DONE for j in q.jobs())
    assert peak["all"] <= 2 and peak["office"] == 1


def test_pdf_pages_named_per_page(qtbot, make_queue, sample_pdf):
    q = make_queue()
    jid = add(q, sample_pdf, "pdf:png", "pdf")
    run_all(q, qtbot)
    assert q.job(jid).outputs == [sample_pdf.with_name("doc-1.png"),
                                  sample_pdf.with_name("doc-2.png")]


def test_odd_names(qtbot, make_queue, odd_names):
    q = make_queue()
    for pid, kind in (("video:mp4", "video"), ("image:webp", "image"), ("audio:mp3", "audio")):
        add(q, odd_names[kind], pid, kind)
    run_all(q, qtbot)
    assert all(j.state is JobState.DONE for j in q.jobs())


def test_build_error_fails_job(qtbot, make_queue, sample_png):
    q = make_queue()
    bad = replace(BUILTIN_BY_ID["image:png"], options={"resize": "big"})
    jid = q.add(sample_png, "image", bad, SAME_FOLDER)
    run_all(q, qtbot, timeout=10_000)
    assert q.job(jid).state is JobState.FAILED and "resize" in q.job(jid).error
    assert not leftovers(sample_png.parent)


def test_trash_failure_is_reported(qtbot, make_queue, sample_wav, monkeypatch):
    from fileconverter.gui.queue_model import QueueModel
    monkeypatch.setattr(queue_mod, "_trash", lambda path: False)
    q = make_queue()
    jid = add(q, sample_wav, "audio:mp3", "audio", trash_originals=True)
    run_all(q, qtbot)
    job = q.job(jid)
    assert job.state is JobState.DONE and job.warning == "Couldn't move the original to the Trash"
    model = QueueModel(q)
    assert job.warning in model.data(model.index(0, 2), Qt.ToolTipRole)


def test_waiting_jobs_pick_up_output_changes(qtbot, make_queue, long_mp4, sample_wav):
    q = make_queue(workers=1)
    busy = add(q, long_mp4, "video:webm", "video")
    waiting = add(q, sample_wav, "audio:mp3", "audio")
    q.start()
    qtbot.waitUntil(lambda: q.job(busy).state is JobState.RUNNING, timeout=10_000)
    assert q.job(waiting).state is JobState.WAITING
    q.set_output(waiting, replace(SAME_FOLDER, trash_originals=True))
    assert q.job(waiting).output.trash_originals is True
    q.shutdown()


def test_cancel_escalates_to_sigkill(qtbot, make_queue, sample_png, monkeypatch):
    # A tool that ignores SIGTERM, like a hung converter.
    monkeypatch.setattr(queue_mod, "build",
                        lambda *a, **k: ["sh", "-c", "trap '' TERM; sleep 60 & wait"])
    q = make_queue()
    jid = add(q, sample_png, "image:png", "image")
    q.start()
    qtbot.waitUntil(lambda: q.job(jid).state is JobState.RUNNING, timeout=5_000)
    qtbot.wait(300)
    with qtbot.waitSignal(q.drained, timeout=8_000):
        q.cancel(jid)
    assert q.job(jid).state is JobState.CANCELLED and not leftovers(sample_png.parent)


def test_processes_are_freed(qtbot, make_queue, sample_wav):
    from PySide6.QtCore import QProcess
    q = make_queue()
    add(q, sample_wav, "audio:mp3", "audio")
    run_all(q, qtbot)
    qtbot.waitUntil(lambda: not q.findChildren(QProcess), timeout=2_000)


def test_late_finished_signal_for_removed_job_is_ignored(qtbot, make_queue):
    from PySide6.QtCore import QProcess
    make_queue()._on_finished(999, QProcess(), 0, False)  # must not raise


def test_percent_in_parent_folder(qtbot, make_queue, tmp_path, _png, _pdf):
    folder = tmp_path / "rate 5%x 50%d"
    folder.mkdir()
    q = make_queue()
    img = add(q, shutil.copy2(_png, folder / "pic.png"), "image:webp", "image")
    pdf = add(q, shutil.copy2(_pdf, folder / "doc.pdf"), "pdf:png", "pdf")
    run_all(q, qtbot)
    assert q.job(img).state is JobState.DONE, q.job(img).error
    assert q.job(pdf).state is JobState.DONE, q.job(pdf).error


def test_hidden_office_source(qtbot, make_queue, tmp_path, _odt):
    src = shutil.copy2(_odt, tmp_path / ".notes.odt")
    q = make_queue()
    jid = add(q, src, "office:pdf", "document")
    run_all(q, qtbot)
    assert q.job(jid).state is JobState.DONE, q.job(jid).error
    assert q.job(jid).outputs == [tmp_path / ".notes.pdf"]


def test_retry_after_failure(qtbot, make_queue, tmp_path, _wav):
    src = tmp_path / "later.wav"
    q = make_queue()
    jid = add(q, src, "audio:mp3", "audio")
    run_all(q, qtbot)
    assert q.job(jid).state is JobState.FAILED and q.job(jid).error == "File not found"
    shutil.copy2(_wav, src)
    with qtbot.waitSignal(q.drained, timeout=30_000):
        q.retry(jid)
    assert q.job(jid).state is JobState.DONE


def test_pending_jobs_wait_for_start(qtbot, make_queue, sample_wav):
    q = make_queue()
    jid = add(q, sample_wav, "audio:mp3", "audio")
    qtbot.wait(200)
    assert q.job(jid).state is JobState.PENDING
    q.remove(jid)
    assert q.jobs() == []


def test_clear_finished_keeps_pending(qtbot, make_queue, sample_wav, tmp_path):
    q = make_queue()
    done = add(q, sample_wav, "audio:mp3", "audio")
    run_all(q, qtbot)
    pending = add(q, sample_wav, "audio:flac", "audio")
    q.clear_finished()
    assert [j.id for j in q.jobs()] == [pending] and done != pending
    assert FINISHED >= {JobState.DONE, JobState.SKIPPED}

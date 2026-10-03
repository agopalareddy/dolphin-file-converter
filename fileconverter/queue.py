"""Run conversions with QProcess: parallel workers, progress, cancel, retry."""

import os
import shutil
import signal
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QProcess, QTimer, Signal

from . import naming
from .commands import build, parse_duration, parse_progress, probe_argv
from .options import Options, format_time
from .presets import Preset


class JobState(Enum):
    PENDING = "pending"
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


FINISHED = {JobState.DONE, JobState.FAILED, JobState.CANCELLED, JobState.SKIPPED}


@dataclass(frozen=True)
class OutputSettings:
    folder: Path | None
    pattern: str
    clash: str
    trash_originals: bool


@dataclass
class Job:
    id: int
    src: Path
    kind: str
    preset: Preset
    output: OutputSettings
    state: JobState = JobState.PENDING
    progress: float | None = None
    outputs: list[Path] = field(default_factory=list)
    log: str = ""
    error: str = ""


@dataclass
class _Run:
    process: QProcess | None = None
    workdir: Path | None = None
    folder: Path | None = None
    stem: str = ""
    argv: list[str] = field(default_factory=list)
    duration: float | None = None
    stdout: str = ""
    cancelled: bool = False
    remove_after: bool = False


def _trash(path: Path) -> None:
    QFile.moveToTrash(str(path))


class JobQueue(QObject):
    job_added = Signal(int)
    job_changed = Signal(int)
    job_removed = Signal(int)
    drained = Signal()

    def __init__(self, workers: int, lo_profile: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._workers = workers
        self._lo_profile = lo_profile
        lo_profile.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[int, Job] = {}
        self._runs: dict[int, _Run] = {}
        self._next_id = 1
        self._timer = QTimer(self, singleShot=True, interval=0)
        self._timer.timeout.connect(self._schedule)

    # Public API

    @property
    def workers(self) -> int:
        return self._workers

    @workers.setter
    def workers(self, n: int) -> None:
        self._workers = max(1, n)
        self._timer.start()

    def add(self, src: Path, kind: str, preset: Preset, output: OutputSettings) -> int:
        jid = self._next_id
        self._next_id += 1
        self._jobs[jid] = Job(jid, src, kind, preset, output)
        self.job_added.emit(jid)
        return jid

    def job(self, job_id: int) -> Job:
        return self._jobs[job_id]

    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def set_preset(self, job_id: int, preset: Preset) -> None:
        job = self._jobs[job_id]
        if job.state is JobState.PENDING or job.state in FINISHED:
            job.preset = preset
            self.job_changed.emit(job_id)

    def set_output(self, job_id: int, output: OutputSettings) -> None:
        job = self._jobs[job_id]
        if job.state is JobState.PENDING or job.state in FINISHED:
            job.output = output
            self.job_changed.emit(job_id)

    def start(self, job_ids: Iterable[int] | None = None) -> None:
        ids = list(self._jobs) if job_ids is None else list(job_ids)
        for jid in ids:
            if self._jobs[jid].state is JobState.PENDING:
                self._set(jid, JobState.WAITING)
        self._timer.start()

    def cancel(self, job_id: int) -> None:
        job = self._jobs[job_id]
        if job.state in (JobState.PENDING, JobState.WAITING):
            self._finish(job_id, JobState.CANCELLED)
        elif job.state is JobState.RUNNING:
            run = self._runs[job_id]
            run.cancelled = True
            self._kill(run.process)

    def retry(self, job_id: int) -> None:
        job = self._jobs[job_id]
        if job.state in FINISHED:
            job.outputs, job.log, job.error, job.progress = [], "", "", None
            self._set(job_id, JobState.WAITING)
            self._timer.start()

    def remove(self, job_id: int) -> None:
        if job_id not in self._jobs:
            return
        if self._jobs[job_id].state is JobState.RUNNING:
            self._runs[job_id].remove_after = True
            self.cancel(job_id)
            return
        del self._jobs[job_id]
        self.job_removed.emit(job_id)

    def active_count(self) -> int:
        return sum(j.state in (JobState.WAITING, JobState.RUNNING) for j in self._jobs.values())

    def shutdown(self) -> None:
        """Cancel everything and wait for processes to exit (call before quitting)."""
        for job in self.jobs():
            if job.state is JobState.WAITING:
                self._jobs[job.id].state = JobState.CANCELLED
        for jid, run in list(self._runs.items()):
            run.cancelled = True
            proc = run.process
            self._kill(proc)
            if proc is not None and not proc.waitForFinished(5000):
                proc.kill()
                proc.waitForFinished(1000)
            if jid in self._runs:  # finished signal didn't arrive
                self._finish(jid, JobState.CANCELLED)

    def clear_finished(self) -> None:
        for job in self.jobs():
            if job.state in FINISHED:
                self.remove(job.id)

    # Scheduling

    def _set(self, job_id: int, state: JobState) -> None:
        self._jobs[job_id].state = state
        self.job_changed.emit(job_id)

    def _schedule(self) -> None:
        for job in self.jobs():
            if len(self._runs) >= self._workers:
                break
            if job.state is not JobState.WAITING:
                continue
            if job.preset.category == "office" and any(
                    self._jobs[r].preset.category == "office" for r in self._runs):
                continue
            self._launch(job)

    def _launch(self, job: Job) -> None:
        jid = job.id
        if not job.src.exists():
            job.error = "File not found"
            self._finish(jid, JobState.FAILED)
            return
        folder = job.output.folder or job.src.parent
        try:
            stem = naming.render(job.output.pattern, name=job.src.stem,
                                 preset_name=job.preset.name, today=date.today())
        except ValueError as e:
            job.error = str(e)
            self._finish(jid, JobState.FAILED)
            return
        first = stem + ("-1" if job.preset.category == "pdf" else "")
        if job.output.clash == "skip" and naming.resolve(
                folder, first, job.preset.ext, "skip") is None:
            self._finish(jid, JobState.SKIPPED)
            return
        try:
            workdir = Path(tempfile.mkdtemp(prefix=".fileconverter-", dir=folder))
        except OSError:
            job.error = f"Can't write to {folder}"
            self._finish(jid, JobState.FAILED)
            return
        run = _Run(workdir=workdir, folder=folder, stem=stem)
        self._runs[jid] = run
        job.progress = None
        self._set(jid, JobState.RUNNING)
        try:
            run.argv = build(job.preset, job.src, workdir, lo_profile=self._lo_profile)
        except OSError as e:
            job.error = str(e)
            self._finish(jid, JobState.FAILED)
            return
        if job.preset.category in ("audio", "video"):
            self._start_process(jid, probe_argv(job.src), probe=True)
        else:
            self._start_process(jid, run.argv, probe=False)

    def _start_process(self, jid: int, argv: list[str], probe: bool) -> None:
        run = self._runs[jid]
        proc = QProcess(self)
        proc.setWorkingDirectory(str(run.workdir))  # magick gets relative names
        run.process, run.stdout = proc, ""
        proc.readyReadStandardOutput.connect(lambda: self._on_stdout(jid, proc))
        proc.readyReadStandardError.connect(lambda: self._on_stderr(jid, proc))
        proc.finished.connect(lambda code, status: self._on_finished(jid, proc, code, probe))
        proc.errorOccurred.connect(lambda err: self._on_error(jid, proc, err))
        # Own process group, so cancel also stops children (soffice.bin).
        proc.start("setsid", ["-w", *argv])

    def _kill(self, proc: QProcess | None) -> None:
        if proc is None or proc.state() == QProcess.NotRunning:
            return
        try:
            os.killpg(proc.processId(), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.kill()

    # Process events

    def _on_stdout(self, jid: int, proc: QProcess) -> None:
        run, job = self._runs.get(jid), self._jobs.get(jid)
        if run is None or run.process is not proc:
            return
        text = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        if job.preset.category == "office":
            job.log += text
            return
        run.stdout = (run.stdout + text)[-4096:]
        seconds = parse_progress(run.stdout)
        total = self._effective_duration(job, run)
        if seconds is not None and total:
            progress = min(1.0, seconds / total)
            if job.progress is None or progress - job.progress >= 0.01:
                job.progress = progress
                self.job_changed.emit(jid)

    def _on_stderr(self, jid: int, proc: QProcess) -> None:
        if jid in self._jobs:
            self._jobs[jid].log += bytes(proc.readAllStandardError()).decode(errors="replace")

    def _on_error(self, jid: int, proc: QProcess, err: QProcess.ProcessError) -> None:
        run = self._runs.get(jid)
        if err == QProcess.FailedToStart and run is not None and run.process is proc:
            self._jobs[jid].error = f"Couldn't start {self._tool(run.argv)}"
            self._finish(jid, JobState.FAILED)

    def _on_finished(self, jid: int, proc: QProcess, code: int, probe: bool) -> None:
        run, job = self._runs.get(jid), self._jobs[jid]
        if run is None or run.process is not proc:
            return
        if run.cancelled:
            self._finish(jid, JobState.CANCELLED)
        elif probe:
            run.duration = parse_duration(run.stdout) if code == 0 else None
            start = Options.from_dict(job.preset.options).trim_start or 0
            if run.duration is not None and start >= run.duration:
                # ffmpeg would "succeed" with an empty file; with Trash on
                # that would cost the user the original.
                job.error = (f"Trim start ({format_time(start)}) is past the end of the "
                             f"file ({format_time(run.duration)})")
                self._finish(jid, JobState.FAILED)
                return
            self._start_process(jid, run.argv, probe=False)
        elif code != 0:
            lines = [ln for ln in job.log.splitlines() if ln.strip()]
            job.error = lines[-1] if lines else f"{self._tool(run.argv)} exited with code {code}"
            self._finish(jid, JobState.FAILED)
        else:
            self._collect(job, run)

    def _collect(self, job: Job, run: _Run) -> None:
        # Everything except the input link: LibreOffice names its output after
        # the source, which may itself be a hidden file.
        produced = sorted((p for p in run.workdir.iterdir() if not p.is_symlink()),
                          key=lambda p: (len(p.name), p.name))
        if not produced:
            job.error = f"{self._tool(run.argv)} produced no output"
            self._finish(job.id, JobState.FAILED)
            return
        ext, clash = job.preset.ext, job.output.clash
        try:
            for p in produced:
                stem = run.stem
                if len(produced) > 1:
                    stem += "-" + p.stem.rsplit("-", 1)[-1]
                dest = naming.resolve(run.folder, stem, ext, clash)
                if dest is not None:
                    os.replace(p, dest)
                    job.outputs.append(dest)
        except OSError as e:
            job.error = str(e)
            self._finish(job.id, JobState.FAILED)
            return
        if not job.outputs:
            self._finish(job.id, JobState.SKIPPED)
            return
        if job.output.trash_originals and not any(
                os.path.samefile(o, job.src) for o in job.outputs if job.src.exists()):
            _trash(job.src)
        job.progress = 1.0
        self._finish(job.id, JobState.DONE)

    def _finish(self, jid: int, state: JobState) -> None:
        run = self._runs.pop(jid, None)
        if run is not None and run.workdir is not None:
            shutil.rmtree(run.workdir, ignore_errors=True)
        self._set(jid, state)
        if run is not None and run.remove_after:
            self.remove(jid)
        self._timer.start()
        busy = (JobState.WAITING, JobState.RUNNING)
        if not self._runs and not any(j.state in busy for j in self._jobs.values()):
            self.drained.emit()

    @staticmethod
    def _effective_duration(job: Job, run: _Run) -> float | None:
        if run.duration is None:
            return None
        o = Options.from_dict(job.preset.options)
        end = min(o.trim_end, run.duration) if o.trim_end else run.duration
        return max(0.0, end - (o.trim_start or 0)) or None

    @staticmethod
    def _tool(argv: list[str]) -> str:
        return "soffice" if argv and argv[0] == "flock" else (argv[0] if argv else "converter")

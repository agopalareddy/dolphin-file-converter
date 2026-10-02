"""``fileconvert PRESET FILE...``: convert without opening a window."""

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop

from .commands import detect_tools, required_tools
from .filetypes import kind_of
from .queue import FINISHED, JobQueue, JobState, OutputSettings
from .store import load, lo_profile_path


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    st = load()
    if len(args) < 2:
        _say("Usage: fileconvert PRESET FILE...\nPresets:")
        for p in st.all_presets():
            _say(f"  {p.id:<18} {p.name}")
        return 2
    try:
        preset = st.get(args[0])
    except KeyError:
        _say(f"Unknown preset: {args[0]}")
        return 2
    tools = detect_tools()
    missing = [t for t in required_tools(preset) if not tools.get(t)]
    if missing:
        _say(f"{missing[0]} is not installed")
        return 1

    app = QCoreApplication.instance() or QCoreApplication([])  # noqa: F841 (keeps the loop alive)
    s = st.settings
    output = OutputSettings(Path(s.output_dir).expanduser() if s.output_dir else None,
                            s.pattern, s.clash, trash_originals=False)
    queue = JobQueue(1, lo_profile_path())
    files = [Path(a).absolute() for a in args[1:]]
    total, failed, order = len(files), 0, {}
    for n, src in enumerate(files, 1):
        kind = kind_of(src)
        if kind not in preset.inputs:
            _say(f"Failed: {preset.name} can't convert {src.name}")
            failed += 1
            continue
        order[queue.add(src, kind, preset, output)] = n

    announced = set()

    def report(jid: int) -> None:
        nonlocal failed
        job = queue.job(jid)
        if job.state is JobState.RUNNING and jid not in announced:
            announced.add(jid)
            _say(f"Converting {order[jid]} of {total} to {preset.name}: {job.src.name}")
        elif job.state in FINISHED:
            if job.state is JobState.FAILED:
                failed += 1
                _say(f"Failed: {job.error}")
            else:
                _say("Skipped (file exists)" if job.state is JobState.SKIPPED else "Done")

    if order:
        queue.job_changed.connect(report)
        loop = QEventLoop()
        queue.drained.connect(loop.quit)
        queue.start()
        loop.exec()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

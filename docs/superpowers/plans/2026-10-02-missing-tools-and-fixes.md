# Missing-Tools Help and Review Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Help users install missing conversion tools (warning bar, per-distro command, open a terminal to run it) and fix the review's deferred issues.

**Architecture:** New pure module `installer.py` (os-release parsing, package mapping, install command, terminal argv). New `gui/missing_tools.py` (warning bar + dialog). Remaining fixes are local changes to existing modules.

**Tech Stack:** Python 3.11+, PySide6 6.11, pytest, pytest-qt. Branch `feat/gui-app` (continues the unmerged GUI work).

**Spec:** `docs/superpowers/specs/2026-10-02-missing-tools-and-fixes-design.md` (and the base spec `2026-10-02-gui-app-design.md`)

## Global Constraints

- The app never runs privileged commands itself; installs run in the user's terminal via `sudo`.
- Runtime dependency stays `pyside6` only.
- Tool keys are those of `commands.TOOLS`: `ffmpeg`, `ffprobe`, `magick`, `gs`, `soffice`.
- Packages: Arch `ffmpeg imagemagick ghostscript libreoffice-fresh`; Debian/Ubuntu `ffmpeg ghostscript libreoffice` (no ImageMagick 7); Fedora `ffmpeg ImageMagick ghostscript libreoffice`.
- Commands: Arch `sudo pacman -S --needed <pkgs>`; Debian `sudo apt install <pkgs>`; Fedora `sudo dnf install <pkgs>`.
- Exact copy: bar text `Some formats are unavailable because {names} {is/are}n't installed.`; Debian ImageMagick note `Debian and Ubuntu ship ImageMagick 6, which has no "magick" command. Install ImageMagick 7 from its website to convert images.`; Fedora note `Fedora's ffmpeg can't encode H.264 (MP4). Enable RPM Fusion and install its ffmpeg for MP4 output.`; no-terminal tooltip `No terminal found — copy the command instead`.
- Commit style: Conventional Commits, no `Co-Authored-By` trailers.
- Tests: `QT_QPA_PLATFORM=offscreen python -m pytest`.

## Review Focus

1. **`$TERMINAL` set to something odd** (a path with spaces, or a terminal not in the known list): expected to run as `$TERMINAL -e sh -c …`, never crash. Test in Task 1.
2. **Tools installed while the dialog is open**: Check again must enable formats and hide the bar without restarting. Test in Task 2.
3. **Distro with `ID_LIKE` only** (e.g. CachyOS `ID=cachyos ID_LIKE=arch`, Linux Mint `ID_LIKE="ubuntu debian"`): must map to the right family. Test in Task 1.
4. **Hidden source file whose output lands in a hidden name** (`.notes.odt` → `.notes.pdf`): must be collected and named by the pattern. Test in Task 3.
5. **Retrying or re-converting a row whose source was moved to the Trash**: fails with "File not found", no crash. Covered by existing `test_retry_after_failure`; Task 4 adds the Done→format change→Convert path.

---

### Task 1: Install knowledge (`installer.py`)

**Files:** Create `fileconverter/installer.py`, `tests/test_installer.py`

**Interfaces — Produces:**
- `installer.TOOL_INFO: dict[str, tuple[str, str]]` — tool → (display name, what it enables): `ffmpeg`/`ffprobe` → `("FFmpeg", "audio and video")`, `magick` → `("ImageMagick 7", "images")`, `gs` → `("Ghostscript", "PDF pages")`, `soffice` → `("LibreOffice", "documents")`.
- `installer.read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]` — parses `KEY=value` / `KEY="value"`; missing file → `{}`.
- `installer.family(os_release: Mapping[str, str]) -> str | None` — `"arch"`, `"debian"`, `"fedora"` from `ID` then each word of `ID_LIKE` (`ubuntu` → debian, `rhel`/`centos` → fedora); else `None`.
- `@dataclass(frozen=True) installer.InstallPlan`: `tools: tuple[str, ...]` (display names, deduplicated, order of `TOOLS`), `packages: tuple[str, ...]`, `command: tuple[str, ...] | None`, `notes: tuple[str, ...]`.
- `installer.plan_install(missing: Iterable[str], os_release: Mapping[str, str]) -> InstallPlan` — ffmpeg/ffprobe dedupe to one package; Debian magick contributes no package + the Debian note; Fedora ffmpeg adds the Fedora note; command `None` when no family or no packages.
- `installer.find_terminal(which=shutil.which, env=os.environ) -> list[str] | None` — argv prefix that runs a following command: `$TERMINAL` → `[$TERMINAL, "-e"]`; `konsole` → `["konsole", "-e"]`; `gnome-terminal` → `["gnome-terminal", "--"]`; `kgx` → `["kgx", "--"]`; `xfce4-terminal` → `["xfce4-terminal", "-x"]`; `alacritty` → `["alacritty", "-e"]`; `kitty` → `["kitty"]`; `foot` → `["foot"]`; `xterm` → `["xterm", "-e"]`; none → `None`.
- `installer.terminal_argv(prefix: list[str], command: Sequence[str]) -> list[str]` — `prefix + ["sh", "-c", f"{shlex.join(command)}; echo; printf 'Press Enter to close. '; read _"]`.

- [ ] **Step 1: Write failing tests**

```python
ARCH = {"ID": "cachyos", "ID_LIKE": "arch"}
MINT = {"ID": "linuxmint", "ID_LIKE": "ubuntu debian"}
FEDORA = {"ID": "fedora"}

def test_read_os_release(tmp_path):
    p = tmp_path / "os-release"; p.write_text('ID=cachyos\nID_LIKE="arch"\n# c\nNAME="CachyOS Linux"\n')
    assert read_os_release(p) == {"ID": "cachyos", "ID_LIKE": "arch", "NAME": "CachyOS Linux"}
    assert read_os_release(tmp_path / "missing") == {}

@pytest.mark.parametrize("osr,fam", [(ARCH, "arch"), (MINT, "debian"), (FEDORA, "fedora"),
    ({"ID": "rocky", "ID_LIKE": "rhel centos fedora"}, "fedora"), ({"ID": "nixos"}, None)])
def test_family(osr, fam): assert family(osr) == fam

def test_arch_plan_dedupes_ffmpeg():
    plan = plan_install(["ffmpeg", "ffprobe", "soffice"], ARCH)
    assert plan.packages == ("ffmpeg", "libreoffice-fresh")
    assert plan.command == ("sudo", "pacman", "-S", "--needed", "ffmpeg", "libreoffice-fresh")
    assert plan.tools == ("FFmpeg", "LibreOffice") and plan.notes == ()

def test_debian_has_no_imagemagick7():
    plan = plan_install(["magick", "gs"], MINT)
    assert plan.command == ("sudo", "apt", "install", "ghostscript")
    assert any("ImageMagick 6" in n for n in plan.notes)

def test_debian_only_magick_has_no_command():
    assert plan_install(["magick"], MINT).command is None

def test_fedora_ffmpeg_note():
    plan = plan_install(["ffmpeg"], FEDORA)
    assert plan.command == ("sudo", "dnf", "install", "ffmpeg") and "RPM Fusion" in plan.notes[0]

def test_unknown_distro_lists_tools_without_command():
    plan = plan_install(["gs"], {"ID": "nixos"})
    assert plan.command is None and plan.tools == ("Ghostscript",)

def test_find_terminal_prefers_env_then_konsole():
    which = lambda t: f"/usr/bin/{t}" if t in ("konsole", "xterm") else None
    assert find_terminal(which, {}) == ["konsole", "-e"]
    assert find_terminal(which, {"TERMINAL": "/opt/My Term/term"}) == ["/opt/My Term/term", "-e"]
    assert find_terminal(lambda t: None, {}) is None

def test_terminal_argv_keeps_window_open():
    argv = terminal_argv(["konsole", "-e"], ("sudo", "pacman", "-S", "ffmpeg"))
    assert argv[:4] == ["konsole", "-e", "sh", "-c"]
    assert argv[4].startswith("sudo pacman -S ffmpeg;") and "read _" in argv[4]
```

- [ ] **Step 2: Run** `python -m pytest tests/test_installer.py -q` — expected FAIL (import error).
- [ ] **Step 3: Implement** `installer.py`.
- [ ] **Step 4: Run** — expected PASS.
- [ ] **Step 5: Commit** `feat: work out install commands for missing tools`

---

### Task 2: Warning bar, install dialog, re-detection, CLI hint

**Files:** Create `fileconverter/gui/missing_tools.py`, `tests/test_missing_tools.py`. Modify `fileconverter/gui/main_window.py`, `fileconverter/app.py`, `fileconverter/cli.py`, `tests/test_cli.py`.

**Interfaces:**
- Consumes: Task 1 everything; `commands.detect_tools`.
- Produces:
  - `gui.missing_tools.MissingToolsBar(QFrame)`: `set_missing(tools: Iterable[str]) -> None` (hidden when empty or dismissed; text per Global Constraints, names from `TOOL_INFO`, joined "A and B" / "A, B and C"); signals `install_requested()`; object names `missing_text`, `install`, `dismiss`.
  - `gui.missing_tools.MissingToolsDialog(QDialog)(missing: list[str], plan: InstallPlan, terminal: list[str] | None, parent=None)`: shows tool rows, command field (`objectName="command"`, read-only, `shlex.join`), **Copy** (`copy`), **Install in terminal** (`install`, disabled with the no-terminal tooltip when `terminal` or `plan.command` is None), **Check again** (`check`), notes label. Signals `install_started(QProcess)`, `check_requested()`. Install starts `QProcess` with `terminal_argv(terminal, plan.command)`; launching goes through module-level `_start_process(argv) -> QProcess` so tests can replace it.
  - `MainWindow.recheck_tools() -> None` — `self.tools = detect_tools()` (via module attribute so tests can patch), updates bar, refreshes Convert and the options panel. Called on dialog `check_requested`, on the terminal process `finished`, and in `changeEvent` on `ActivationChange` when active.
  - `MainWindow.missing_tools() -> list[str]` — missing keys in `TOOLS` order, `ffprobe` folded into `ffmpeg`.
  - CLI: after `<tool> is not installed` print `Install it with: <shlex.join(command)>` when a command exists.

- [ ] **Step 1: Write failing tests** (`tests/test_missing_tools.py`, `qtbot`, `make_window` from conftest):

```python
def test_bar_shows_missing_names(make_window):
    win = make_window(tools={**ALL, "ffmpeg": False, "ffprobe": False, "soffice": False})
    bar = win.findChild(MissingToolsBar)
    assert bar.isVisibleTo(win)
    assert bar.findChild(QLabel, "missing_text").text() == (
        "Some formats are unavailable because FFmpeg and LibreOffice aren't installed.")

def test_bar_hidden_when_all_present(window):
    assert not window.findChild(MissingToolsBar).isVisibleTo(window)

def test_dismiss_hides_for_session(make_window): ...  # click dismiss → hidden; recheck_tools with same missing → still hidden

def test_check_again_enables_formats(make_window, monkeypatch, sample_mp4):
    win = make_window(tools={**ALL, "ffmpeg": False})
    [jid] = win.add_files([sample_mp4])
    monkeypatch.setattr(main_window_mod, "detect_tools", lambda: dict(ALL))
    win.recheck_tools()
    assert dict((p.id, t) for p, t in win.preset_choices(jid))["video:mp4"] is None
    assert not win.findChild(MissingToolsBar).isVisibleTo(win)   # Review Focus 2

def test_dialog_command_copy_and_install(qtbot, monkeypatch):
    started = []
    monkeypatch.setattr(missing_tools_mod, "_start_process", lambda argv: started.append(argv) or QProcess())
    plan = plan_install(["ffmpeg"], {"ID": "arch"})
    dlg = MissingToolsDialog(["ffmpeg"], plan, ["konsole", "-e"]); qtbot.addWidget(dlg)
    assert dlg.findChild(QLineEdit, "command").text() == "sudo pacman -S --needed ffmpeg"
    dlg.findChild(QPushButton, "copy").click()
    assert QGuiApplication.clipboard().text() == "sudo pacman -S --needed ffmpeg"
    dlg.findChild(QPushButton, "install").click()
    assert started[0][:4] == ["konsole", "-e", "sh", "-c"]

def test_dialog_without_terminal_or_command(qtbot):
    dlg = MissingToolsDialog(["magick"], plan_install(["magick"], {"ID": "debian"}), None); qtbot.addWidget(dlg)
    install = dlg.findChild(QPushButton, "install")
    assert not install.isEnabled() and "ImageMagick 6" in dlg.findChild(QLabel, "notes").text()

def test_convert_message_points_to_bar(make_window, sample_mp4): ...  # tools ffmpeg False → convert() → message contains "click Install…"
```

In `tests/test_cli.py` extend `test_missing_tool` to assert `"Install it with: sudo pacman -S --needed ffmpeg"` with `installer.read_os_release` patched to `{"ID": "arch"}`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_missing_tools.py tests/test_cli.py -q` — expected FAIL.
- [ ] **Step 3: Implement** `missing_tools.py`; wire the bar above the stack in `MainWindow`, `recheck_tools`, `changeEvent`; CLI hint. `MainWindow` imports `detect_tools` into its module namespace.
- [ ] **Step 4: Run** full suite — expected PASS.
- [ ] **Step 5: Manual check on the real display:** a scratch script builds `MainWindow(..., tools={**ALL, "ffmpeg": False, "soffice": False})`, opens the dialog, and saves `grab()` of both; inspect the images. Do not click Install (it would run sudo in a terminal).
- [ ] **Step 6: Commit** `feat: help install missing conversion tools`

---

### Task 3: Conversion paths (M1, M2, PDF→JPG quality)

**Files:** Modify `fileconverter/commands.py`, `fileconverter/queue.py`, `fileconverter/options.py`, tests `tests/test_commands.py`, `tests/test_conversions.py`, `tests/test_queue.py`, `tests/test_options.py`, `tests/conftest.py`.

**Interfaces:**
- `commands.build` keeps its signature; image and PDF argv use **relative** names (`.in.png[0]`, `out.png`, `page-%d.png`) and must run with cwd = workdir. New `commands.INPUT_LINK_PREFIX = ".in"`.
- `queue` starts every process with `QProcess.setWorkingDirectory(str(workdir))`; `_collect` takes every entry in workdir except names starting with `INPUT_LINK_PREFIX` + ".".
- `options.applicable`: `pdf:jpg` adds `"quality"`.

- [ ] **Step 1: Failing tests**
  - `test_magick_argv_is_relative`: `build(image:png, …)` → argv contains `".in.png[0]"` and ends with `"out.png"`; no absolute path in argv.
  - conftest fixture `percent_dir(tmp_path)` = `tmp_path / "rate 5%x 50%d"`; `test_percent_in_parent_folder` in test_queue: image:webp and pdf:png jobs on samples copied there → DONE.
  - `test_hidden_office_source` in test_queue: copy odt to `.notes.odt`, office:pdf → DONE, outputs `[folder / ".notes.pdf"]` (Review Focus 4).
  - `test_pdf_jpg_quality_applicable`: `"quality" in applicable(BUILTIN_BY_ID["pdf:jpg"])`.
- [ ] **Step 2: Run** — expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `fix: handle odd folder names and hidden source files`

---

### Task 4: Queue robustness (M4, M7 start errors, M8, M9, M12, M14)

**Files:** Modify `fileconverter/queue.py`, `fileconverter/gui/main_window.py`, `fileconverter/gui/queue_model.py`; tests in `tests/test_queue.py`, `tests/test_main_window.py`.

**Interfaces:**
- `JobQueue.set_output` / `set_preset`: also allowed for `WAITING`.
- `JobQueue.set_preset` on a finished job resets it to `PENDING` (clears outputs/error/log/progress).
- `Job.warning: str = ""` — set to `"Couldn't move the original to the Trash"` when `_trash` returns False; `_trash(path) -> bool`.
- `QueueModel` status tooltip shows `job.warning` for DONE when set.
- `_launch`: any exception from `naming`/`build` → job FAILED with `str(e)`, temp dir removed.
- PDF jobs: no skip pre-check.
- `cancel()`: SIGTERM to the group, then a 5 s single-shot timer sends SIGKILL to the group if the process still runs; `shutdown()` fallback uses group SIGKILL.
- Each finished `QProcess` is `deleteLater()`'d; `_on_finished` ignores unknown job ids.
- MainWindow `_output_changed` applies to PENDING and WAITING jobs.

- [ ] **Step 1: Failing tests**
  - `test_build_error_fails_job` — preset with `options={"resize": "big"}` bypassing validation via `Preset(...)` → FAILED, error mentions "resize", no leftovers, queue drains.
  - `test_single_page_pdf_skip_runs_once` — 1-page PDF (fixture `sample_pdf_1page` made by `magick sample_png pdf`) with existing `<stem>.png` and clash skip → SKIPPED, existing file untouched.
  - `test_trash_failure_is_reported` — `_trash` patched to return False → DONE, `job.warning` set, model tooltip contains it.
  - `test_waiting_jobs_pick_up_output_changes` — workers=1, two long jobs, change output via `set_output` on the WAITING one → applied.
  - `test_cancel_escalates_to_sigkill` — job running `sleep` under a fake preset? Use `long_mp4` webm and patch `os.killpg` to drop SIGTERM, then assert CANCELLED within 7 s.
  - `test_format_change_on_done_row_requeues` (main window) — finish a wav→mp3, set preset audio:flac → state PENDING, Convert button counts 1, convert → DONE with .flac.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `fix: make the queue robust to bad input and slow exits`

---

### Task 5: Presets, store validation, folders, unknown preset (M3, M6, M7 load, M13, hidden-category menus)

**Files:** Modify `fileconverter/store.py`, `fileconverter/gui/main_window.py`, `fileconverter/filetypes.py`, `fileconverter/menus.py`; tests in `tests/test_store.py`, `tests/test_main_window.py`, `tests/test_presets.py`, `tests/test_menus.py`.

**Interfaces:**
- `store.load` validates: preset `category` in the five categories, `inputs` ⊆ `filetypes.KINDS`, `Options.from_dict(options)` succeeds and `quality`/`max_height`/`pdf_dpi` are int or None, id matches `^user:[a-z0-9-]+$`; settings `parallel` int ≥1 or None, `trash_originals` bool, `output_dir` str or None. Any failure → existing backup path.
- `filetypes.kind_of`: MIME types `audio/x-mpegurl`, `audio/x-scpls`, `application/vnd.apple.mpegurl` → `None`.
- `MainWindow.add_files`: `rglob` skips anything under a dot-directory; a folder that adds nothing → status `No convertible files in <name>`; unknown `preset_id` → status `Unknown preset: <id>` and `start` is ignored.
- `MainWindow._apply_options` / `_save_preset`: base preset = `store.get(id)` if present else the job's preset.
- `menus.render_menus`: a kind with no shown presets still gets `fileconverter-<kind>.desktop` with `Actions=;` and no action sections (shadows the system copy).

- [ ] **Step 1: Failing tests** — one per bullet: `test_invalid_option_types_backed_up`, `test_invalid_settings_types_backed_up`, `test_playlist_not_audio` (`list.m3u` → None), `test_hidden_dirs_skipped_and_empty_folder_reported`, `test_unknown_preset_reported_and_not_started`, `test_options_after_preset_deleted`, `test_all_hidden_kind_writes_empty_shadow`.
- [ ] **Step 2–4:** run FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit** `fix: validate presets and tidy folder and preset edge cases`

---

### Task 6: Single-instance socket (M5)

**Files:** Modify `fileconverter/instance.py`, `tests/test_instance.py`.

**Interfaces:**
- `instance.server_name()` → `f"{runtime_dir}/dolphin-file-converter.sock"` where runtime_dir = `$XDG_RUNTIME_DIR` if set and a directory, else `QStandardPaths.writableLocation(RuntimeLocation)`, else the old `dolphin-file-converter-<uid>` name.
- `send_to_running`: returns True once connected and the message is fully written; waits up to `timeout_ms` (default 3000) for `ok` but treats no reply as delivered; returns False only when it can't connect or the server answers `error`.

- [ ] **Step 1: Failing tests:** `test_server_name_in_runtime_dir` (monkeypatched `XDG_RUNTIME_DIR=tmp_path`), `test_busy_server_still_counts_as_delivered` (a raw `QLocalServer` in a subprocess that accepts but never replies → `send_to_running` True).
- [ ] **Step 2–4:** FAIL → implement → full suite PASS.
- [ ] **Step 5: Commit** `fix: keep the instance socket private and avoid duplicate windows`

---

### Task 7: Docs and packaging (M10, M11)

**Files:** Modify `README.md`, `pyproject.toml`, `tests/conftest.py`.

- [ ] **Step 1:** `tests/conftest.py`: `_pdf` calls `_need("gs")` so PDF tests skip instead of erroring without Ghostscript. Check with `PATH` limited to a temp dir that symlinks every needed tool except `gs`: `python -m pytest tests/test_queue.py -k pdf -q` → those tests reported as skipped.
- [ ] **Step 2:** `pyproject.toml` `requires = ["setuptools>=77"]`.
- [ ] **Step 3:** README: Formats table video row lists "MP3, AAC, OGG Vorbis, Opus, FLAC, WAV audio only"; Contributing lists Ghostscript; Usage gains a short "Missing tools" paragraph (warning bar → Install… → terminal). Re-run the standard-readme lint in a `dolphin-file-converter` dir copy — expected `no issues found`.
- [ ] **Step 4:** Full suite PASS.
- [ ] **Step 5: Commit** `docs: describe tool installation and fix README details`

---

After Task 7: whole-branch review by a fresh reviewer (most capable model), one fix pass, then the branch-finishing menu.

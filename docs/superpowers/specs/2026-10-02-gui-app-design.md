# File Converter GUI app: design

Date: 2026-10-02
Status: approved in conversation, awaiting spec review

## Goal

Turn dolphin-file-converter from a bash script plus static service menus
into a user-friendly Qt app that works two ways with equal weight:

- opened from the app launcher, files dragged in
- opened from Dolphin's right-click menu with files preloaded

It is published on GitHub for the community and installed via the AUR
(Arch/CachyOS) or `git clone` + `install.sh` (other distros). It uses the
system's ffmpeg, ImageMagick, Ghostscript and LibreOffice.

## Scope (v1)

1. **Quality and options**: quality slider, max video size, image resize,
   trim, remove metadata.
2. **Queue with live progress**: per-file progress, cancel, retry, parallel
   conversions, open output location.
3. **Custom presets**: save format + options under a name; presets appear in
   the format dropdown and in Dolphin's right-click menu.
4. **Output location and naming**: output folder, filename pattern, clash
   rule, optional "move originals to Trash".

Out of scope for v1: free-form ffmpeg argument box, Flatpak, non-KDE file
manager integration (the design must not block it), video merging/splitting,
audio/video stream selection.

## Stack

- Python 3.11+, PySide6 (Qt 6 Widgets). Picks up the Breeze theme and dark
  mode on Plasma.
- Runtime dependency: `pyside6` only (stdlib for everything else; presets in
  JSON so no TOML writer is needed).
- Conversion tools are optional at runtime; missing ones disable the formats
  that need them.
- Tests: `pytest`, `pytest-qt` (both in Arch `extra`).

The bash `fileconvert` script is replaced by the Python CLI with the same
command name and the same `category:format` preset ids, so existing usage
keeps working.

## Components

```
fileconverter/
  presets.py     Preset model, built-in presets, load/save user presets
  options.py     Option schema per category; quality 0–100 → encoder scale
  commands.py    (preset, options, src, out) → argv. Pure, no Qt.
  naming.py      Output path from folder + pattern + clash rule. Pure.
  tools.py       Detects ffmpeg / ffprobe / magick / gs / soffice
  queue.py       Qt job runner: QProcess, progress parsing, parallelism
  menus.py       Generates Dolphin service menus from presets
  instance.py    Single-instance handoff over QLocalServer
  cli.py         `fileconvert` headless command
  app.py         `fileconverter` GUI entry point (argument parsing, startup)
  gui/
    main_window.py   Queue table, options panel, output controls
    options_panel.py Per-category option widgets
    settings.py      Settings dialog incl. preset manager
tests/
packaging/aur/PKGBUILD
data/  fileconverter.desktop (launcher), icon, built-in service menus (generated)
```

Each pure module (`presets`, `options`, `commands`, `naming`) is testable
without Qt or any conversion tool installed.

### Preset model

```json
{
  "id": "user:whatsapp-video",
  "name": "WhatsApp video",
  "category": "video",
  "format": "mp4",
  "options": {"quality": 40, "max_height": 720, "strip_metadata": true},
  "in_menu": true
}
```

- Categories: `audio`, `video`, `image`, `office`, `pdf`.
- Built-in presets reproduce today's 28 presets exactly, with ids such as
  `audio:mp3`, `video:mp4-small`. They are read-only; "Duplicate" creates an
  editable user copy.
- User presets live in `~/.config/dolphin-file-converter/presets.json`
  (respecting `XDG_CONFIG_HOME`) together with `hidden_builtins: [ids]` and
  app settings.
- Corrupt file: rename to `presets.json.bak`, start from built-ins, show a
  one-time notice.

### Options

| Option | Applies to | Mapping |
|---|---|---|
| quality 0–100 | lossy audio, lossy video, JPG/WebP/AVIF | per encoder: x264 CRF 35→16, VP9 CRF 45→20, MP3 `-q:a` 9→0, Vorbis `-q:a` 0→10, AAC/Opus bitrate 64→320k / 48→256k, ImageMagick `-quality` 1→100 |
| max_height | video | `scale=-2:'min(ih,H)'`; choices Original/2160/1440/1080/720/480 |
| resize | image | none, percent, or max width×height (`-resize WxH>`) |
| trim start/end | audio, video | `-ss` / `-to` before output |
| strip_metadata | audio, video, image | ffmpeg `-map_metadata -1`; magick `-strip` |
| pdf_dpi | pdf → image | `-density` (72/150/300) |

Hidden when meaningless: quality for FLAC, WAV, PNG, ICO, GIF and MKV remux;
trim and max_height for MKV remux (stream copy).

Defaults per built-in preset equal the current bash settings, so a
conversion with untouched options produces the same output as today. Each
built-in stores the slider value that maps exactly onto its current encoder
setting (e.g. MP4 → CRF 20, MP3 → `-q:a 2`), and a unit test asserts this
for every built-in.

### Output naming

- Folder: same as source (default) or a chosen folder.
- Pattern: tokens `{name}` (source basename), `{preset}` (preset name),
  `{date}` (YYYY-MM-DD). Default `{name}`. Extension is always the preset's.
- Clash rule: `rename` (default, `name (1).ext`), `overwrite`, `skip`.
- The output path is resolved when the job starts, not when queued.

### Queue and job lifecycle

States: `waiting → running → done | failed | cancelled | skipped`.

- Parallel workers: default `max(1, cores // 2)`, configurable. LibreOffice
  jobs run one at a time (shared profile in
  `~/.cache/dolphin-file-converter/lo-profile`).
- Each job writes to a hidden temp directory in the output folder and
  renames into place on success, so cancel or crash leaves no partial files.
- Progress: ffmpeg `-progress pipe:1` parsed from stdout against the
  ffprobe duration (trim-adjusted). ImageMagick and LibreOffice rows show an
  indeterminate bar.
- Cancel kills the job's process group. Retry re-queues with the same preset
  and options.
- "Move originals to Trash" (off by default, confirm on enable) runs only
  after that job succeeds, using `QFile.moveToTrash`.
- Job output (stderr) kept in memory per job; viewable and copyable from
  the row's "?" button.
- Desktop notification when the queue drains and the window is not focused.

### Single instance and launch modes

- `fileconverter` → empty window.
- `fileconverter FILE...` → files queued, waiting for format choice.
- `fileconverter --preset ID FILE...` → files queued with that preset and
  started immediately.
- If an instance is running (QLocalServer name
  `dolphin-file-converter-<uid>`), the new process sends
  `{"files": [...], "preset": id|null}` as JSON and exits; the running
  window raises and appends the files.

### Dolphin integration

- Top-level "Convert…" entry for all supported MIME types → `fileconverter %F`.
- "Convert to ▸" submenu per category listing presets with `in_menu` →
  `fileconverter --preset ID %F`.
- AUR package installs built-in menus to `/usr/share/kio/servicemenus/`,
  generated at build time by `menus.py`.
- The app writes `~/.local/share/kio/servicemenus/` files for user presets
  and for built-in categories with hidden presets (same filename shadows the
  system copy). Written with the executable bit Plasma requires.

### Main window

- Toolbar: Add files, Clear finished, Settings.
- Queue table: file, "Convert to" dropdown (per row; multi-select edits all),
  status (progress / Done + Open / Failed + Retry + ?), remove/cancel.
  Drop zone hint when empty.
- Default format by category: audio→MP3, video→MP4, image→WebP,
  office→PDF, pdf→PNG.
- Options panel for the selected rows' preset, showing only applicable
  options, with "Save as preset…".
- Output section: same folder / chosen folder, name pattern, clash rule.
- "Convert N files" button.
- Formats needing a missing tool are disabled with tooltip "Install X to
  enable".

### CLI

`fileconvert PRESET FILE...` keeps working with built-in and user preset
ids, honours default output settings, prints progress lines, and exits
non-zero if any file fails. No window, no notification.

## Testing

- Unit (`pytest`): `commands` argv for every built-in preset and option
  combination; `options` quality mapping endpoints; `naming` patterns and
  clash rules; `presets` load/save/hidden/corrupt-file recovery.
- Integration: run real tools on tiny generated samples (sine audio,
  testsrc video at odd size, gradient image, LibreOffice-made odt/xlsx/odp,
  two-page PDF); skipped per tool when not installed. Assert output exists
  and has the expected codec/dimensions.
- GUI smoke (`pytest-qt`, `QT_QPA_PLATFORM=offscreen`): queue files, run,
  verify statuses and outputs; single-instance handoff appends to the queue.

## Packaging

- `pyproject.toml` (setuptools) with entry points `fileconverter` and
  `fileconvert`.
- `data/fileconverter.desktop` launcher + scalable SVG icon.
- `packaging/aur/PKGBUILD`: depends `pyside6`; optdepends ffmpeg,
  imagemagick, ghostscript, libreoffice, with reasons.
- `install.sh` (non-Arch): symlinks launchers that run from the checkout
  with system PySide6, installs the `.desktop` launcher and service menus to
  `~/.local`; `--uninstall` removes them. Replaces the current symlinks.

## Migration

- Existing `~/.local/bin/fileconvert` and `fileconvert-*.desktop` symlinks
  are replaced by `install.sh`; preset ids are unchanged so nothing else
  breaks.
- README rewritten around the app, with screenshots.

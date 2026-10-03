# Missing-tools help and review follow-ups: design

Date: 2026-10-02
Builds on: `2026-10-02-gui-app-design.md`
Status: awaiting review

## Goal

1. When conversion tools are missing, tell the user clearly and make
   installing them one click plus their password, without the app ever
   running privileged commands itself.
2. Fix the costs and minor issues found during the GUI app's final review
   that a real user could hit.

## 1. Missing tools

### What the user sees

- A warning bar at the top of the window when any of ffmpeg, ImageMagick 7,
  Ghostscript or LibreOffice is missing:
  "Some formats are unavailable because FFmpeg and LibreOffice aren't
  installed." with buttons **Install…** and **✕** (hide for this session).
- **Install…** opens a dialog:
  - one row per missing tool: name, what it enables ("audio and video",
    "images", "PDF pages", "documents"), and its package name;
  - the exact install command for their distro in a read-only field with a
    **Copy** button;
  - **Install in terminal**: opens their terminal running that command.
    `sudo` asks for their password there; that is the approval. The terminal
    stays open at the end ("Press Enter to close") so they can read the result;
  - distro notes where needed (see table);
  - **Check again** re-detects tools.
- Tools are re-detected when the terminal process exits and whenever the
  window is re-activated, so formats enable themselves after installing
  without restarting the app.
- The existing per-format tooltip ("Install ffmpeg to enable") stays, and
  the Convert status message gains "— click Install… in the yellow bar".
- `fileconvert` (CLI) prints the install command after
  "`<tool>` is not installed".

### Distros and packages

Detected from `/etc/os-release` `ID` and `ID_LIKE`.

| Tool | Arch (`pacman -S --needed`) | Debian/Ubuntu (`apt install`) | Fedora (`dnf install`) |
|---|---|---|---|
| ffmpeg, ffprobe | `ffmpeg` | `ffmpeg` | `ffmpeg-free` + note: needs RPM Fusion for H.264 |
| magick | `imagemagick` | none + note: ships ImageMagick 6 | `ImageMagick` |
| gs | `ghostscript` | `ghostscript` | `ghostscript` |
| soffice | `libreoffice-fresh` | `libreoffice` | `libreoffice` |

Other distros: no command; the dialog lists the tools to install with the
system's package manager.

### Terminals

First found of: `$TERMINAL`, `konsole`, `gnome-terminal`, `kgx`,
`xfce4-terminal`, `alacritty`, `kitty`, `foot`, `xterm`. None found: the
Install button is disabled with tooltip "No terminal found — copy the
command instead".

## 2. Review follow-ups

| Issue | Fix |
|---|---|
| Parent folder with `%d`/`%x` breaks magick | Run magick with the work dir as cwd and relative names |
| Hidden office files fail | Collector ignores only the app's own input link |
| Folder drops: hidden dirs, silent empty folders, `.m3u` | Skip hidden dirs; message "No convertible files in <folder>"; playlists not audio |
| Trash setting change skips waiting jobs | Output settings also update WAITING jobs |
| Second launch can open a duplicate window; socket in /tmp | Socket in `$XDG_RUNTIME_DIR`; a connected, written message counts as delivered |
| Unknown `--preset` uses the default silently | Status bar "Unknown preset: <id>", files added but not started |
| Bad presets.json content can hang a job | Validate on load (back up if invalid); any error while starting a job fails that job |
| Single-page PDF skip check uses the wrong name | No pre-check for PDF pages; skip is decided per page |
| Trash failures ignored | Job stays Done; tooltip "Couldn't move the original to the Trash" |
| README/test inaccuracies | Video menu lists all six audio formats; Ghostscript in Contributing; PDF tests skip without gs |
| setuptools floor | `setuptools>=77` |
| Process cleanup | Guard late signals, free QProcess objects, SIGKILL the group after 5 s if SIGTERM didn't stop it |
| Deleted preset breaks options panel | Fall back to the job's own preset |
| Format change on Done/Cancelled/Skipped rows does nothing | Changing the format resets the row to Ready |
| Hiding every preset of a category doesn't hide it on AUR installs | Write a shadow menu file with no actions |
| PDF→JPG quality not adjustable | Show the quality slider for PDF→JPG |

Not changing: notify-send for notifications, the quality-50 split for MP4
speed/audio bitrate, quiet skipping of unsupported files inside folders
(now with the empty-folder message), the toolbar rendering (needs a human
look on screen first).

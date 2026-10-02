# File Converter for Dolphin

Right-click any file in Dolphin and pick **Convert to → format**. Inspired by
[Tichau/FileConverter](https://github.com/Tichau/FileConverter) on Windows,
rebuilt for KDE Plasma as a small shell script and a set of service menus.

- Works on many files at once, with a progress dialog and a Cancel button
- Output is saved next to the original and never overwrites anything
  (`name (1).ext` instead)
- A notification when the batch is done; failures keep a log in
  `~/.local/state/fileconvert/`

## Formats

| Right-click on | Convert to |
|---|---|
| Audio | MP3, AAC (M4A), OGG Vorbis, Opus, FLAC, WAV |
| Video | MP4 (H.264), MP4 (smaller file), WebM (VP9), MKV (no re-encode), animated GIF, plus MP3 / AAC / FLAC audio only |
| Images | PNG, JPG, WebP, AVIF, GIF, ICO, PDF |
| Word documents (DOC, DOCX, ODT, RTF) | PDF, DOCX, ODT |
| Spreadsheets (XLS, XLSX, ODS, CSV) | PDF, XLSX, ODS, CSV |
| Presentations (PPT, PPTX, ODP) | PDF, PPTX, ODP |
| PDF | PNG or JPG, one image per page |

## Requirements

KDE Plasma 6 with Dolphin, plus:

| Tool | Used for | Arch | Debian / Ubuntu | Fedora |
|---|---|---|---|---|
| ffmpeg | audio, video | `ffmpeg` | `ffmpeg` | `ffmpeg` (RPM Fusion) |
| ImageMagick 7 | images, PDF pages | `imagemagick` | `imagemagick` | `ImageMagick` |
| Ghostscript | PDF pages | `ghostscript` | `ghostscript` | `ghostscript` |
| LibreOffice | documents | `libreoffice-fresh` | `libreoffice` | `libreoffice` |
| kdialog, qdbus | progress dialog | `kdialog`, `qt6-tools` | `kdialog`, `qdbus-qt6` | `kdialog`, `qt6-qttools` |

You only need the tools for the formats you use. ImageMagick 7 is required
because the script calls `magick`; Debian and Ubuntu releases that ship
ImageMagick 6 won't work for images.

## Install

```bash
git clone https://github.com/agopalareddy/dolphin-file-converter.git
cd dolphin-file-converter
./install.sh
```

This symlinks `fileconvert` into `~/.local/bin` and the service menus into
`~/.local/share/kio/servicemenus`. Open a new Dolphin window and right-click
a file. `~/.local/bin` must be on your session `PATH` (it is by default on
most distros).

To remove it:

```bash
./install.sh --uninstall
```

## Command line

The script works on its own too:

```bash
fileconvert video:webm clip.mp4 other.mov
FILECONVERT_NOGUI=1 fileconvert image:webp *.png
```

Run `fileconvert` with no arguments to list every preset. To change quality
settings or add a format, edit the `case` block at the top of `fileconvert`
and add a matching `[Desktop Action]` to the file in `servicemenus/`.

## License

MIT

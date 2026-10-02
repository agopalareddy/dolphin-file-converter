#!/usr/bin/env bash
# Install File Converter for the current user, running from this checkout:
# launchers in ~/.local/bin, the app menu entry and icon, and Dolphin's
# right-click menus. --uninstall removes everything this script installs.

set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin_dir=$HOME/.local/bin
data_dir=${XDG_DATA_HOME:-$HOME/.local/share}
menu_dir=$data_dir/kio/servicemenus
app_file=$data_dir/applications/fileconverter.desktop
icon_file=$data_dir/icons/hicolor/scalable/apps/fileconverter.svg

# Links left by the earlier bash-only version.
remove_old_version() {
  rm -f -- "$menu_dir"/fileconvert-*.desktop
  [[ -L $bin_dir/fileconvert ]] && rm -f -- "$bin_dir/fileconvert"
  return 0
}

if [[ ${1:-} == --uninstall ]]; then
  remove_old_version
  rm -f -- "$bin_dir/fileconverter" "$bin_dir/fileconvert" "$app_file" "$icon_file" \
    "$menu_dir"/fileconverter-*.desktop
  echo "File Converter removed."
  exit
fi

if ! python3 -c "import PySide6" 2>/dev/null; then
  cat >&2 <<'EOF'
Install PySide6 first:
  Arch:          sudo pacman -S pyside6
  Debian/Ubuntu: sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtnetwork python3-pyside6.qtdbus
  Fedora:        sudo dnf install python3-pyside6
EOF
  exit 1
fi

remove_old_version
mkdir -p -- "$bin_dir" "$menu_dir" "${app_file%/*}" "${icon_file%/*}"

quoted=${repo//\'/\'\\\'\'}
for pair in fileconverter:app fileconvert:cli; do
  name=${pair%%:*}
  rm -f -- "$bin_dir/$name"
  printf '#!/bin/sh\nPYTHONPATH='\''%s'\''${PYTHONPATH:+:$PYTHONPATH} exec python3 -m fileconverter.%s "$@"\n' \
    "$quoted" "${pair#*:}" >"$bin_dir/$name"
  chmod 755 -- "$bin_dir/$name"
done

install -m 644 -- "$repo/data/fileconverter.desktop" "$app_file"
install -m 644 -- "$repo/data/fileconverter.svg" "$icon_file"
PYTHONPATH=$repo python3 -m fileconverter.menus "$menu_dir"
if command -v update-desktop-database >/dev/null; then
  update-desktop-database -q "${app_file%/*}" || true
fi

echo "File Converter installed. Open a new Dolphin window and right-click a file."
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "Note: $bin_dir is not on your PATH; add it so Dolphin can find fileconverter." >&2 ;;
esac

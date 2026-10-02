#!/usr/bin/env bash
# Link fileconvert and its Dolphin service menus into ~/.local, so edits
# in this checkout take effect immediately. --uninstall removes the links.

set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin_dir=$HOME/.local/bin
menu_dir=${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus

if [[ ${1:-} == --uninstall ]]; then
  rm -fv -- "$bin_dir/fileconvert" "$menu_dir"/fileconvert-*.desktop
  exit
fi

mkdir -p -- "$bin_dir" "$menu_dir"
# Plasma ignores service menus in the home directory unless executable.
chmod +x -- "$repo/fileconvert" "$repo"/servicemenus/*.desktop
ln -sfv -- "$repo/fileconvert" "$bin_dir/fileconvert"
ln -sfv -- "$repo"/servicemenus/*.desktop "$menu_dir/"

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "Note: $bin_dir is not on your PATH; Dolphin won't find fileconvert." >&2 ;;
esac

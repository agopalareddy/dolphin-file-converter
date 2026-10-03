#!/usr/bin/env bash
# Install into a throwaway HOME, check every installed piece, uninstall,
# and check nothing is left behind.
set -uo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
home=$(mktemp -d)
trap 'rm -rf -- "$home"' EXIT
export HOME=$home
unset XDG_DATA_HOME XDG_CONFIG_HOME XDG_CACHE_HOME
data=$home/.local/share
failed=0

check() { # description, command...
  local what=$1
  shift
  if "$@"; then echo "ok   $what"; else echo "FAIL $what"; failed=1; fi
}

"$repo/install.sh" >/dev/null || { echo "FAIL install.sh exited $?"; exit 1; }

check "fileconverter launcher is executable" test -x "$home/.local/bin/fileconverter"
check "fileconvert launcher is executable" test -x "$home/.local/bin/fileconvert"
"$home/.local/bin/fileconvert" >"$home/out" 2>&1
check "fileconvert without args exits 2" test $? -eq 2
check "fileconvert prints usage" grep -q "Usage: fileconvert" "$home/out"
check "Convert… menu is executable" test -x "$data/kio/servicemenus/fileconverter-open.desktop"
check "video menu installed" test -f "$data/kio/servicemenus/fileconverter-video.desktop"
check "app launcher installed" test -f "$data/applications/fileconverter.desktop"
check "icon installed" test -f "$data/icons/hicolor/scalable/apps/fileconverter.svg"

# Starting the app syncs the menus; that must not remove the installed ones.
XDG_DATA_DIRS=$home/no-system-dirs PYTHONPATH=$repo python3 -c \
  "from fileconverter.menus import sync_user_menus; from fileconverter.store import load; sync_user_menus(load())"
check "menus survive the app's startup sync" test -f "$data/kio/servicemenus/fileconverter-video.desktop"

"$repo/install.sh" --uninstall >/dev/null
check "launchers removed" test ! -e "$home/.local/bin/fileconverter" -a ! -e "$home/.local/bin/fileconvert"
check "menus removed" test -z "$(find "$data/kio/servicemenus" -name 'fileconverter-*' 2>/dev/null)"
check "launcher and icon removed" test ! -e "$data/applications/fileconverter.desktop" \
  -a ! -e "$data/icons/hicolor/scalable/apps/fileconverter.svg"

exit $failed

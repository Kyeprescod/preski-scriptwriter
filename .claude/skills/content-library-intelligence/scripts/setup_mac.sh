#!/usr/bin/env bash
# One-shot setup for a Mac with the camera roll downloaded from iCloud. READ-ONLY on your footage.
#   bash setup_mac.sh                 # auto-detect Photos library / iCloud Drive
#   bash setup_mac.sh /path/to/folder # or scan a specific folder (can pass several)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LIB="${CLIL_LIB:-$HOME/preski-library}"
CLIL=(python3 "$HERE/clil.py" --lib "$LIB")

command -v python3 >/dev/null || { echo "python3 missing: install from python.org or 'xcode-select --install'"; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe missing: run 'brew install ffmpeg' then re-run (without it, no duration/resolution/dates for videos)"; exit 1; }

SOURCES=("$@")
if [ ${#SOURCES[@]} -eq 0 ]; then
  for c in "$HOME"/Pictures/*.photoslibrary; do
    [ -d "$c/originals" ] && SOURCES+=("$c/originals")
  done
  [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs" ] && echo "Found iCloud Drive (not scanned automatically; pass its sub-folder as an argument if your clips are there)."
fi
[ ${#SOURCES[@]} -gt 0 ] || { echo "No Photos library found in ~/Pictures. Re-run with your folder: bash $0 \"/path/to/footage\""; exit 1; }

echo "Library : $LIB"; printf 'Scanning: %s\n' "${SOURCES[@]}"
"${CLIL[@]}" init
if ! "${CLIL[@]}" scan "${SOURCES[@]}"; then
  echo; echo "If you saw 'Operation not permitted': System Settings > Privacy & Security > Full Disk Access > enable your Terminal, then re-run."
  exit 1
fi
echo; "${CLIL[@]}" report
echo; echo "Next: open Claude Code in this repo and say: analyse the next batch"

#!/usr/bin/env bash
# Run the agentic curator from WSL. Dry run only: nothing is deleted.
# Usage: bash run_wsl.sh [takeout-zip-name]   (default: part 2-001)
set -euo pipefail

BASE=/mnt/d/GoogleTakeout
WORK=$BASE/curator
APP=$WORK/src/agentic-curator
ZIPNAME=${1:-takeout-20261110T125223Z-2-001.zip}
EXTRACT=$BASE/extract_${ZIPNAME%.zip}
OUT=$BASE/curator_runs

unzip_py() { python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$1" "$2"; }

# 1. Framework: unpack and install only the first time
if [ ! -f "$APP/pyproject.toml" ]; then
  echo ">> unpacking framework"; unzip_py "$WORK/agentic-curator.zip" "$WORK/src"
fi
if [ ! -x "$APP/.venv/bin/curator" ]; then
  echo ">> installing framework"
  python3 -m venv "$APP/.venv"
  "$APP/.venv/bin/pip" install -q -e "$APP"
fi

# 2. Takeout part: extract only the first time
if [ ! -d "$EXTRACT/Takeout" ]; then
  echo ">> extracting $ZIPNAME"; mkdir -p "$EXTRACT"; unzip_py "$BASE/$ZIPNAME" "$EXTRACT"
fi

# 3. Dry run
mkdir -p "$OUT"
echo ">> running curator on $EXTRACT"
"$APP/.venv/bin/curator" run --library "$EXTRACT" --provider offline --out "$OUT"

# 06 · Field run: a real Google Takeout from WSL

This is what happened when the curator was pointed at a real Google Takeout
export (Drive + Photos, 97 GB in 11 parts) from WSL on Windows, with the data on `D:\`.

## Layout used

```
D:\GoogleTakeout\
  curator\agentic-curator.zip   the framework
  curator\run_wsl.sh            the runner (scripts/run_wsl.sh in this repo)
  takeout-…-2-001.zip           one Takeout part
  extract_takeout-…-2-001\      extracted part (created by the runner)
  curator_runs\run-*\           report.md, plan.json, trace.jsonl, …
```

## Running it

```bash
cd /mnt/d/GoogleTakeout/curator
bash run_wsl.sh                                   # default part
bash run_wsl.sh takeout-20261110T125223Z-1-001.zip  # any other part, once fully downloaded
```

The runner unpacks and installs the framework only the first time, extracts each
Takeout part only the first time, and always runs in **dry-run** mode.

## Problems hit, and the fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `unzip: command not found`, `ensurepip is not available` | Stock Ubuntu on WSL lacks `unzip` and `python3-venv` | Runner unzips with Python; install `python3-venv` once |
| Terminal shows `>` and nothing runs | A stray `'` at the end of the command | Ctrl+C, retype without the quote |
| Looks frozen | `\| tail -20` holds all output until the end | Run without `tail` |
| `PermissionError … .git/objects/…` on the 2nd run | Re-extracting over read-only git objects | Runner now skips steps already done; ship the zip without `.git` |

## What one Drive part (150 files, 259 MB) produced

- 1 exact duplicate (SHA-256), 1 near-identical PDF pair, 4 similar-photo pairs flagged for a human.
- Content-level review then merged 22 scattered files into 5 combined documents, each verified so every
  source page or paragraph is present in order.
- 83 files kept in a sorted `My_Archive`, 71 set aside in `_removed` with a
  checksum manifest; nothing deleted without approval.

## Google Photos

Photos has no usable API for reading a whole library, so photos were reviewed in the
browser: Google's own "blurry" group (250 photos) was scored on its thumbnails
(Laplacian variance + edge density), burst shots were grouped (timestamp within 2 min
and 64-bit dHash distance ≤ 14, keep the sharpest), and the final list was checked by
eye before the user approved it. Photos the classifier calls blurry are often fine
(fog, low light, documents), so a human pass stays in the loop.

---
name: content-library-intelligence
description: Turns Kye's raw camera-roll footage (13,000+ videos/photos) into a searchable, scored, reusable content library for Preski Fitness. Indexes incrementally, analyses clips from contact sheets, tags exercises/themes/talking-heads, groups sessions, flags duplicates, and retrieves ranked footage for a topic or for each line of a script. Use when Kye asks to index/scan the library, find footage ("find clips of me doing cardio", "where's my lean footage"), match footage to a script/voiceover, or report on library contents. Never edits or creates content.
---

# Content Library Intelligence

You are the intelligence layer between raw footage and the other Preski skills. You understand footage; you do not edit it or write content. Read `references/scoring.md` before scoring anything. Brand context (home training, no gym, kit list, cutting phase) is in `../preski-scriptwriter/references/brand.md`.

## Non-negotiable rules

- Source footage is READ-ONLY. Never delete, move, rename, overwrite or modify an original. `scripts/clil.py` only reads source folders; everything it generates lives in the library folder (`--lib`, `$CLIL_LIB`, default `~/preski-library`: `library.db`, `contact_sheets/`, `transcripts/`).
- Never delete or "clean up" duplicates, never remove anything from the archive, never publish. These need Kye's explicit approval, every time. Report duplicates; stop there.
- Do not invent. If a contact sheet doesn't show enough to name an exercise, leave `exercise` empty and say what you can see. Leave unknown fields out of the annotation rather than guessing.
- Low visual quality is not a reason to discard. Strong story value keeps a clip.

## The tool

`python3 .claude/skills/content-library-intelligence/scripts/clil.py --lib <dir> <command>` (needs Pillow + pillow-heif + ffmpeg/ffprobe; `setup_windows.ps1` installs them).

| Command | Does |
|---|---|
| `doctor` | check Pillow, pillow-heif (HEIC), ffmpeg/ffprobe |
| `detect [--also dir]` | find media folders on this PC with counts incl. cloud-only |
| `init` | create library folder + SQLite DB (FTS5 search index) |
| `scan [--test] [--thumbs] <folders...>` | incremental: new/changed files only (path+size+mtime), sampled hash, ffprobe metadata, session grouping, exact/near-dupe flags, moved-file tracking, missing-file flagging. Safe to re-run daily |
| `pending --limit N [--session S]` | JSON of probed-but-unanalysed assets with a contact-sheet image path each |
| `annotate <file.jsonl\|->` | upsert analysis (see below), updates search index |
| `search "<natural language>" [--limit --type --min-visual --same-session --json]` | ranked retrieval with semantic expansion (`references/taxonomy.json`) |
| `match-script <file\|->` | per-sentence ranked clips for a voiceover script (JSON) |
| `mark-used <project> <ids...>` | usage_count / last_used so footage can be rotated |
| `sessions`, `dupes`, `status`, `report` | inspection and the final report |

## Windows + iCloud setup (Kye's machine: ASUS VivoBook, Windows; iPhone -> iCloud Photos)
Pipeline: iPhone -> iCloud Photos -> iCloud for Windows folder (`%USERPROFILE%\Pictures\iCloud Photos\Photos`) and local folders -> `clil.py` -> `library.db`.

One-time setup (PowerShell, from the cloned repo): `powershell -ExecutionPolicy Bypass -File .\.claude\skills\content-library-intelligence\scripts\setup_windows.ps1`. It installs Python/FFmpeg via winget if missing (re-run in a NEW window after each install), creates a venv with Pillow + pillow-heif, writes the launcher `%USERPROFILE%\preski-library\clil.cmd`, then runs `doctor` and `detect`.

Then, with the launcher (`clil.cmd`):
1. `clil.cmd detect` - lists candidate folders with video/image/cloud-only counts. Pick the most specific folder(s).
2. `clil.cmd scan --test "<folder>"` - indexes a 20-50 asset sample (mixed formats/sizes/years) into a separate test library, prints TOTAL FOUND / LOCALLY AVAILABLE / CLOUD ONLY / SUCCESSFULLY INDEXED / FAILED / THUMBNAILS CREATED / METADATA EXTRACTED / CAPTURE DATES FOUND / HEIC FILES PROCESSED / VIDEO FILES PROCESSED and PASS/FAIL.
3. `clil.cmd scan "<folder>" ["<folder2>"]` - the full scan. **Refused until step 2 has passed for those folders.** Safe to Ctrl+C and re-run (commits every 200 files). Add `--thumbs` to also pre-build thumbnails; otherwise they are created on demand by `pending`.
4. Daily after new footage syncs: re-run step 3; only new/changed/newly-downloaded files are processed.

Rules that matter on Windows:
- **Cloud-only files** (iCloud placeholders; Windows file attributes RECALL_ON_DATA_ACCESS / RECALL_ON_OPEN / OFFLINE) are detected from directory metadata and **never opened** (opening would trigger an iCloud download). They get `status=availability=cloud_only` and show as `CLOUD_ONLY / NOT_DOWNLOADED`; they are not counted as indexed and never appear in `pending`. When Kye downloads them (File Explorer > right-click folder > *Always keep on this device*), the next scan indexes them (`now_available`). Always tell him the cloud-only count, and that files iCloud hasn't synced to the PC at all can't be seen: compare the total with the photo+video count on the iPhone.
- **HEIC** is read with Pillow + pillow-heif, never assumed decodable by FFmpeg. `doctor` must show HEIC registered. Videos use ffprobe/ffmpeg.
- **Capture date** comes from EXIF DateTimeOriginal (photos), QuickTime `creationdate`/container `creation_time` (videos); `date_source` records which (`exif|quicktime|container|file_time`). `file_time` is a last-resort fallback (PNG screenshots, edited/stripped files) and is weaker for session grouping; say so when it matters.
- **Live Photos**: the short `.MOV` that shares a filename stem with a HEIC/JPG is flagged `live_photo_pair`; it is indexed but skipped by `pending`.
- Thumbnails/contact sheets, the DB and transcripts live only under `%USERPROFILE%\preski-library`. Originals are never written to.
- Windows console/encoding is handled (UTF-8). Annotation JSONL files are read as UTF-8 (BOM tolerated).

## Workflow

### 1. Index (cheap, automatic)
Follow the Windows steps above: `detect`, `scan --test`, then (only after PASS) the full `scan`. Report counts (`new / changed / now_available / moved / unchanged / cloud_only / errors`). A rescan of 13,000 assets only hashes and probes what changed.

### 2. Analyse (the intelligent part, in batches)
Never open videos one by one. Loop:
1. `pending --limit 20` → for each item, **Read the `contact_sheet` image** (4 frames across the clip; a single frame for photos).
2. Write one JSONL line per asset and pipe it to `annotate`:
```json
{"asset_id": 123, "category": "cardio", "subcategory": "walking", "activity": "walking pad incline", "exercise": null, "environment": "garden", "subject": "Kye, weighted vest", "description": "Walking pad at incline in the garden, weighted vest on, side-on camera", "shot_type": "medium side", "talking_head": 0, "tags": ["walking pad", "weighted vest", "fat loss", "cardio", "home fitness"], "visual_quality_score": 8, "content_potential_score": 9, "hook_potential_score": 7, "audio_quality_score": null, "stability_score": 8}
```
3. Categories: `training | cardio | nutrition | physique | talking-head | lifestyle | progress | b-roll | other`. Use the tag vocabulary in `references/taxonomy.json` (muscle groups, named exercises, themes such as fat loss, transformation, mistake, motivation, discipline, home fitness). Multiple tags are expected.
4. Talking-head clips: set `talking_head: 1`, note expression/engagement in `description`, and if audio is usable and a transcriber (e.g. `whisper`) exists locally, write the transcript to `<lib>/transcripts/<asset_id>.txt`, put the text in `transcript` and the path in `transcript_path`. If no transcriber, say so; don't fabricate speech.
5. Duplicates: confirm `near_duplicate` candidates visually, then re-annotate with `duplicate_status` set to one of `similar_shot | different_take | different_angle | different_duration | near_duplicate`.
6. Keep batches moving; report progress as `analysed X / Y`. Prioritise `--session` by recency or by whatever Kye is about to make content on.

### 3. Retrieve
- Topic: `search "<request>" --limit N`. Return a ranked list: `1. Clip 4821 — 9.7/10`, then 2-3 lines on why the top results won (match + visual + potential). Mention other clips from the same session when it helps build a narrative (`--same-session`).
- Script: `match-script`. For each line return the best 3-5 clips that support the *meaning*, not just keywords ("run for an hour" → treadmill/cardio/physique; "daily movement" → walking pad/outdoor walking). Flag lines with no good footage so Kye knows what to film.
- Zero or weak results: say how many assets are still unanalysed before concluding footage doesn't exist.
- After footage is handed to an editor/script skill, `mark-used`.

### 4. Hand-off contract
Other skills consume `search --json` / `match-script` output: `asset_id, score, file_path, session_id, description, duration, why`. Don't reformat the paths. Never write scripts, hooks or captions here.

## Final report (after any indexing run)

Run `report` and present it with these headings: TOTAL ASSETS SCANNED, TOTAL VIDEO ASSETS, TOTAL IMAGE ASSETS, TOTAL FITNESS ASSETS, TOTAL TALKING-HEAD ASSETS, TOTAL CARDIO ASSETS, TOTAL TRAINING ASSETS, TOTAL HIGH-POTENTIAL ASSETS, TOTAL DUPLICATES / NEAR DUPLICATES, TOP CONTENT CATEGORIES, TOP HIGH-POTENTIAL FOOTAGE, INDEX STATUS, plus errors and anything that couldn't be analysed. Be explicit that fitness/cardio/training/talking-head totals only cover **analysed** assets and state how many remain unanalysed; never present a partial count as the whole library.

## Limits to state honestly
- Windows cloud-only detection relies on the placeholder attributes iCloud for Windows sets; if the iCloud client hides un-downloaded items entirely they cannot be counted, so verify totals against the iPhone.
- Exact duplicates use a sampled hash (head/middle/tail + size). Near-duplicates are cheap candidates (same duration/resolution/session) until visually confirmed. No perceptual hashing yet.
- Audio quality and stability are judgement calls from contact sheets unless Kye supplies more; score them only when evidenced, otherwise leave null.
- Embeddings are not used; semantic matching is taxonomy-driven. Extend `references/taxonomy.json` when a search misses obvious relatives.

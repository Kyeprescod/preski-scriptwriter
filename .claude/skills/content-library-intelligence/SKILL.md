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

`python3 .claude/skills/content-library-intelligence/scripts/clil.py --lib <dir> <command>` (stdlib only; ffprobe/ffmpeg make probing and contact sheets work).

| Command | Does |
|---|---|
| `init` | create library folder + SQLite DB (FTS5 search index) |
| `scan <folders...>` | incremental: new/changed files only (path+size+mtime), sampled hash, ffprobe metadata, session grouping, exact/near-dupe flags, moved-file tracking, missing-file flagging. Safe to re-run daily |
| `pending --limit N [--session S]` | JSON of probed-but-unanalysed assets with a contact-sheet image path each |
| `annotate <file.jsonl\|->` | upsert analysis (see below), updates search index |
| `search "<natural language>" [--limit --type --min-visual --same-session --json]` | ranked retrieval with semantic expansion (`references/taxonomy.json`) |
| `match-script <file\|->` | per-sentence ranked clips for a voiceover script (JSON) |
| `mark-used <project> <ids...>` | usage_count / last_used so footage can be rotated |
| `sessions`, `dupes`, `status`, `report` | inspection and the final report |

## Workflow

### 1. Index (cheap, automatic)
`init` once, then `scan` the camera-roll folder(s). Report counts (`new / changed / moved / unchanged / errors`). A rescan of 13,000 assets only hashes and probes what changed.

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
- Exact duplicates use a sampled hash (head/middle/tail + size). Near-duplicates are cheap candidates (same duration/resolution/session) until visually confirmed. No perceptual hashing yet.
- Audio quality and stability are judgement calls from contact sheets unless Kye supplies more; score them only when evidenced, otherwise leave null.
- Embeddings are not used; semantic matching is taxonomy-driven. Extend `references/taxonomy.json` when a search misses obvious relatives.

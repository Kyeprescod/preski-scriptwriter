# Preski Studio: one production record (audit + test evidence, 28 Oct 2026)

## Audit (what exists where)
- `business/clip-drop`, `business/daily-post`, Postiz, Poppy, Herk Edit Kit: NOT in this repo or this cloud machine. `C:\Users\kyber\PreskiStudio` is not reachable from the cloud session. Not audited; needs a local Claude Code session.
- Clip Drop = claude.ai artifact (`/artifact/32DMLtSwRrFiMd9QxTEPxP`) with `db` + `assets` capabilities. Collections: `clips`, `shotlist/current`. Clips are stored in the asset store (20 MB cap each).
- Editor + approval inbox = this repo (`editor.py`, `share_server.py`, laptop only; inbox reads `<phone root>/finished/*.mp4` + `.meta.json`).

## Shared source of truth
`jobs` collection in the Clip Drop artifact database (no new service, no cost). One document per video, id `job_YYYYMMDD_slug`.
Schema, states and prerequisites: `scripts/studio_jobs.py`. Every write is pinned with `if_version`, so two agents cannot overwrite each other.
Editor hand-off: `scripts/studio_bridge.py edit` (calls the existing `editor.py make`; no second engine).

## Evidence (test job `job_20261028_pushup-test`, test=true, never publishable)
- Shared DB read/write from the cloud session: PASS
- Stale write (version 1) refused, correct claim accepted: PASS
- Asset downloaded from the store, sha256 matches, ffmpeg decodes it (h264 720x1280): PASS
- Editor produced 1080x1920 H.264 MP4 (5.5 s), captions/hook/CTA visible: PASS (Linux cloud run)
- Approval inbox lists it as pending: PASS (share_server.load_items)
- Postiz package validated offline, nothing sent: PASS (`postiz_status=package_valid_unsent`)
- Failure path records `FAILED` + reason in the patch: PASS (first run)
NOT TESTED: Poppy's own read/write, laptop reading the DB, a real push-up upload from the phone, Postiz API, analytics.
The clip used is a Claude-made stand-in (weighted-vest talk, not a push-up).

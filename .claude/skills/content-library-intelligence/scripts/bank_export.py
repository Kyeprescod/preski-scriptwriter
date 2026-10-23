#!/usr/bin/env python3
"""Export your best tagged footage as a clip/photo BANK for the cloud Daily Post (no originals touched).

    bank_export.py --lib LIB --out DIR [--max-clips 40] [--max-photos 40] [--min-score 6.5] [--secs 5]
                   [--allow-landscape] [--travel] [--since 2025-01-01]

Writes, into DIR:
  clips/<name>.mp4   short (<= --secs), silent, 1080x1920, H.264, all metadata stripped (no GPS, no device info)
  photos/<name>.jpg  long side <= 2400 px, JPEG q92, EXIF/GPS stripped
  clips.json, photos.json    in the same shape the Daily Post renderer reads (file, date, secs/size, what/desc, tags ...)
  bank_manifest.json  which library asset each file came from + why it was chosen
Only clips that are tagged ("analysed"), on this PC (not cloud-only), not duplicates and above the score threshold are
used. Cloud-only winners are listed so you can `fetch` them first. Travel footage is left out unless --travel.
Then ask Claude (Local session): "publish the bank in <DIR> to the Daily Post artifact".
"""
import argparse, json, os, re, sqlite3, subprocess, sys
from pathlib import Path


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib"); ap.add_argument("--out", required=True)
    ap.add_argument("--max-clips", type=int, default=40); ap.add_argument("--max-photos", type=int, default=40)
    ap.add_argument("--min-score", type=float, default=6.5); ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--allow-landscape", action="store_true"); ap.add_argument("--travel", action="store_true")
    ap.add_argument("--since")
    a = ap.parse_args()
    lib = Path(a.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library")
    con = sqlite3.connect(lib / "library.db")
    con.row_factory = sqlite3.Row
    out = Path(a.out)
    (out / "clips").mkdir(parents=True, exist_ok=True)
    (out / "photos").mkdir(exist_ok=True)

    def tags(aid):
        return [r[0] for r in con.execute("SELECT tag FROM tags WHERE asset_id=?", (aid,))]

    where = ("status='analysed' AND COALESCE(availability,'local')='local' AND COALESCE(duplicate_status,'') NOT IN ('exact_duplicate','near_duplicate') "
             "AND COALESCE(visual_quality_score,0)>=? AND COALESCE(content_potential_score,0)>=?")
    params = [a.min_score, a.min_score]
    if a.since:
        where += " AND date_created>=?"
        params.append(a.since)
    rows = con.execute(f"SELECT * FROM assets WHERE {where} ORDER BY (COALESCE(visual_quality_score,0)+COALESCE(content_potential_score,0)+"
                       f"CASE WHEN LOWER(COALESCE(description,'')||' '||COALESCE((SELECT group_concat(tag,' ') FROM tags t WHERE t.asset_id=assets.asset_id),'')) "
                       f"LIKE '%showcase%' THEN 3 ELSE 0 END) DESC", params).fetchall()
    skipped = {"travel": 0, "landscape": 0, "talking": 0, "missing": 0, "exists": 0}
    clips, photos, manifest, used_names = [], [], [], set()
    for r in rows:
        t = tags(r["asset_id"])
        if not a.travel and ({"travel", "travel-page-only"} & set(t) or (r["category"] or "") == "travel"):
            skipped["travel"] += 1
            continue
        src = Path(r["file_path"])
        if not src.exists():
            skipped["missing"] += 1
            continue
        date = (r["date_created"] or "")[:10]
        label = slug(r["exercise"] or r["activity"] or r["subcategory"] or r["category"] or "clip")
        base = f"{slug(r['category'] or 'clip')}-{label}-{date}".strip("-")
        if r["media_type"] == "video" and len(clips) < a.max_clips:
            if (r["orientation"] or "") != "portrait" and not a.allow_landscape:
                skipped["landscape"] += 1
                continue
            letter = "a"
            while f"{base}-{letter}" in used_names:
                letter = chr(ord(letter) + 1)
            name = f"{base}-{letter}"
            used_names.add(name)
            dur = float(r["duration"] or a.secs)
            secs = min(a.secs, dur)
            start = 0.0 if dur <= a.secs + 0.5 else max(0.3, min(dur - secs - 0.2, dur * 0.3))
            dst = out / "clips" / (name + ".mp4")
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{secs:.2f}", "-i", str(src),
                   "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                   "-an", "-map_metadata", "-1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "medium",
                   "-movflags", "+faststart", str(dst)]
            try:
                run(cmd)
            except RuntimeError as e:
                print("skip", src.name, "->", e)
                continue
            th = bool(r["talking_head"])
            clips.append({"file": name + ".mp4", "date": date, "secs": round(secs, 1), "what": r["description"] or label,
                          "tags": t, "voiceover_ok": not th, "quality": r["visual_quality_score"], "potential": r["content_potential_score"]})
            manifest.append({"file": "clips/" + name + ".mp4", "asset_id": r["asset_id"], "source": str(src), "start": round(start, 2),
                             "scores": [r["visual_quality_score"], r["content_potential_score"]]})
        elif r["media_type"] == "image" and len(photos) < a.max_photos:
            from PIL import Image, ImageOps
            name = f"{base}-{r['asset_id']}"
            try:
                im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            except Exception as e:  # noqa: BLE001
                print("skip", src.name, "->", e)
                continue
            if max(im.size) > 2400:
                im.thumbnail((2400, 2400), Image.LANCZOS)
            dst = out / "photos" / (name + ".jpg")
            im.save(dst, quality=92, subsampling=0)  # no exif argument: metadata (GPS, device) is not carried over
            photos.append({"file": name + ".jpg", "date": date, "desc": r["description"] or label, "tags": t, "size": list(im.size)})
            manifest.append({"file": "photos/" + name + ".jpg", "asset_id": r["asset_id"], "source": str(src),
                             "scores": [r["visual_quality_score"], r["content_potential_score"]]})
    cloud = con.execute("SELECT COUNT(*) FROM assets WHERE status='analysed' AND availability='cloud_only' AND COALESCE(visual_quality_score,0)>=? AND COALESCE(content_potential_score,0)>=?",
                        (a.min_score, a.min_score)).fetchone()[0]
    (out / "clips.json").write_text(json.dumps(clips, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "photos.json").write_text(json.dumps(photos, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "bank_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Bank written to %s: %d clips, %d photos" % (out, len(clips), len(photos)))
    print("Left out: " + ", ".join("%d %s" % (v, k) for k, v in skipped.items() if v) if any(skipped.values()) else "Nothing left out for other reasons.")
    if cloud:
        print("%d more high-scoring clips/photos are cloud-only: use `fetch` on them, then run this again." % cloud)
    print("Next: ask Claude (Local session): publish the bank in %s to the Daily Post artifact." % out)


if __name__ == "__main__":
    main()

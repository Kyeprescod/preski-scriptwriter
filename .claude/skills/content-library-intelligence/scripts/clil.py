#!/usr/bin/env python3
"""Content Library Intelligence (clil): searchable metadata index over a raw footage archive.

Standard library only. Needs ffprobe/ffmpeg on PATH for probing and contact sheets (optional).

NON-DESTRUCTIVE: source folders are only ever READ. Everything generated (database, contact
sheets, transcripts) lives in the library folder (--lib / $CLIL_LIB / ~/preski-library).

Commands: init scan pending annotate sessions search match-script mark-used dupes report status
"""
import argparse, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tiff", ".dng"}
SESSION_GAP_S = 45 * 60
HERE = Path(__file__).resolve().parent
TAXONOMY = json.loads((HERE.parent / "references" / "taxonomy.json").read_text())

TEXT_FIELDS = ["category", "subcategory", "exercise", "activity", "environment", "subject",
               "description", "transcript", "shot_type"]
SCORE_FIELDS = ["visual_quality_score", "content_potential_score", "hook_potential_score",
                "audio_quality_score", "stability_score"]
ANNOTATABLE = set(TEXT_FIELDS + SCORE_FIELDS + [
    "talking_head", "duplicate_status", "duplicate_of", "available_for_repurpose", "session_id",
    "location", "transcript_path", "extra"])
# FTS column -> weight when scoring a match
FTS_WEIGHTS = {"exercise": 5, "activity": 4, "tags": 4, "category": 3, "subcategory": 3,
               "subject": 3, "description": 2, "transcript": 1.5, "environment": 1, "file_name": 0.5}
STOP = set("""find me my of the a an for to in on with and or is are i you your clips clip footage video
videos best strongest show showing shows that this those these doing where any all some about suitable
support supports look looks looking like get give need want under over from at as be it its when how why
would could should can will make made use using explain explaining explains work works""".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
  asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path TEXT UNIQUE NOT NULL, file_name TEXT, media_type TEXT,
  size INTEGER, mtime REAL, quick_hash TEXT,
  duration REAL, width INTEGER, height INTEGER, resolution TEXT, aspect_ratio TEXT,
  orientation TEXT, fps REAL, has_audio INTEGER, codec TEXT,
  date_created TEXT, date_modified TEXT, location TEXT,
  category TEXT, subcategory TEXT, exercise TEXT, activity TEXT, environment TEXT,
  subject TEXT, description TEXT, shot_type TEXT, transcript TEXT, transcript_path TEXT,
  talking_head INTEGER DEFAULT 0,
  visual_quality_score REAL, content_potential_score REAL, hook_potential_score REAL,
  audio_quality_score REAL, stability_score REAL,
  session_id TEXT, duplicate_status TEXT, duplicate_of INTEGER,
  usage_count INTEGER DEFAULT 0, last_used TEXT, available_for_repurpose INTEGER DEFAULT 1,
  status TEXT DEFAULT 'new',          -- new | probed | analysed | missing | error
  error TEXT, extra TEXT, indexed_at TEXT, analysed_at TEXT
);
CREATE TABLE IF NOT EXISTS tags (asset_id INTEGER, tag TEXT, PRIMARY KEY (asset_id, tag));
CREATE TABLE IF NOT EXISTS usage (asset_id INTEGER, project TEXT, used_at TEXT);
CREATE INDEX IF NOT EXISTS ix_status ON assets(status);
CREATE INDEX IF NOT EXISTS ix_hash ON assets(quick_hash);
CREATE INDEX IF NOT EXISTS ix_session ON assets(session_id);
CREATE INDEX IF NOT EXISTS ix_tag ON tags(tag);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  exercise, activity, tags, category, subcategory, subject, description, transcript,
  environment, file_name, tokenize='porter unicode61');
"""


# ---------------------------------------------------------------- helpers
def lib_dir(args):
    return Path(args.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library").expanduser()


def connect(args, create=False):
    lib = lib_dir(args)
    db = lib / "library.db"
    if not db.exists() and not create:
        sys.exit(f"No library at {lib}. Run: clil.py init --lib {lib}")
    lib.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def quick_hash(path, size):
    """Sampled hash (head/middle/tail 1MB + size): fast on huge videos, exact-dup grade in practice."""
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        for off in (0, max(0, size // 2 - 524288), max(0, size - 1048576)):
            f.seek(off)
            h.update(f.read(1048576))
    return h.hexdigest()


def ffprobe(path):
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                              "-show_streams", str(path)], capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except Exception:
        return None


def probe_fields(path, media_type):
    """Technical metadata only. Anything undeterminable stays NULL (never invented)."""
    info = ffprobe(path)
    if not info:
        return {}
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    fields = {"has_audio": int(any(s.get("codec_type") == "audio" for s in info["streams"]))}
    if v:
        w, h = v.get("width"), v.get("height")
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            rot = int(sd.get("rotation", 0) or 0)
        rot = int(v.get("tags", {}).get("rotate", rot) or rot)
        if abs(rot) in (90, 270) and w and h:
            w, h = h, w
        if w and h:
            from math import gcd
            g = gcd(w, h)
            fields.update(width=w, height=h, resolution=f"{w}x{h}", aspect_ratio=f"{w // g}:{h // g}",
                          orientation="portrait" if h > w else "landscape" if w > h else "square")
        fields["codec"] = v.get("codec_name")
        if media_type == "video":
            try:
                n, d = v.get("avg_frame_rate", "0/1").split("/")
                fields["fps"] = round(float(n) / float(d), 2) if float(d) else None
            except Exception:
                pass
    dur = info.get("format", {}).get("duration")
    if dur and media_type == "video":
        fields["duration"] = round(float(dur), 2)
    tags = {k.lower(): val for k, val in info.get("format", {}).get("tags", {}).items()}
    if tags.get("creation_time"):
        fields["date_created"] = tags["creation_time"]
    if tags.get("location"):
        fields["location"] = tags["location"]
    return fields


def sync_fts(con, asset_id):
    r = con.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    tags = " ".join(t[0] for t in con.execute("SELECT tag FROM tags WHERE asset_id=?", (asset_id,)))
    con.execute("DELETE FROM fts WHERE rowid=?", (asset_id,))
    con.execute("INSERT INTO fts(rowid,exercise,activity,tags,category,subcategory,subject,description,"
                "transcript,environment,file_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, r["exercise"], r["activity"], tags, r["category"], r["subcategory"],
                 r["subject"], r["description"], r["transcript"], r["environment"], r["file_name"]))


# ---------------------------------------------------------------- commands
def cmd_init(a):
    con = connect(a, create=True)
    (lib_dir(a) / "contact_sheets").mkdir(exist_ok=True)
    (lib_dir(a) / "transcripts").mkdir(exist_ok=True)
    print(f"Library ready at {lib_dir(a)}")
    con.close()


def cmd_scan(a):
    """Incremental: only new/changed files are hashed and probed. Rows are never deleted."""
    con = connect(a, create=True)
    known = {r["file_path"]: r for r in con.execute("SELECT * FROM assets")}
    seen, stats = set(), dict(scanned=0, new=0, changed=0, moved=0, unchanged=0, errors=0)
    t0 = time.time()
    for src in a.sources:
        for root, _, files in os.walk(Path(src).expanduser()):
            for fn in files:
                ext = Path(fn).suffix.lower()
                if ext not in VIDEO_EXT | IMAGE_EXT or fn.startswith("."):
                    continue
                p = os.path.abspath(os.path.join(root, fn))
                seen.add(p)
                stats["scanned"] += 1
                try:
                    st = os.stat(p)
                    old = known.get(p)
                    if old and old["size"] == st.st_size and abs((old["mtime"] or 0) - st.st_mtime) < 1:
                        if old["status"] == "missing":
                            con.execute("UPDATE assets SET status='probed' WHERE asset_id=?", (old["asset_id"],))
                        stats["unchanged"] += 1
                        continue
                    mt = "video" if ext in VIDEO_EXT else "image"
                    qh = quick_hash(p, st.st_size)
                    fields = dict(file_name=fn, media_type=mt, size=st.st_size, mtime=st.st_mtime,
                                  quick_hash=qh, date_modified=iso(st.st_mtime), indexed_at=now(),
                                  date_created=iso(getattr(st, "st_birthtime", st.st_mtime)))
                    fields.update(probe_fields(p, mt))
                    if old:   # file changed in place: keep id, drop stale analysis flag
                        fields["status"] = "probed"
                        sets = ",".join(f"{k}=?" for k in fields)
                        con.execute(f"UPDATE assets SET {sets} WHERE asset_id=?", (*fields.values(), old["asset_id"]))
                        stats["changed"] += 1
                        continue
                    moved = con.execute("SELECT asset_id,file_path FROM assets WHERE quick_hash=? AND size=?",
                                        (qh, st.st_size)).fetchall()
                    gone = [m for m in moved if not os.path.exists(m["file_path"])]
                    if gone:  # same file at a new path: keep its analysis
                        con.execute("UPDATE assets SET file_path=?,file_name=?,status=CASE WHEN analysed_at "
                                    "IS NULL THEN 'probed' ELSE 'analysed' END WHERE asset_id=?",
                                    (p, fn, gone[0]["asset_id"]))
                        stats["moved"] += 1
                        sync_fts(con, gone[0]["asset_id"])
                        continue
                    fields.update(file_path=p, status="probed")
                    cols = ",".join(fields)
                    cur = con.execute(f"INSERT INTO assets({cols}) VALUES ({','.join('?' * len(fields))})",
                                      tuple(fields.values()))
                    if moved:  # identical bytes already indexed at a live path
                        con.execute("UPDATE assets SET duplicate_status='exact_duplicate', duplicate_of=? "
                                    "WHERE asset_id=?", (moved[0]["asset_id"], cur.lastrowid))
                    stats["new"] += 1
                    sync_fts(con, cur.lastrowid)
                except Exception as e:
                    stats["errors"] += 1
                    con.execute("INSERT INTO assets(file_path,file_name,status,error,indexed_at) VALUES(?,?,?,?,?) "
                                "ON CONFLICT(file_path) DO UPDATE SET status='error',error=excluded.error",
                                (p, fn, "error", str(e), now()))
    # Flag (never delete) rows whose files vanished from the scanned roots.
    roots = tuple(os.path.abspath(str(Path(s).expanduser())) for s in a.sources)
    missing = 0
    for p, r in known.items():
        cur = con.execute("SELECT file_path FROM assets WHERE asset_id=?", (r["asset_id"],)).fetchone()
        if cur["file_path"] == p and p.startswith(roots) and p not in seen and r["status"] != "missing":
            con.execute("UPDATE assets SET status='missing' WHERE asset_id=?", (r["asset_id"],))
            missing += 1
    con.commit()
    assign_sessions(con)
    mark_near_duplicates(con)
    con.commit()
    print(json.dumps({**stats, "missing_flagged": missing, "seconds": round(time.time() - t0, 1)}))


def mark_near_duplicates(con):
    """Cheap candidates only (same duration +-0.3s, resolution, within a session). Needs visual confirmation
    to promote to similar_shot / different_take / different_angle - never auto-deleted either way."""
    rows = con.execute("SELECT asset_id,duration,resolution,session_id FROM assets WHERE media_type='video' "
                       "AND duration IS NOT NULL AND status NOT IN ('missing','error') AND duplicate_status IS NULL "
                       "ORDER BY resolution,duration").fetchall()
    for i, r in enumerate(rows):
        for q in rows[i + 1:i + 6]:
            if q["resolution"] == r["resolution"] and abs(q["duration"] - r["duration"]) <= 0.3 \
                    and r["session_id"] and r["session_id"] == q["session_id"]:
                con.execute("UPDATE assets SET duplicate_status='near_duplicate', duplicate_of=? "
                            "WHERE asset_id=? AND duplicate_status IS NULL", (r["asset_id"], q["asset_id"]))


def assign_sessions(con):
    """Group clips shot within 45 min of each other into one session (workout/event)."""
    rows = con.execute("SELECT asset_id,date_created,session_id FROM assets WHERE date_created IS NOT NULL "
                       "AND status NOT IN ('error') ORDER BY date_created").fetchall()
    prev, sid, n = None, None, 0
    for r in rows:
        try:
            t = datetime.fromisoformat(r["date_created"].replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if prev is None or t - prev > SESSION_GAP_S:
            n += 1
            sid = f"S{r['date_created'][:10].replace('-', '')}-{n:05d}"
        prev = t
        if r["session_id"] != sid:
            con.execute("UPDATE assets SET session_id=? WHERE asset_id=?", (sid, r["asset_id"]))


def contact_sheet(lib, r):
    out = lib / "contact_sheets" / f"{r['asset_id']}.jpg"
    if out.exists() or not shutil.which("ffmpeg"):
        return str(out) if out.exists() else None
    if r["media_type"] == "video":
        d = max(r["duration"] or 1, 1)
        vf = f"fps=4/{d},scale=360:-2,tile=4x1:padding=2"
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", r["file_path"], "-vf", vf, "-frames:v", "1", str(out)]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", r["file_path"], "-vf", "scale=720:-2", "-frames:v", "1", str(out)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:
        return None
    return str(out) if out.exists() else None


def cmd_pending(a):
    """Assets still needing visual analysis, with a contact-sheet image for Claude to look at."""
    con = connect(a)
    q = ("SELECT * FROM assets WHERE status='probed' AND NOT (duplicate_status='exact_duplicate' AND "
         "duplicate_of IN (SELECT asset_id FROM assets WHERE status!='missing'))")
    if a.session:
        q += " AND session_id=" + repr(a.session)
    rows = con.execute(q + " ORDER BY date_created DESC LIMIT ?", (a.limit,)).fetchall()
    out = []
    for r in rows:
        out.append({"asset_id": r["asset_id"], "file_name": r["file_name"], "media_type": r["media_type"],
                    "duration": r["duration"], "orientation": r["orientation"], "has_audio": r["has_audio"],
                    "date_created": r["date_created"], "session_id": r["session_id"],
                    "contact_sheet": contact_sheet(lib_dir(a), r)})
    print(json.dumps(out, indent=1))


def cmd_annotate(a):
    """Upsert analysis from JSONL: {asset_id|file_path, <fields>, tags:[...]}. Only evidenced fields."""
    con = connect(a)
    n = bad = 0
    for line in (sys.stdin if a.file == "-" else open(a.file)):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        aid = d.get("asset_id")
        if aid is None and d.get("file_path"):
            r = con.execute("SELECT asset_id FROM assets WHERE file_path=?", (d["file_path"],)).fetchone()
            aid = r and r["asset_id"]
        if aid is None or not con.execute("SELECT 1 FROM assets WHERE asset_id=?", (aid,)).fetchone():
            bad += 1
            continue
        f = {k: v for k, v in d.items() if k in ANNOTATABLE}
        for k in SCORE_FIELDS:
            if f.get(k) is not None:
                f[k] = max(1.0, min(10.0, float(f[k])))
        if "extra" in f and not isinstance(f["extra"], str):
            f["extra"] = json.dumps(f["extra"])
        f.update(status="analysed", analysed_at=now())
        con.execute(f"UPDATE assets SET {','.join(k + '=?' for k in f)} WHERE asset_id=?", (*f.values(), aid))
        if d.get("tags"):
            for t in d["tags"]:
                con.execute("INSERT OR IGNORE INTO tags VALUES (?,?)", (aid, t.strip().lower()))
        sync_fts(con, aid)
        n += 1
    con.commit()
    print(json.dumps({"annotated": n, "rejected_unknown_asset": bad}))


def cmd_sessions(a):
    con = connect(a)
    assign_sessions(con)
    con.commit()
    for r in con.execute("SELECT session_id,COUNT(*) c,MIN(date_created) t FROM assets WHERE session_id IS NOT NULL "
                         "GROUP BY session_id ORDER BY t DESC LIMIT ?", (a.limit,)):
        print(f"{r['session_id']}  {r['c']:>4} clips  {r['t']}")


# ---------------------------------------------------------------- search
def stem(w):
    return re.sub(r"(ing|es|s)$", "", w) if len(w) > 5 else w.rstrip("s") if len(w) > 3 else w


def expand_query(q):
    """-> (literal_terms, expanded_terms). Phrases from the taxonomy are matched as a whole first."""
    ql = q.lower().replace("’", "'")
    concepts = TAXONOMY["concepts"]
    literal, expanded = [], {}
    names = set(concepts) | set(TAXONOMY["exercise_to_muscle"]) | {v for c in concepts.values() for v in c}
    for ph in sorted(names, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(ph)}(?![\w-])", ql):
            literal.append(ph)
            ql = re.sub(rf"(?<![\w-]){re.escape(ph)}(?![\w-])", " ", ql)
    literal += [w for w in re.findall(r"[a-z0-9'-]+", ql) if w not in STOP and len(w) > 2]
    for t in literal:
        for rel in concepts.get(t, []):
            expanded.setdefault(rel, 0.4)
        m = TAXONOMY["exercise_to_muscle"].get(t)
        if m:
            expanded.setdefault(m, 0.5)
    for t in literal:
        expanded.pop(t, None)
    return list(dict.fromkeys(literal)), expanded


def fts_query(terms):
    parts = []
    for t in terms:
        t = re.sub(r"[^\w' -]", "", t).replace("'", "")
        if t:
            parts.append(f'"{t}"')
    return " OR ".join(parts)


def run_search(con, query, limit=10, media=None, min_visual=None, include_dupes=False, want_talking=None):
    lit, exp = expand_query(query)
    if not lit:
        return []
    q = fts_query(lit + list(exp))
    cand = con.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 3000", (q,)).fetchall()
    talking_intent = want_talking if want_talking is not None else any(
        t in ("talking head", "talking to camera", "speaking", "selfie") for t in lit)
    results = []
    for (rid,) in cand:
        r = con.execute("SELECT * FROM assets WHERE asset_id=?", (rid,)).fetchone()
        if r["status"] != "analysed" or r["available_for_repurpose"] == 0:
            continue
        if (media and r["media_type"] != media) or (min_visual and (r["visual_quality_score"] or 0) < min_visual):
            continue
        if not include_dupes and r["duplicate_status"] == "exact_duplicate" and con.execute(
                "SELECT 1 FROM assets WHERE asset_id=? AND status='analysed'", (r["duplicate_of"],)).fetchone():
            continue   # the analysed original represents this group
        tags = " ".join(t[0] for t in con.execute("SELECT tag FROM tags WHERE asset_id=?", (rid,)))
        cols = {c: (tags if c == "tags" else (r[c] or "")).lower() for c in FTS_WEIGHTS}
        got, why, rel = 0.0, [], 0.0
        for term, w in [(t, 1.0) for t in lit] + list(exp.items()):
            s = stem(term)
            best = max(((FTS_WEIGHTS[c] * w, c) for c in cols if s in cols[c]), default=(0, None))
            if best[0]:
                got += best[0]
                why.append(f"{term}→{best[1]}" if w < 1 else f"{term}@{best[1]}")
                rel += 1 if w == 1 else 0
        if not got:
            continue
        coverage = rel / len(lit)                       # share of literal asks satisfied
        relevance = min(1.0, got / (5.0 * len(lit)))    # strength of match
        pot = (r["content_potential_score"] or 5) / 10
        vis = (r["visual_quality_score"] or 5) / 10
        score = 0.40 * relevance + 0.20 * coverage + 0.25 * pot + 0.15 * vis
        if talking_intent:
            score = score * 0.6 + 0.4 * (1.0 if r["talking_head"] else 0.0) if not r["talking_head"] else score + 0.05
        results.append((round(min(score, 1.0) * 10, 1), r, why[:6]))
    results.sort(key=lambda x: (-x[0], -(x[1]["content_potential_score"] or 0)))
    return results[:limit]


def fmt_hit(i, s, r, why):
    d = f"{r['duration']:.0f}s" if r["duration"] else r["media_type"]
    return (f"{i}. Clip {r['asset_id']} — {s}/10  [{d}, {r['orientation'] or '?'}]  "
            f"{(r['description'] or r['activity'] or r['file_name'])[:90]}\n"
            f"   {r['file_path']}\n   why: {', '.join(why)} | visual {r['visual_quality_score']} "
            f"potential {r['content_potential_score']} | session {r['session_id']}")


def cmd_search(a):
    con = connect(a)
    res = run_search(con, a.query, a.limit, a.type, a.min_visual, a.include_dupes)
    if a.json:
        print(json.dumps([{"asset_id": r["asset_id"], "score": s, "file_path": r["file_path"],
                           "session_id": r["session_id"], "description": r["description"], "why": w,
                           "duration": r["duration"]} for s, r, w in res], indent=1))
        return
    if not res:
        n = con.execute("SELECT COUNT(*) FROM assets WHERE status='probed'").fetchone()[0]
        print(f"No analysed footage matched. ({n} assets are indexed but not yet analysed.)")
    for i, (s, r, w) in enumerate(res, 1):
        print(fmt_hit(i, s, r, w))
    if a.same_session and res:
        sid = res[0][1]["session_id"]
        print(f"\nOther clips in session {sid}:")
        for r in con.execute("SELECT asset_id,description,exercise,duration FROM assets WHERE session_id=? "
                             "AND asset_id!=? ORDER BY date_created", (sid, res[0][1]["asset_id"])):
            print(f"   Clip {r['asset_id']}: {r['exercise'] or ''} {r['description'] or ''} ({r['duration']}s)")


def cmd_match_script(a):
    """Each non-empty line of the script file -> top clips that visually support that line."""
    con = connect(a)
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text()
    lines = [l.strip() for l in re.split(r"(?<=[.!?])\s+|\n+", text) if l.strip()]
    out = []
    for i, line in enumerate(lines, 1):
        hits = run_search(con, line, a.per)
        out.append({"line": i, "text": line, "clips": [
            {"asset_id": r["asset_id"], "score": s, "file_path": r["file_path"], "why": w,
             "session_id": r["session_id"]} for s, r, w in hits]})
    print(json.dumps(out, indent=1))


def cmd_mark_used(a):
    con = connect(a)
    for aid in a.ids:
        con.execute("UPDATE assets SET usage_count=usage_count+1,last_used=? WHERE asset_id=?", (now(), aid))
        con.execute("INSERT INTO usage VALUES (?,?,?)", (aid, a.project, now()))
    con.commit()
    print(f"Marked {len(a.ids)} clips used in '{a.project}'")


def cmd_dupes(a):
    con = connect(a)
    for r in con.execute("SELECT a.asset_id,a.file_path,a.duplicate_status,a.duplicate_of,b.file_path orig "
                         "FROM assets a LEFT JOIN assets b ON b.asset_id=a.duplicate_of "
                         "WHERE a.duplicate_status IS NOT NULL ORDER BY a.duplicate_status,a.asset_id"):
        print(f"{r['duplicate_status']:<18} {r['asset_id']} ← {r['duplicate_of']}\n   {r['file_path']}\n   {r['orig']}")
    print("\nNothing has been deleted or moved. Review and approve any removal yourself.")


def cmd_status(a):
    con = connect(a)
    for r in con.execute("SELECT status,COUNT(*) c FROM assets GROUP BY status"):
        print(f"{r['status']:<10} {r['c']}")


def cmd_report(a):
    con = connect(a)
    one = lambda q: con.execute(q).fetchone()[0]
    live = "status NOT IN ('missing','error')"
    fit = "status='analysed' AND category IS NOT NULL AND category NOT IN ('other','lifestyle','b-roll')"
    print("CONTENT LIBRARY INTELLIGENCE REPORT")
    print(f"TOTAL ASSETS SCANNED:        {one(f'SELECT COUNT(*) FROM assets WHERE {live}')}")
    print(f"TOTAL VIDEO ASSETS:          {one(f'SELECT COUNT(*) FROM assets WHERE media_type=\"video\" AND {live}')}")
    print(f"TOTAL IMAGE ASSETS:          {one(f'SELECT COUNT(*) FROM assets WHERE media_type=\"image\" AND {live}')}")
    print(f"TOTAL FITNESS ASSETS:        {one(f'SELECT COUNT(*) FROM assets WHERE {fit}')}")
    print(f"TOTAL TALKING-HEAD ASSETS:   {one('SELECT COUNT(*) FROM assets WHERE talking_head=1')}")
    print(f"TOTAL CARDIO ASSETS:         {one('SELECT COUNT(*) FROM assets WHERE status=\"analysed\" AND (category=\"cardio\" OR asset_id IN (SELECT asset_id FROM tags WHERE tag=\"cardio\"))')}")
    print(f"TOTAL TRAINING ASSETS:       {one('SELECT COUNT(*) FROM assets WHERE status=\"analysed\" AND category=\"training\"')}")
    print(f"TOTAL HIGH-POTENTIAL (>=8):  {one('SELECT COUNT(*) FROM assets WHERE content_potential_score>=8')}")
    print(f"DUPLICATES / NEAR-DUPLICATES:{one('SELECT COUNT(*) FROM assets WHERE duplicate_status IS NOT NULL'):>4}")
    print("\nTOP CONTENT CATEGORIES")
    for r in con.execute("SELECT category,COUNT(*) c FROM assets WHERE category IS NOT NULL GROUP BY category ORDER BY c DESC LIMIT 8"):
        print(f"  {r['category']:<14} {r['c']}")
    print("\nTOP HIGH-POTENTIAL FOOTAGE")
    for r in con.execute("SELECT asset_id,description,exercise,content_potential_score p,visual_quality_score v FROM assets "
                         "WHERE content_potential_score IS NOT NULL ORDER BY p DESC,v DESC LIMIT 10"):
        print(f"  Clip {r['asset_id']} — potential {r['p']} / visual {r['v']} — {r['exercise'] or ''} {r['description'] or ''}"[:140])
    st = {r["status"]: r["c"] for r in con.execute("SELECT status,COUNT(*) c FROM assets GROUP BY status")}
    print("\nINDEX STATUS")
    print(f"  analysed {st.get('analysed', 0)} | awaiting analysis {st.get('probed', 0)} | "
          f"missing from disk {st.get('missing', 0)} | errors {st.get('error', 0)}")
    for r in con.execute("SELECT file_path,error FROM assets WHERE status='error' LIMIT 20"):
        print(f"  ERROR {r['file_path']}: {r['error']}")
    nm = one("SELECT COUNT(*) FROM assets WHERE status NOT IN ('error') AND media_type='video' AND duration IS NULL")
    if nm:
        print(f"  {nm} videos have no technical metadata (ffprobe missing or unreadable)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lib", help="library folder (default $CLIL_LIB or ~/preski-library)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("scan"); s.add_argument("sources", nargs="+"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("pending"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--session"); s.set_defaults(fn=cmd_pending)
    s = sub.add_parser("annotate"); s.add_argument("file", help="JSONL file or - for stdin"); s.set_defaults(fn=cmd_annotate)
    s = sub.add_parser("sessions"); s.add_argument("--limit", type=int, default=20); s.set_defaults(fn=cmd_sessions)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=10)
    s.add_argument("--type", choices=["video", "image"]); s.add_argument("--min-visual", type=float)
    s.add_argument("--include-dupes", action="store_true"); s.add_argument("--same-session", action="store_true")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("match-script"); s.add_argument("file", help="script text file or -")
    s.add_argument("--per", type=int, default=5); s.set_defaults(fn=cmd_match_script)
    s = sub.add_parser("mark-used"); s.add_argument("project"); s.add_argument("ids", nargs="+", type=int)
    s.set_defaults(fn=cmd_mark_used)
    sub.add_parser("dupes").set_defaults(fn=cmd_dupes)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

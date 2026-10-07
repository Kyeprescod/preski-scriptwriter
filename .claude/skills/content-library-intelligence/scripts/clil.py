#!/usr/bin/env python3
"""Content Library Intelligence (clil): searchable metadata index over a raw footage archive.

Built for Windows + iCloud Photos (also runs on Linux/macOS). Needs:
  - Python 3.9+
  - Pillow + pillow-heif   (images incl. HEIC: metadata, EXIF capture date, thumbnails)
  - ffmpeg + ffprobe       (videos: metadata, frame extraction)
Run `doctor` to check, `detect` to find your library, `scan --test` before the full scan.

NON-DESTRUCTIVE: source folders are only ever READ. Cloud-only placeholders are detected from file
attributes and never opened (opening one would make iCloud download it). Everything generated lives
in the library folder (--lib / $CLIL_LIB / ~/preski-library).

Commands: doctor detect folders init scan fetch download free pending annotate sessions search match-script mark-used dupes report status
"""
import argparse, hashlib, json, os, random, re, shutil, sqlite3, subprocess, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr, sys.stdin):        # Windows consoles default to cp1252
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tiff", ".tif", ".dng", ".bmp"}
MEDIA_EXT = VIDEO_EXT | IMAGE_EXT
SESSION_GAP_S = 45 * 60
LIVE_PHOTO_MAX_S = 4.5
SKIP_DIRS = {"thumbnails", ".thumbnails", "@eadir", "$recycle.bin", "system volume information",
             ".git", "node_modules", "temp", "tmp", "cache", "caches"}   # editor/app junk, never footage
HERE = Path(__file__).resolve().parent
TAXONOMY = json.loads((HERE.parent / "references" / "taxonomy.json").read_text(encoding="utf-8"))

# Windows cloud-file placeholder attributes (iCloud Photos / iCloud Drive / OneDrive use these)
ATTR_OFFLINE = 0x1000
ATTR_RECALL_ON_OPEN = 0x40000
ATTR_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ATTRS = ATTR_OFFLINE | ATTR_RECALL_ON_OPEN | ATTR_RECALL_ON_DATA_ACCESS

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

NEW_COLS = {"availability": "TEXT DEFAULT 'local'",   # local | cloud_only
            "date_source": "TEXT",                    # exif | quicktime | container | file_time
            "thumb_path": "TEXT"}


# ---------------------------------------------------------------- helpers
def base_dir(args):
    return Path(args.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library").expanduser()


def lib_dir(args):
    """Test mode writes to its own sub-library so the real index starts clean."""
    b = base_dir(args)
    return b / "_test" if getattr(args, "test", False) else b


def connect(args, create=False):
    lib = lib_dir(args)
    db = lib / "library.db"
    if not db.exists() and not create:
        sys.exit(f"No library at {lib}. Run: clil init")
    lib.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(assets)")}
    for c, t in NEW_COLS.items():
        if c not in have:
            con.execute(f"ALTER TABLE assets ADD COLUMN {c} {t}")
    return con


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def parse_dt(s):
    """Parse EXIF ('2026:10:01 18:22:11'), ISO, 'Z' and '+0100' style stamps. None if unparseable."""
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    s = re.sub(r"^(\d{4}):(\d\d):(\d\d)", r"\1-\2-\3", s)
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    try:
        return datetime.fromisoformat(s.replace(" ", "T", 1))
    except ValueError:
        return None


def valid_date(s):
    d = parse_dt(s)
    return d is not None and 1995 <= d.year <= datetime.now().year + 1   # rejects 1904/1970 epoch zeros


def is_cloud_only(st):
    """True if the file is a cloud placeholder (bytes not on this PC). Windows only; uses stat metadata
    that does NOT trigger a download."""
    return bool(getattr(st, "st_file_attributes", 0) & CLOUD_ATTRS)


def quick_hash(path, size):
    """Sampled hash (head/middle/tail 1MB + size): fast on huge videos, exact-dup grade in practice."""
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        for off in (0, max(0, size // 2 - 524288), max(0, size - 1048576)):
            f.seek(off)
            h.update(f.read(1048576))
    return h.hexdigest()


# ---- images: Pillow (+ pillow-heif for HEIC). ffmpeg is NOT relied on for HEIC.
_PIL = None


def pil():
    global _PIL
    if _PIL is None:
        try:
            from PIL import Image, ImageOps
        except ImportError:
            raise RuntimeError("Pillow not installed (run setup_windows.ps1 or: pip install pillow pillow-heif)")
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
        _PIL = (Image, ImageOps)
    return _PIL


def heic_supported():
    try:
        Image, _ = pil()
        return ".heic" in Image.registered_extensions()
    except RuntimeError:
        return False


def _dms(v, ref):
    d, m, s = (float(x) for x in v)
    val = d + m / 60 + s / 3600
    return -val if ref in ("S", "W") else val


def probe_image(path):
    Image, _ = pil()
    fields = {"has_audio": 0}
    with Image.open(path) as im:
        w, h = im.size
        ex = im.getexif()
        if ex.get(0x0112) in (5, 6, 7, 8):          # EXIF says rotated 90deg (pillow-heif already applies HEIC rotation)
            w, h = h, w
        from math import gcd
        g = gcd(w, h) or 1
        fields.update(width=w, height=h, resolution=f"{w}x{h}", aspect_ratio=f"{w // g}:{h // g}",
                      orientation="portrait" if h > w else "landscape" if w > h else "square",
                      codec=(im.format or "").lower() or None)
        try:
            ifd = ex.get_ifd(0x8769)
            raw = ifd.get(0x9003) or ifd.get(0x9004)           # DateTimeOriginal / DateTimeDigitized
            if raw:
                off = ifd.get(0x9011) or ifd.get(0x9010)       # OffsetTimeOriginal
                d = str(raw).strip()
                d = f"{d[:4]}-{d[5:7]}-{d[8:10]}T{d[11:19]}" + (str(off).strip() if off else "")
                if valid_date(d):
                    fields["date_created"], fields["_date_source"] = d, "exif"
        except Exception:
            pass
        try:
            gps = ex.get_ifd(0x8825)
            if gps.get(2) and gps.get(4):
                fields["location"] = f"{_dms(gps[2], gps.get(1)):.5f},{_dms(gps[4], gps.get(3)):.5f}"
        except Exception:
            pass
    return fields


class NoVisualStream(Exception):
    """Media file with no picture (audio-only .mp4/.mov). Not a failure: nothing visual to index."""


# ---- videos: ffprobe
def ffprobe_json(path):
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not installed (winget install Gyan.FFmpeg, then reopen PowerShell)")
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                          "-show_streams", str(path)], capture_output=True, text=True, timeout=90,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError("ffprobe could not read file: " + (out.stderr.strip()[:120] or "unknown error"))
    return json.loads(out.stdout)


def probe_ffprobe(path, media_type):
    info = ffprobe_json(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise NoVisualStream("audio-only file (no video stream)")
    fields = {"has_audio": int(any(s.get("codec_type") == "audio" for s in info["streams"]))}
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
        if dur:
            fields["duration"] = round(float(dur), 2)
    tags = {k.lower(): val for k, val in info.get("format", {}).get("tags", {}).items()}
    for key, src in (("com.apple.quicktime.creationdate", "quicktime"), ("creation_time", "container")):
        if tags.get(key) and valid_date(tags[key]):
            fields["date_created"], fields["_date_source"] = tags[key], src
            break
    loc = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location")
    if loc:
        fields["location"] = loc
    return fields


def probe_media(path, media_type):
    """Technical metadata + real capture date. Raises RuntimeError with a human reason on failure."""
    if media_type == "video":
        return probe_ffprobe(path, "video")
    err = None
    try:
        f = probe_image(path)
        if f.get("width"):
            return f
    except Exception as e:
        err = str(e)
    try:                                         # secondary route for formats Pillow lacks
        f = probe_ffprobe(path, "image")
        if f.get("width"):
            return f
    except (RuntimeError, NoVisualStream):
        pass
    ext = os.path.splitext(path)[1].lower()
    if ext in (".heic", ".heif") and not heic_supported():
        raise RuntimeError("HEIC not supported: pillow-heif is missing (run setup_windows.ps1 or: pip install pillow-heif)")
    raise RuntimeError("cannot read image (corrupt or unsupported): " + (err or "unknown").replace(str(path), "<file>"))


def sync_fts(con, asset_id):
    r = con.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    tags = " ".join(t[0] for t in con.execute("SELECT tag FROM tags WHERE asset_id=?", (asset_id,)))
    con.execute("DELETE FROM fts WHERE rowid=?", (asset_id,))
    con.execute("INSERT INTO fts(rowid,exercise,activity,tags,category,subcategory,subject,description,"
                "transcript,environment,file_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, r["exercise"], r["activity"], tags, r["category"], r["subcategory"],
                 r["subject"], r["description"], r["transcript"], r["environment"], r["file_name"]))


# ---------------------------------------------------------------- environment checks / discovery
def cmd_doctor(a):
    ok = True
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    try:
        Image, _ = pil()
        import PIL
        print(f"Pillow {PIL.__version__}: OK")
    except RuntimeError as e:
        print(f"Pillow: MISSING - {e}")
        ok = False
    try:
        import pillow_heif
        print(f"pillow-heif {pillow_heif.__version__}: OK (HEIC {'registered' if heic_supported() else 'NOT registered'})")
        ok &= heic_supported()
    except ImportError:
        print("pillow-heif: MISSING - HEIC photos cannot be read (pip install pillow-heif)")
        ok = False
    for tool in ("ffprobe", "ffmpeg"):
        p = shutil.which(tool)
        print(f"{tool}: {p or 'MISSING - winget install Gyan.FFmpeg (then close and reopen PowerShell)'}")
        ok &= bool(p)
    print("\nAll good." if ok else "\nFix the MISSING items above, then run doctor again.")
    sys.exit(0 if ok else 1)


def count_media(root, cap=300000):
    c = Counter()
    n = 0
    sizes = 0
    for p, ext, st in iter_media([root], []):
        n += 1
        if n > cap:
            c["capped"] = 1
            break
        c["video" if ext in VIDEO_EXT else "image"] += 1
        if is_cloud_only(st):
            c["cloud_only"] += 1
        sizes += st.st_size
    c["bytes"] = sizes
    return c


def cmd_detect(a):
    """Find where the iPhone/iCloud/local media actually lives on this PC."""
    home = Path.home()
    od = [Path(os.environ[k]) for k in ("OneDrive", "OneDriveConsumer") if os.environ.get(k)]
    cands = [home / "Pictures" / "iCloud Photos" / "Photos", home / "Pictures" / "iCloud Photos",
             home / "iCloudPhotos" / "Photos", home / "iCloudDrive", home / "Pictures" / "Camera Roll",
             home / "Pictures", home / "Videos", home / "Downloads", home / "Desktop", home / "Documents"]
    for o in od:
        cands += [o / "Pictures", o / "Pictures" / "Camera Roll"]
    cands += [Path(x) for x in (a.also or [])]
    seen, rows = set(), []
    for c in cands:
        key = os.path.normcase(str(c))
        if key in seen or not c.is_dir():
            continue
        seen.add(key)
        m = count_media(str(c))
        rows.append((c, m))
    if not rows:
        print("No standard media folders found. Pass yours with: detect --also \"D:\\path\"")
        return
    print(f"{'FOLDER':<60} {'VIDEOS':>7} {'IMAGES':>7} {'CLOUD-ONLY':>11} {'SIZE GB':>8}")
    for c, m in rows:
        print(f"{str(c):<60} {m['video']:>7} {m['image']:>7} {m['cloud_only']:>11} {m['bytes'] / 1e9:>8.1f}"
              + ("  (count capped)" if m["capped"] else ""))
    print("\nFolders overlap (Pictures contains iCloud Photos, etc.): scan the most specific folder(s) that hold your footage.")
    best = max(rows, key=lambda r: r[1]["video"] + r[1]["image"] if "iCloud" in str(r[0]) else 0)
    if "iCloud" in str(best[0]):
        print(f"Likely iPhone library: {best[0]}")
    print("Compare TOTAL here with the photo+video count on your iPhone (Settings > General > About). A gap means")
    print("iCloud has not downloaded everything (or those items are in a folder not listed). CLOUD-ONLY files are")
    print("placeholders: right-click the folder > 'Always keep on this device' (or download in iCloud for Windows).")


# ---------------------------------------------------------------- commands
def cmd_init(a):
    con = connect(a, create=True)
    (lib_dir(a) / "contact_sheets").mkdir(exist_ok=True)
    (lib_dir(a) / "transcripts").mkdir(exist_ok=True)
    print(f"Library ready at {lib_dir(a)}")
    con.close()


def iter_media(sources, problems, excludes=()):
    """Walk with scandir: file attributes come with the directory listing, so cloud-only files are never opened."""
    for src in sources:
        stack = [os.path.abspath(os.path.expanduser(str(src)))]
        while stack:
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError as e:
                problems.append(f"cannot read folder {d}: {e.strerror}")
                continue
            with it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            low = e.path.lower()
                            if e.name.lower() not in SKIP_DIRS and not e.name.startswith(".") \
                                    and not any(x in low for x in excludes):
                                stack.append(e.path)
                            continue
                        ext = os.path.splitext(e.name)[1].lower()
                        if ext in MEDIA_EXT and not e.name.startswith(("._", "~$")):
                            yield e.path, ext, e.stat(follow_symlinks=False)
                    except OSError as ex:
                        problems.append(f"cannot stat {e.path}: {ex.strerror}")


def ext_group(ext):
    return {".jpeg": ".jpg", ".heif": ".heic", ".tif": ".tiff"}.get(ext, ext)


def pick_test_sample(entries, n):
    """~n assets mixing formats, sizes and years; a few cloud-only ones are included to exercise detection."""
    rng = random.Random(42)
    n = max(20, min(50, n))
    cloud = [e for e in entries if is_cloud_only(e[2])]
    local = [e for e in entries if not is_cloud_only(e[2])]
    chosen = rng.sample(cloud, min(3, len(cloud)))
    by_group = defaultdict(list)
    for e in local:
        by_group[ext_group(e[1])].append(e)
    buckets = defaultdict(list)
    for g, es in by_group.items():
        sizes = sorted(e[2].st_size for e in es)
        lo, hi = sizes[len(sizes) // 3], sizes[2 * len(sizes) // 3]
        for e in es:
            s = e[2].st_size
            buckets[(g, 0 if s <= lo else 1 if s <= hi else 2, datetime.fromtimestamp(e[2].st_mtime).year)].append(e)
    for b in buckets.values():
        rng.shuffle(b)
    keys = sorted(buckets)
    while len(chosen) < n and any(buckets[k] for k in keys):
        for k in keys:
            if buckets[k] and len(chosen) < n:
                chosen.append(buckets[k].pop())
    return chosen


def video_strip(path, duration, out, n=4, per_frame_timeout=60):
    """Contact sheet for a video: n frames grabbed by fast seeking (-ss before -i jumps to the nearest keyframe
    instead of decoding the whole clip, which would take minutes for a long 4K HEVC video), tiled with Pillow."""
    tmp = out.parent / f"_tmp_{out.stem}"
    tmp.mkdir(parents=True, exist_ok=True)
    frames = []
    dur = max(duration or 1.0, 0.5)
    try:
        for i in range(n):
            t = dur * (0.1 + 0.8 * i / (n - 1)) if dur > 1 else 0
            f = tmp / f"f{i}.jpg"
            try:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
                                "-vf", "scale=360:-2", "-q:v", "4", str(f)],
                               capture_output=True, timeout=per_frame_timeout)
            except subprocess.TimeoutExpired:
                continue
            if f.exists() and f.stat().st_size > 0:
                frames.append(f)
        if not frames:
            return
        Image, _ = pil()
        ims = [Image.open(f).convert("RGB") for f in frames]
        sheet = Image.new("RGB", (sum(i.width for i in ims) + 2 * (len(ims) - 1), max(i.height for i in ims)), "black")
        x = 0
        for im in ims:
            sheet.paste(im, (x, 0))
            x += im.width + 2
        sheet.save(out, "JPEG", quality=85)
    except Exception:
        out.unlink(missing_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def contact_sheet(lib, r):
    """Windows-safe derivatives in the library folder: Pillow for images (incl. HEIC), ffmpeg for video frames."""
    out = lib / "contact_sheets" / f"{r['asset_id']}.jpg"
    if out.exists():
        return str(out)
    if r["availability"] == "cloud_only" or not os.path.exists(r["file_path"]):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    if r["media_type"] == "image":
        try:
            Image, ImageOps = pil()
            with Image.open(r["file_path"]) as im:
                try:
                    im.draft("RGB", (1440, 1440))
                except Exception:
                    pass
                im = ImageOps.exif_transpose(im)
                im.thumbnail((720, 720))
                im.convert("RGB").save(out, "JPEG", quality=85)
        except Exception:
            out.unlink(missing_ok=True)
    if not out.exists() and shutil.which("ffmpeg"):
        if r["media_type"] == "video":
            video_strip(r["file_path"], r["duration"], out)
        else:
            try:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", r["file_path"], "-vf", "scale=720:-2",
                                "-frames:v", "1", str(out)], capture_output=True, timeout=120)
            except Exception:
                pass
    return str(out) if out.exists() and out.stat().st_size > 0 else None


def index_file(con, known, p, ext, st, lib, stats, thumbs):
    fn = os.path.basename(p)
    old = known.get(os.path.normcase(p))
    mt = "video" if ext in VIDEO_EXT else "image"
    base = dict(file_name=fn, media_type=mt, size=st.st_size, mtime=st.st_mtime,
                date_modified=iso(st.st_mtime), indexed_at=now())
    try:
        if is_cloud_only(st):                       # CLOUD_ONLY / NOT_DOWNLOADED: never opened, never "indexed"
            stats["cloud_only"] += 1
            if old:
                con.execute("UPDATE assets SET availability='cloud_only', status=CASE WHEN status='analysed' "
                            "THEN status ELSE 'cloud_only' END WHERE asset_id=?", (old["asset_id"],))
            else:
                f = dict(base, file_path=p, status="cloud_only", availability="cloud_only")
                con.execute(f"INSERT INTO assets({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
            return
        stats["local"] += 1
        if old and old["status"] not in ("cloud_only", "error") and old["size"] == st.st_size \
                and abs((old["mtime"] or 0) - st.st_mtime) < 1:
            upd = {}
            if old["status"] in ("missing", "excluded"):
                upd["status"] = "analysed" if old["analysed_at"] else "probed"
            if old["availability"] != "local":
                upd["availability"] = "local"
            if upd:
                con.execute(f"UPDATE assets SET {','.join(k + '=?' for k in upd)} WHERE asset_id=?",
                            (*upd.values(), old["asset_id"]))
            stats["unchanged"] += 1
            aid = old["asset_id"]
        else:
            if st.st_size == 0:
                raise RuntimeError("zero-byte file (download incomplete?)")
            fields = dict(base, quick_hash=quick_hash(p, st.st_size), availability="local", error=None)
            fields.update(probe_media(p, mt))
            src = fields.pop("_date_source", None)
            dt = parse_dt(fields.get("date_created"))
            if dt:
                fields["date_created"] = dt.isoformat(timespec="seconds")
            else:
                fields["date_created"], src = iso(st.st_mtime), "file_time"    # last resort, flagged as such
            fields["date_source"] = src
            if mt == "video" and (fields.get("duration") or 99) <= LIVE_PHOTO_MAX_S:
                stem = os.path.splitext(p)[0]
                if any(os.path.exists(stem + e2) or os.path.exists(stem + e2.upper()) for e2 in (".heic", ".jpg", ".jpeg")):
                    fields["extra"] = json.dumps({"live_photo_pair": True})
            if old:
                was_cloud = old["status"] == "cloud_only"
                fields["status"] = "probed"
                con.execute(f"UPDATE assets SET {','.join(k + '=?' for k in fields)} WHERE asset_id=?",
                            (*fields.values(), old["asset_id"]))
                stats["now_available" if was_cloud else "changed"] += 1
                aid = old["asset_id"]
            else:
                qh = fields["quick_hash"]
                moved = con.execute("SELECT asset_id,file_path FROM assets WHERE quick_hash=? AND size=?",
                                    (qh, st.st_size)).fetchall()
                gone = [m for m in moved if not os.path.exists(m["file_path"])]
                if gone:                            # same bytes at a new path: keep its analysis
                    aid = gone[0]["asset_id"]
                    con.execute("UPDATE assets SET file_path=?,file_name=?,availability='local',status=CASE WHEN "
                                "analysed_at IS NULL THEN 'probed' ELSE 'analysed' END WHERE asset_id=?", (p, fn, aid))
                    stats["moved"] += 1
                else:
                    fields.update(file_path=p, status="probed")
                    cur = con.execute(f"INSERT INTO assets({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
                                      tuple(fields.values()))
                    aid = cur.lastrowid
                    if moved:
                        con.execute("UPDATE assets SET duplicate_status='exact_duplicate', duplicate_of=? "
                                    "WHERE asset_id=?", (moved[0]["asset_id"], aid))
                    stats["new"] += 1
            sync_fts(con, aid)
        if thumbs:
            r = con.execute("SELECT * FROM assets WHERE asset_id=?", (aid,)).fetchone()
            if r["status"] in ("probed", "analysed"):
                tp = contact_sheet(lib, r)
                if tp:
                    stats["thumbnails_created"] += 1
                    con.execute("UPDATE assets SET thumb_path=? WHERE asset_id=?", (tp, aid))
    except NoVisualStream as e:
        stats["skipped"] += 1
        msg = str(e)
        if old:
            con.execute("UPDATE assets SET status='skipped', error=?, availability='local', size=?, mtime=? "
                        "WHERE asset_id=?", (msg, st.st_size, st.st_mtime, old["asset_id"]))
        else:
            f = dict(base, file_path=p, status="skipped", error=msg, availability="local")
            con.execute(f"INSERT INTO assets({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    except Exception as e:
        stats["errors"] += 1
        stats["error_reasons"][str(e)[:90]] += 1
        msg = str(e)
        if old:
            con.execute("UPDATE assets SET status='error', error=?, availability='local' WHERE asset_id=?",
                        (msg, old["asset_id"]))
        else:
            f = dict(base, file_path=p, status="error", error=msg)
            con.execute(f"INSERT INTO assets({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))


def cmd_scan(a):
    """Incremental: only new/changed/newly-downloaded files are hashed and probed. Rows are never deleted."""
    sources = [os.path.abspath(os.path.expanduser(s)) for s in a.sources]
    bad = [s for s in sources if not os.path.isdir(s)]
    if bad:
        sys.exit("Folder not found: " + "; ".join(bad) + "\nRun `detect` to find your library.")
    base = base_dir(a)
    marker = base / "test_passed.json"
    if not a.test and not a.skip_test:
        try:
            ok_src = {os.path.normcase(s) for s in json.loads(marker.read_text(encoding="utf-8"))["sources"]}
        except Exception:
            ok_src = set()
        if not {os.path.normcase(s) for s in sources} <= ok_src:
            sys.exit("Run the test first, and only scan everything after it passes:\n"
                     f"  scan --test {' '.join(chr(34) + s + chr(34) for s in sources)}")
    if a.test:
        shutil.rmtree(lib_dir(a), ignore_errors=True)       # our own derived test data only
    con = connect(a, create=True)
    lib = lib_dir(a)
    problems = []
    t0 = time.time()
    print("Listing files (no file contents are read)...", file=sys.stderr)
    excludes = [x.lower() for x in (a.exclude or [])]
    entries = list(iter_media(sources, problems, excludes))
    whole = dict(found=len(entries), cloud=sum(1 for e in entries if is_cloud_only(e[2])))
    if a.test:
        entries = pick_test_sample(entries, a.sample)
    known = {os.path.normcase(r["file_path"]): r for r in con.execute("SELECT * FROM assets")}
    stats = dict(found=len(entries), local=0, cloud_only=0, new=0, changed=0, now_available=0, moved=0,
                 unchanged=0, errors=0, skipped=0, excluded=0, thumbnails_created=0, error_reasons=Counter())
    seen = set()
    for i, (p, ext, st) in enumerate(entries, 1):
        seen.add(os.path.normcase(p))
        index_file(con, known, p, ext, st, lib, stats, a.thumbs or a.test)
        step = 5 if (a.thumbs or a.test) else 200
        if i % step == 0:
            con.commit()                                   # resumable: Ctrl+C then re-run continues
            print(f"  {i}/{len(entries)} processed ({time.time() - t0:.0f}s)", file=sys.stderr)
    missing = 0
    if not a.test and not problems:                         # never flag missing on a partial walk
        roots = tuple(os.path.normcase(s).rstrip("\\/") + os.sep for s in sources)
        for key, r in known.items():
            cur = con.execute("SELECT file_path,status FROM assets WHERE asset_id=?", (r["asset_id"],)).fetchone()
            if os.path.normcase(cur["file_path"]) == key and key.startswith(roots) and key not in seen \
                    and cur["status"] not in ("missing", "excluded"):
                parts = {x.lower() for x in cur["file_path"].replace("/", os.sep).split(os.sep)}
                low = cur["file_path"].lower()
                if parts & SKIP_DIRS or any(x in low for x in excludes):
                    con.execute("UPDATE assets SET status='excluded' WHERE asset_id=?", (r["asset_id"],))
                    stats["excluded"] += 1
                else:
                    con.execute("UPDATE assets SET status='missing' WHERE asset_id=?", (r["asset_id"],))
                    missing += 1
    con.commit()
    assign_sessions(con)
    mark_near_duplicates(con)
    con.commit()
    secs = round(time.time() - t0, 1)
    if a.test:
        return test_report(con, stats, whole, problems, sources, marker, secs)
    out = {k: v for k, v in stats.items() if k != "error_reasons"}
    out.update(missing_flagged=missing, seconds=secs, whole_source_found=whole["found"])
    if stats["errors"]:
        out["error_reasons"] = dict(stats["error_reasons"])
    if problems:
        out["unreadable"] = problems[:10]
    print(json.dumps(out))
    if stats["cloud_only"]:
        print(f"\n{stats['cloud_only']} files are CLOUD_ONLY / NOT_DOWNLOADED: not indexed. Download them "
              "(File Explorer > right-click folder > Always keep on this device), then re-run scan.")


def test_report(con, stats, whole, problems, sources, marker, secs):
    q = lambda s: con.execute(s).fetchone()[0]
    idx = "status IN ('probed','analysed')"
    indexed = q(f"SELECT COUNT(*) FROM assets WHERE {idx}")
    meta = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND resolution IS NOT NULL AND (media_type='image' OR duration IS NOT NULL)")
    dates = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND date_source IN ('exif','quicktime','container')")
    heic = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND lower(file_name) GLOB '*.hei[cf]'")
    vids = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND media_type='video'")
    fmts = Counter(os.path.splitext(r[0])[1].lower() for r in con.execute(f"SELECT file_name FROM assets WHERE {idx}"))
    ori = Counter(r[0] for r in con.execute(f"SELECT orientation FROM assets WHERE {idx} AND orientation IS NOT NULL"))
    yrs = sorted({(r[0] or "")[:4] for r in con.execute(f"SELECT date_created FROM assets WHERE {idx}") if r[0]})
    sz = con.execute(f"SELECT MIN(size),MAX(size) FROM assets WHERE {idx}").fetchone()
    local = stats["local"] - stats["skipped"]
    print("PRESKI LIBRARY SCAN TEST (sample only; nothing deleted/moved/modified)")
    print(f"TOTAL FOUND:              {stats['found']}   (whole source folder(s): {whole['found']}, of which cloud-only {whole['cloud']})")
    print(f"LOCALLY AVAILABLE:        {local}")
    print(f"CLOUD ONLY:               {stats['cloud_only']}   <- CLOUD_ONLY / NOT_DOWNLOADED, not indexed, never opened")
    print(f"SUCCESSFULLY INDEXED:     {indexed}")
    print(f"FAILED:                   {stats['errors']}")
    if stats["skipped"]:
        print(f"SKIPPED (audio-only):     {stats['skipped']}   <- no picture to index; not a failure")
    print(f"THUMBNAILS CREATED:       {stats['thumbnails_created']}")
    print(f"METADATA EXTRACTED:       {meta}")
    print(f"CAPTURE DATES FOUND:      {dates}   (from EXIF/QuickTime; {indexed - dates} fell back to file time)")
    print(f"HEIC FILES PROCESSED:     {heic}")
    print(f"VIDEO FILES PROCESSED:    {vids}")
    print(f"\nMix: formats {dict(fmts)} | orientation {dict(ori)} | capture years {yrs[:1] + yrs[-1:] if yrs else []} | "
          f"size {sz[0] / 1e6:.1f}-{sz[1] / 1e6:.1f} MB" if indexed else "\nNothing indexed.")
    for reason, n in stats["error_reasons"].most_common(5):
        print(f"  FAILED x{n}: {reason}")
    for pr in problems[:5]:
        print(f"  WARNING: {pr}")
    warns = []
    for want, label in ((heic, "HEIC"), (vids, "video")):
        if not want:
            warns.append(f"no {label} file was successfully processed in the sample (none in the source, all cloud-only, or all failed)")
    if len(ori) < 2 and indexed > 5:
        warns.append("only one orientation seen in the sample")
    if not heic_supported() and any(f in fmts for f in (".heic", ".heif")):
        warns.append("pillow-heif missing")
    fails = []
    if indexed == 0:
        fails.append("nothing was indexed")
    if local and stats["errors"] / local > 0.10:
        fails.append(f"{stats['errors']} of {local} local files failed (more than 10%)")
    elif stats["errors"]:
        warns.append(f"{stats['errors']} file(s) failed (rare corrupt/incomplete files are tolerated; they are listed in `report`)")
    by_fmt = defaultdict(lambda: [0, 0])                    # ext group -> [ok, failed]
    for r in con.execute("SELECT file_name,status FROM assets WHERE availability='local' AND status!='skipped'"):
        g = by_fmt[ext_group(os.path.splitext(r[0])[1].lower())]
        g[0 if r[1] in ("probed", "analysed") else 1] += 1
    for g, (ok_n, bad_n) in by_fmt.items():
        if bad_n and not ok_n and bad_n >= 2:
            fails.append(f"every {g} file failed ({bad_n}); format not supported on this machine")
    if indexed and stats["thumbnails_created"] < indexed:
        fails.append("thumbnails could not be created for some indexed files")
    if indexed and meta < indexed:
        fails.append("some indexed files have no resolution/duration")
    native = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND lower(file_name) GLOB '*.[hm][eo][iv]*'")
    native_dates = q(f"SELECT COUNT(*) FROM assets WHERE {idx} AND lower(file_name) GLOB '*.[hm][eo][iv]*' "
                     "AND date_source IN ('exif','quicktime','container')")
    if native and native_dates < 0.9 * native and native - native_dates >= 2:   # one stray file is tolerated
        fails.append("HEIC/MOV files are missing their capture dates (metadata extraction not working)")
    if indexed and dates < 0.5 * indexed:
        warns.append("under half the sample has a metadata capture date (screenshots/PNGs and edited files often don't)")
    for w in warns:
        print(f"  NOTE: {w}")
    if fails:
        print("\nTEST FAILED: " + "; ".join(fails) + ". Fix the above (run `doctor`) and re-run the test. Full scan is blocked.")
        sys.exit(1)                      # an earlier pass for other folders stays valid
    try:
        prior = json.loads(marker.read_text(encoding="utf-8")).get("sources", [])
    except Exception:
        prior = []
    merged = list(dict.fromkeys([*prior, *sources]))          # passing one folder never revokes another
    marker.write_text(json.dumps({"sources": merged, "passed_at": now(), "sample": stats["found"],
                                  "indexed": indexed}), encoding="utf-8")
    print(f"\nTEST PASSED in {secs}s. Next: run the same command without --test to index everything.")
    print(f"Test thumbnails: {lib_dir_of(marker) / '_test' / 'contact_sheets'}")


def lib_dir_of(marker):
    return marker.parent


# ---------------------------------------------------------------- on-demand download / free up space (Windows)
def pin(path, on=True):
    """Same as File Explorer's 'Always keep on this device' (on) / 'Free up space' (off). Uses the Windows
    `attrib` pinned/unpinned flags; file CONTENT is never touched, and iCloud keeps the original either way."""
    if os.name != "nt":
        raise RuntimeError("download/free only work on Windows (they drive the iCloud placeholder flags)")
    flags = ["+P", "-U"] if on else ["-P", "+U"]
    r = subprocess.run(["attrib", *flags, path], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip()[:120] or "attrib failed")


def wait_local(paths, timeout_s, label="downloading"):
    """Poll until every file is no longer a placeholder. Returns the paths that arrived."""
    t0 = time.time()
    pending = list(paths)
    done = []
    last = 0
    while pending and time.time() - t0 < timeout_s:
        still = []
        for pth in pending:
            try:
                if is_cloud_only(os.stat(pth)):
                    still.append(pth)
                else:
                    done.append(pth)
            except OSError:
                still.append(pth)
        pending = still
        if pending:
            if time.time() - last > 15:
                print(f"  {label}: {len(done)}/{len(done) + len(pending)} arrived ({int(time.time() - t0)}s)", file=sys.stderr)
                last = time.time()
            time.sleep(2)
    return done


def hydrate(con, rows, a):
    """Download the cloud-only rows (with a disk-space guard), wait, and record availability."""
    targets = [r for r in rows if r["availability"] == "cloud_only"]
    already = len(rows) - len(targets)
    need = sum(r["size"] or 0 for r in targets)
    free = shutil.disk_usage(os.path.expanduser("~")).free
    reserve = a.reserve_gb * 1e9
    print(f"{len(rows)} clips selected: {already} already on this PC, {len(targets)} to download "
          f"({need / 1e9:.1f} GB; {free / 1e9:.0f} GB free, keeping {a.reserve_gb:.0f} GB spare)")
    if not targets:
        return [r["file_path"] for r in rows]
    fits = need <= free - reserve
    if a.dry_run:
        for r in targets[:30]:
            print(f"  would download Clip {r['asset_id']}: {r['file_path']} ({(r['size'] or 0) / 1e6:.0f} MB)")
        print("Dry run only: nothing was downloaded." + ("" if fits else " NOTE: this would NOT fit in free disk space."))
        return []
    if not fits:
        sys.exit("Not enough free disk space for that many. Lower --limit, free up space "
                 "(`free --analysed --yes`), or reduce --reserve-gb.")
    failed = []
    for r in targets:
        try:
            pin(r["file_path"], True)
        except Exception as e:
            failed.append((r["file_path"], str(e)))
    arrived = wait_local([r["file_path"] for r in targets if r["file_path"] not in {f[0] for f in failed}], a.timeout)
    got = set(arrived)
    for r in targets:
        if r["file_path"] in got:
            con.execute("UPDATE assets SET availability='local' WHERE asset_id=?", (r["asset_id"],))
    con.commit()
    print(f"Downloaded {len(arrived)}/{len(targets)}." + (f" Still downloading in the background: {len(targets) - len(arrived) - len(failed)}"
          if len(arrived) + len(failed) < len(targets) else ""))
    for pth, err in failed[:5]:
        print(f"  FAILED {pth}: {err}")
    return [r["file_path"] for r in rows if r["availability"] == "local" or r["file_path"] in got]


def cmd_fetch(a):
    """Download the footage that matches a theme/topic, or specific clip ids."""
    con = connect(a)
    if a.ids:
        marks = ",".join("?" * len(a.ids))
        rows = con.execute(f"SELECT * FROM assets WHERE asset_id IN ({marks})", a.ids).fetchall()
        scores = {}
    else:
        if not a.query:
            sys.exit('Give a topic: fetch "walking for fat loss"  (or --ids 12 40 77)')
        res = run_search(con, a.query, a.limit, a.type)
        rows = [r for _, r, _ in res]
        scores = {r["asset_id"]: s for s, r, _ in res}
        if not rows:
            n = con.execute("SELECT COUNT(*) FROM assets WHERE status='cloud_only'").fetchone()[0]
            sys.exit(f"No tagged footage matches. {n} clips are still cloud-only and untagged, so they can't be "
                     "searched yet: use `download --since/--until` to pull a batch, scan, then tag it.")
    paths = hydrate(con, rows, a)
    if paths and not a.dry_run:
        print("\nReady to use:")
        for r in rows:
            print(f"  Clip {r['asset_id']}" + (f" - {scores[r['asset_id']]}/10" if r["asset_id"] in scores else "")
                  + f"  {r['file_path']}")


def cmd_download(a):
    """Pull a batch of untagged cloud-only clips (by date added/modified) so they can be scanned and tagged."""
    con = connect(a)
    q = "SELECT * FROM assets WHERE status='cloud_only' AND availability='cloud_only'"
    args = []
    if a.type:
        q += " AND media_type=?"
        args.append(a.type)
    if a.since:
        q += " AND date_modified>=?"
        args.append(a.since)
    if a.until:
        q += " AND date_modified<=?"
        args.append(a.until + "T23:59:59")
    rows = con.execute(q + " ORDER BY date_modified DESC LIMIT ?", (*args, a.limit)).fetchall()
    if not rows:
        sys.exit("Nothing matches: no untagged cloud-only clips in that range.")
    print("Placeholders only carry the file's date, which may differ slightly from the real capture date.")
    hydrate(con, rows, a)
    if not a.dry_run:
        print("\nNext: scan the folder again (indexes them), then tag the batch with Claude Code.")


def cmd_free(a):
    """Release disk space for clips already analysed. Never deletes: iCloud keeps the originals."""
    con = connect(a)
    if a.ids:
        marks = ",".join("?" * len(a.ids))
        rows = con.execute(f"SELECT * FROM assets WHERE asset_id IN ({marks}) AND availability='local'", a.ids).fetchall()
    elif a.analysed:
        rows = con.execute("SELECT * FROM assets WHERE status='analysed' AND availability='local'").fetchall()
    else:
        sys.exit("Say what to free: --analysed (everything already tagged) or --ids 1 2 3")
    rows = [r for r in rows if os.path.exists(r["file_path"])]
    gb = sum(r["size"] or 0 for r in rows) / 1e9
    print(f"{len(rows)} analysed clips would be freed (~{gb:.1f} GB). They stay in iCloud and in the library.")
    if not a.yes:
        print("Nothing changed. Add --yes to go ahead.")
        return
    ok = 0
    for r in rows:
        try:
            pin(r["file_path"], False)
            ok += 1
        except Exception as e:
            print(f"  FAILED {r['file_path']}: {e}", file=sys.stderr)
    print(f"Freed {ok}/{len(rows)}. Windows releases the space shortly; the next scan updates the library.")


def mark_near_duplicates(con):
    """Cheap candidates only (same duration +-0.3s, resolution, within a session). Needs visual confirmation
    to promote to similar_shot / different_take / different_angle - never auto-deleted either way."""
    rows = con.execute("SELECT asset_id,duration,resolution,session_id FROM assets WHERE media_type='video' "
                       "AND duration IS NOT NULL AND status NOT IN ('missing','error','cloud_only') "
                       "AND duplicate_status IS NULL ORDER BY resolution,duration").fetchall()
    for i, r in enumerate(rows):
        for q in rows[i + 1:i + 6]:
            if q["resolution"] == r["resolution"] and abs(q["duration"] - r["duration"]) <= 0.3 \
                    and r["session_id"] and r["session_id"] == q["session_id"]:
                con.execute("UPDATE assets SET duplicate_status='near_duplicate', duplicate_of=? "
                            "WHERE asset_id=? AND duplicate_status IS NULL", (r["asset_id"], q["asset_id"]))


def assign_sessions(con):
    """Group clips shot within 45 min of each other into one session (workout/event), by capture time."""
    rows = []
    for r in con.execute("SELECT asset_id,date_created,session_id FROM assets WHERE date_created IS NOT NULL "
                         "AND status IN ('probed','analysed')"):
        d = parse_dt(r["date_created"])
        if d:
            rows.append((d.timestamp(), r))
    rows.sort(key=lambda x: x[0])
    prev, sid, n = None, None, 0
    for t, r in rows:
        if prev is None or t - prev > SESSION_GAP_S:
            n += 1
            sid = f"S{r['date_created'][:10].replace('-', '').replace(':', '')}-{n:05d}"
        prev = t
        if r["session_id"] != sid:
            con.execute("UPDATE assets SET session_id=? WHERE asset_id=?", (sid, r["asset_id"]))


def cmd_pending(a):
    """Assets still needing visual analysis, with a contact-sheet image for Claude to look at."""
    con = connect(a)
    q = ("SELECT * FROM assets WHERE status='probed' AND availability='local' "
         "AND (extra IS NULL OR extra NOT LIKE '%live_photo_pair%') "
         "AND (duplicate_status IS NOT 'exact_duplicate' OR "      # IS NOT: NULL-safe (plain != drops every NULL row)
         "duplicate_of NOT IN (SELECT asset_id FROM assets WHERE status!='missing'))")
    args = []
    if a.session:
        q += " AND session_id=?"
        args.append(a.session)
    rows = con.execute(q + " ORDER BY date_created DESC LIMIT ?", (*args, a.limit)).fetchall()
    out = []
    for r in rows:
        out.append({"asset_id": r["asset_id"], "file_name": r["file_name"], "media_type": r["media_type"],
                    "duration": r["duration"], "orientation": r["orientation"], "has_audio": r["has_audio"],
                    "date_created": r["date_created"], "date_source": r["date_source"],
                    "session_id": r["session_id"], "contact_sheet": contact_sheet(lib_dir(a), r)})
    print(json.dumps(out, indent=1))


def cmd_annotate(a):
    """Upsert analysis from JSONL: {asset_id|file_path, <fields>, tags:[...]}. Only evidenced fields."""
    con = connect(a)
    n = bad = 0
    for line in (sys.stdin if a.file == "-" else open(a.file, encoding="utf-8-sig")):
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
    if r["availability"] == "cloud_only":
        d += ", CLOUD_ONLY / NOT_DOWNLOADED"
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
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8-sig")
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


def cmd_folders(a):
    """Which folders hold the most files? Spot junk (editor caches, thumbnails) before tagging anything."""
    con = connect(a)
    c = defaultdict(Counter)
    for r in con.execute("SELECT file_path,media_type,status,date_source,duplicate_status FROM assets "
                         "WHERE status IN ('probed','analysed','cloud_only','skipped')"):
        k = c[os.path.dirname(r["file_path"])]
        k["total"] += 1
        k[r["media_type"] or "other"] += 1
        k["cloud"] += r["status"] == "cloud_only"
        k["nodate"] += r["date_source"] == "file_time"
        k["dupes"] += r["duplicate_status"] is not None
    print(f"{'TOTAL':>6} {'VIDEO':>6} {'IMAGE':>6} {'CLOUD':>6} {'NO-DATE':>8} {'DUPES':>6}  FOLDER")
    for d, k in sorted(c.items(), key=lambda x: -x[1]["total"])[:a.top]:
        print(f"{k['total']:>6} {k['video']:>6} {k['image']:>6} {k['cloud']:>6} {k['nodate']:>8} {k['dupes']:>6}  "
              + (d if len(d) <= 90 else "..." + d[-87:]))
    print("\nNO-DATE = no camera capture date in the file (screenshots, downloads, app-generated images).")
    print("Exclude junk folders with:  scan \"<root>\" --exclude \"<part of folder path>\"")


def cmd_status(a):
    con = connect(a)
    for r in con.execute("SELECT status,COUNT(*) c FROM assets GROUP BY status"):
        print(f"{r['status']:<10} {r['c']}")


def cmd_report(a):
    con = connect(a)

    def one(sql):
        return con.execute(sql).fetchone()[0]

    live = "status IN ('probed','analysed')"
    fit = "status='analysed' AND category IS NOT NULL AND category NOT IN ('other','lifestyle','b-roll')"
    rows = [
        ("TOTAL ASSETS FOUND", "SELECT COUNT(*) FROM assets WHERE status NOT IN ('missing','excluded')"),
        ("TOTAL ASSETS INDEXED (local)", f"SELECT COUNT(*) FROM assets WHERE {live}"),
        ("CLOUD_ONLY / NOT_DOWNLOADED", "SELECT COUNT(*) FROM assets WHERE availability='cloud_only' AND status!='missing'"),
        ("TOTAL VIDEO ASSETS", f"SELECT COUNT(*) FROM assets WHERE media_type='video' AND {live}"),
        ("TOTAL IMAGE ASSETS", f"SELECT COUNT(*) FROM assets WHERE media_type='image' AND {live}"),
        ("TOTAL FITNESS ASSETS", f"SELECT COUNT(*) FROM assets WHERE {fit}"),
        ("TOTAL TALKING-HEAD ASSETS", "SELECT COUNT(*) FROM assets WHERE talking_head=1"),
        ("TOTAL CARDIO ASSETS", "SELECT COUNT(*) FROM assets WHERE status='analysed' AND (category='cardio' OR "
                                "asset_id IN (SELECT asset_id FROM tags WHERE tag='cardio'))"),
        ("TOTAL TRAINING ASSETS", "SELECT COUNT(*) FROM assets WHERE status='analysed' AND category='training'"),
        ("TOTAL HIGH-POTENTIAL (>=8)", "SELECT COUNT(*) FROM assets WHERE content_potential_score>=8"),
        ("DUPLICATES / NEAR-DUPLICATES", "SELECT COUNT(*) FROM assets WHERE duplicate_status IS NOT NULL AND status IN ('probed','analysed')"),
    ]
    print("CONTENT LIBRARY INTELLIGENCE REPORT")
    for label, sql in rows:
        print(f"{label + ':':<34}{one(sql)}")
    print("\nTOP CONTENT CATEGORIES")
    for r in con.execute("SELECT category,COUNT(*) c FROM assets WHERE category IS NOT NULL GROUP BY category "
                         "ORDER BY c DESC LIMIT 8"):
        print(f"  {r['category']:<14} {r['c']}")
    print("\nTOP HIGH-POTENTIAL FOOTAGE")
    for r in con.execute("SELECT asset_id,description,exercise,content_potential_score p,visual_quality_score v "
                         "FROM assets WHERE content_potential_score IS NOT NULL ORDER BY p DESC,v DESC LIMIT 10"):
        print(f"  Clip {r['asset_id']} - potential {r['p']} / visual {r['v']} - {r['exercise'] or ''} {r['description'] or ''}"[:140])
    st = {r["status"]: r["c"] for r in con.execute("SELECT status,COUNT(*) c FROM assets GROUP BY status")}
    print("\nINDEX STATUS")
    print(f"  analysed {st.get('analysed', 0)} | awaiting analysis {st.get('probed', 0)} | "
          f"cloud-only {st.get('cloud_only', 0)} | skipped audio-only {st.get('skipped', 0)} | excluded {st.get('excluded', 0)} | "
          f"missing from disk {st.get('missing', 0)} | errors {st.get('error', 0)}")
    ds = Counter(r[0] or "none" for r in con.execute(f"SELECT date_source FROM assets WHERE {live}"))
    print(f"  capture date source: {dict(ds)}  (file_time = no metadata date, less reliable for sessions)")
    lp = one("SELECT COUNT(*) FROM assets WHERE extra LIKE '%live_photo_pair%'")
    if lp:
        print(f"  {lp} Live Photo companion clips (indexed, not analysed separately)")
    for r in con.execute("SELECT file_path,error FROM assets WHERE status='error' LIMIT 20"):
        print(f"  ERROR {r['file_path']}: {r['error']}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lib", help="library folder (default $CLIL_LIB or %%USERPROFILE%%\\preski-library)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("detect"); s.add_argument("--also", nargs="*", help="extra folders to check")
    s.set_defaults(fn=cmd_detect)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("scan"); s.add_argument("sources", nargs="+")
    s.add_argument("--test", action="store_true", help="index a 20-50 asset sample into a separate test library")
    s.add_argument("--sample", type=int, default=40, help="test sample size (20-50)")
    s.add_argument("--thumbs", action="store_true", help="also create thumbnails during the scan")
    s.add_argument("--skip-test", action="store_true", help="bypass the must-pass-test gate")
    s.add_argument("--exclude", nargs="+", metavar="TEXT", help="skip any folder whose path contains this text")
    s.set_defaults(fn=cmd_scan)
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
    s = sub.add_parser("fetch", help="download footage matching a topic (cloud-only clips only)")
    s.add_argument("query", nargs="?"); s.add_argument("--ids", nargs="+", type=int)
    s.add_argument("--limit", type=int, default=10); s.add_argument("--type", choices=["video", "image"])
    for sp in (s,):
        sp.add_argument("--reserve-gb", type=float, default=60); sp.add_argument("--timeout", type=int, default=600)
        sp.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("download", help="download a batch of untagged clips by date so they can be tagged")
    s.add_argument("--since", help="YYYY-MM-DD"); s.add_argument("--until", help="YYYY-MM-DD")
    s.add_argument("--type", choices=["video", "image"]); s.add_argument("--limit", type=int, default=50)
    s.add_argument("--reserve-gb", type=float, default=60); s.add_argument("--timeout", type=int, default=900)
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_download)
    s = sub.add_parser("free", help="free disk space for clips that are already tagged (never deletes)")
    s.add_argument("--analysed", action="store_true"); s.add_argument("--ids", nargs="+", type=int)
    s.add_argument("--yes", action="store_true"); s.set_defaults(fn=cmd_free)
    sub.add_parser("dupes").set_defaults(fn=cmd_dupes)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("folders"); s.add_argument("--top", type=int, default=20); s.set_defaults(fn=cmd_folders)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

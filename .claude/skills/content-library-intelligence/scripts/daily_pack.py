#!/usr/bin/env python3
"""Daily pack <-> footage library.

    daily_pack.py import <pack.txt|.md> [--lib LIB] [--date YYYY-MM-DD]   split a pack into one folder per video and
                                                                         check your library for footage for every line
    daily_pack.py status [--lib LIB] [--date D]                           what is ready / waiting for a voiceover
    daily_pack.py make   [--lib LIB] [--date D] [--style S] [--only F1]   edit every video that has a voiceover
                                                                         (drop voice.m4a/.wav/.mp3/.mp4/.mov in its folder)

A pack is the text of the preski-daily-production-pack output: each video starts with an ID line (F1, T2 ...) and has the
labelled sections: On-screen hook, Opening spoken hook, Teleprompter script, Shot list, Objection addressed, Edit steps,
Long-form caption, Pinned comment. Nothing is posted: finished videos land in <lib>/for-phone/finished for your approval.
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import editor  # noqa: E402

LABELS = [("hook", r"on[- ]screen hook"), ("spoken_hook", r"opening spoken hook"), ("script", r"teleprompter script|script"),
          ("shots", r"shot list"), ("objection", r"objection addressed|objection"), ("edit", r"edit steps|edit notes"),
          ("caption", r"long[- ]form caption|caption"), ("pinned", r"pinned comment")]
ID_RE = re.compile(r"^\W*((?:F|T)\d{1,3})\b[\s:.\-–—)]*(.*)$", re.I)
VOICE_EXT = (".m4a", ".wav", ".mp3", ".aac", ".mp4", ".mov")


def lib_dir(a):
    return Path(a.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library")


def today_dir(a):
    return lib_dir(a) / "daily" / (a.date or time.strftime("%Y-%m-%d"))


def clean(line):
    line = line.replace("**", "").replace("__", "")
    return re.sub(r"^[\s#>*_\-]+|[\s*_]+$", "", line).strip()


def parse_pack(text):
    videos, cur, sec = [], None, None
    for raw in text.replace("\r", "").split("\n"):
        line = clean(raw)
        m = ID_RE.match(line) if line and len(line) < 140 else None
        if m and not any(re.match(p + r"\s*:?\s*$", line, re.I) for _, p in LABELS):
            cur = {"id": m.group(1).upper(), "title": m.group(2).strip(" :-–—") or m.group(1).upper(),
                   **{k: [] for k, _ in LABELS}}
            videos.append(cur)
            sec = None
            continue
        if cur is None:
            continue
        hit = None
        for key, pat in LABELS:
            mm = re.match(r"^(?:%s)\s*(?:\([^)]*\))?\s*(?::|[-\u2013\u2014]\s|$)\s*(.*)$" % pat, line, re.I)
            if mm:
                hit = (key, mm.group(1))
                break
        if hit:
            sec = hit[0]
            if hit[1]:
                cur[sec].append(hit[1])
            continue
        if sec and raw.strip():
            cur[sec].append(raw.strip())
    out = []
    for v in videos:
        d = {"id": v["id"], "title": v["title"]}
        for k, _ in LABELS:
            d[k] = "\n".join(v[k]).strip() if k in ("caption", "script", "shots", "edit") else " ".join(v[k]).strip()
        if d["script"]:
            out.append(d)
    return out


def sentences(script):
    s = re.sub(r"\[[^\]]*\]", " ", script)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", s) if p.strip()]
    return parts


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "video"


def cmd_import(a):
    text = Path(a.pack).read_text(encoding="utf-8-sig")
    vids = parse_pack(text)
    if not vids:
        raise SystemExit("No videos found. Each video needs an ID line (F1, T1...) and a 'Teleprompter script' section.")
    day = today_dir(a)
    lib = str(lib_dir(a))
    print("Pack: %d video(s) -> %s\n" % (len(vids), day))
    for v in vids:
        vd = day / ("%s_%s" % (v["id"], slug(v["title"])))
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "script.txt").write_text(v["script"], encoding="utf-8")
        (vd / "caption.txt").write_text(v["caption"], encoding="utf-8")
        (vd / "pack.json").write_text(json.dumps(v, indent=1, ensure_ascii=False), encoding="utf-8")
        have, need, lines = 0, [], []
        for s_ in sentences(v["script"]):
            found = editor.find_clips(lib, s_, 3)
            if found:
                have += 1
                lines.append("OK    %s\n        -> clip %s: %s" % (s_, found[0].get("asset_id"), found[0].get("description") or found[0]["file_path"]))
            else:
                need.append(s_)
                lines.append("FILM  " + s_)
        total = have + len(need)
        pct = int(100 * have / total) if total else 0
        rep = ["%s  %s" % (v["id"], v["title"]), "Footage coverage: %d%% (%d of %d lines have a matching tagged clip)" % (pct, have, total), ""]
        if v["shots"]:
            rep += ["SHOT LIST (from the pack):", v["shots"], ""]
        rep += ["LINE BY LINE:"] + lines
        if need:
            rep += ["", "FILM THESE (no matching tagged footage yet):"] + ["  - " + n for n in need]
        (vd / "film-list.txt").write_text("\n".join(rep), encoding="utf-8")
        print("%-4s %-40s coverage %3d%%   still to film: %d   -> %s" % (v["id"], v["title"][:40], pct, len(need), vd.name))
    print("\nNext: record each voiceover/sit-down video and drop it in that video's folder as voice.m4a (or .wav/.mp3/.mp4/.mov),")
    print("then run:  daily_pack.py make")


def find_voice(vd):
    for ext in VOICE_EXT:
        for p in vd.glob("voice*" + ext):
            return p
    return None


def cmd_status(a):
    day = today_dir(a)
    if not day.exists():
        raise SystemExit("No pack imported for %s yet." % day.name)
    fin = lib_dir(a) / "for-phone" / "finished"
    for vd in sorted(p for p in day.iterdir() if p.is_dir()):
        pid = vd.name.split("_")[0]
        done = list(fin.glob("%s_*.mp4" % pid)) + list(fin.glob("%s.mp4" % pid))
        state = "edited (in approval inbox)" if done else ("voiceover ready: run make" if find_voice(vd) else "waiting for your voiceover")
        print("%-4s %-45s %s" % (pid, vd.name.split("_", 1)[1][:45], state))


def cmd_make(a):
    day = today_dir(a)
    if not day.exists():
        raise SystemExit("No pack imported for %s yet." % day.name)
    fin = lib_dir(a) / "for-phone" / "finished"
    made = 0
    for vd in sorted(p for p in day.iterdir() if p.is_dir()):
        pid = vd.name.split("_")[0]
        if a.only and pid.upper() != a.only.upper():
            continue
        voice = find_voice(vd)
        if not voice:
            print("%s: no voiceover yet, skipped" % pid)
            continue
        pk = json.loads((vd / "pack.json").read_text(encoding="utf-8"))
        out = fin / ("%s_%s.mp4" % (pid, slug(pk["title"])))
        cmd = [sys.executable, str(HERE / "editor.py"), "make", str(voice), "--script", str(vd / "script.txt"),
               "--lib", str(lib_dir(a)), "--title", "%s %s" % (pid, pk["title"]), "--caption-file", str(vd / "caption.txt"),
               "--out", str(out)]
        for flag, val in (("--hook", pk.get("hook")), ("--pinned", pk.get("pinned")), ("--style", a.style)):
            if val:
                cmd += [flag, val]
        if pk.get("pinned"):
            kw = re.search(r"\b([A-Z]{3,12})\b", pk["pinned"])
            if kw:
                cmd += ["--cta", "COMMENT %s" % kw.group(1)]
        print("%s: editing..." % pid)
        r = subprocess.run(cmd)
        if r.returncode == 0:
            made += 1
        else:
            print("%s: the edit failed (see message above)" % pid)
    print("\n%d video(s) edited. Open the phone page (menu 9) and tap Approve posts." % made)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lib"); p.add_argument("--date")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import"); s.add_argument("pack")
    sub.add_parser("status")
    s = sub.add_parser("make"); s.add_argument("--style", default="shred"); s.add_argument("--only")
    a = p.parse_args()
    {"import": cmd_import, "status": cmd_status, "make": cmd_make}[a.cmd](a)


if __name__ == "__main__":
    main()

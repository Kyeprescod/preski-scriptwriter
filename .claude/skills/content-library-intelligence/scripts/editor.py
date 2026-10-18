#!/usr/bin/env python3
"""Preski editor: voiceover (or sit-down video) + your tagged footage -> finished vertical video.

    editor.py make  <voice> [--script S.txt|--words W.json] [--hook TEXT] [--cta TEXT]
                    [--music M.mp3] [--style styles/shred.json] [--lib LIB] [--clips-dir DIR]
                    [--out finished/name.mp4]
    editor.py transcribe <voice> [--model small]          -> <voice>.words.json (needs faster-whisper)
    editor.py plan  <voice> ...                           -> <out>.plan.json (edit it, then:)
    editor.py render <plan.json> [--out file.mp4]

Never touches originals: clips are only read, output goes to the finished folder.
Needs ffmpeg + ffprobe (with libass). Word timings come from faster-whisper, an SRT, or --script (even timing).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIL = HERE / "clil.py"


# ---------- helpers ----------
def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", **kw)
    if r.returncode != 0:
        raise SystemExit("ffmpeg/ffprobe failed:\n" + " ".join(map(str, cmd[:12])) + " ...\n" + r.stderr[-1800:])
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
               "-of", "json", str(path)])
    d = json.loads(out)
    has_video = any(s.get("codec_type") == "video" for s in d.get("streams", []))
    return float(d["format"]["duration"]), has_video


def load_style(path):
    p = Path(path) if path else HERE / "styles" / "shred.json"
    if not p.exists():
        p = HERE / "styles" / (str(path) + ".json")
    return json.loads(p.read_text(encoding="utf-8"))


def ass_time(t):
    t = max(0.0, t)
    return "%d:%02d:%02d.%02d" % (int(t // 3600), int(t % 3600 // 60), int(t % 60), int(round((t % 1) * 100)) % 100)


# ---------- words ----------
def words_from_whisper(path, model="small"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("Transcription needs faster-whisper:  python -m pip install faster-whisper\n"
                         "(or pass --script your_script.txt for even timing, or --words words.json)")
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(path), word_timestamps=True, vad_filter=True)
    return [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
            for s in segs for w in (s.words or []) if w.word.strip()]


def words_from_srt(path):
    out = []
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8-sig").replace("\r", ""))
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    for b in blocks:
        m = pat.search(b)
        if not m:
            continue
        g = list(map(int, m.groups()))
        s, e = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(b[m.end():].split())
        ws = text.split()
        for i, w in enumerate(ws):
            out.append({"w": w, "s": round(s + (e - s) * i / len(ws), 3), "e": round(s + (e - s) * (i + 1) / len(ws), 3)})
    return out


def words_even(text, duration):
    ws = text.split()
    if not ws:
        raise SystemExit("The script file is empty.")
    weights = [max(2, len(re.sub(r"\W", "", w))) + (6 if w[-1:] in ".?!," else 0) for w in ws]
    total, t, out = sum(weights), 0.0, []
    for w, k in zip(ws, weights):
        d = duration * k / total
        out.append({"w": w, "s": round(t, 3), "e": round(t + d, 3)})
        t += d
    return out


def get_words(a, voice, duration):
    if a.words:
        return json.loads(Path(a.words).read_text(encoding="utf-8"))
    cached = Path(str(voice) + ".words.json")
    if a.script:
        txt = Path(a.script).read_text(encoding="utf-8")
        txt = re.sub(r"\[[^\]]*\]", " ", txt)  # drop [0:00-0:04] timing tags
        return words_even(txt, duration)
    if getattr(a, "srt", None):
        return words_from_srt(a.srt)
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    ws = words_from_whisper(voice, getattr(a, "model", "small"))
    cached.write_text(json.dumps(ws, indent=1), encoding="utf-8")
    return ws


# ---------- planning ----------
def make_beats(words, duration, st):
    beats, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = (words[i + 1]["s"] - w["e"]) if i + 1 < len(words) else 9
        length = w["e"] - cur[0]["s"]
        if w["w"][-1:] in ".?!" or gap > 0.55 or length >= st["max_shot"]:
            beats.append(cur)
            cur = []
    if cur:
        beats.append(cur)
    merged = []
    for b in beats:  # merge too-short beats into the previous one
        if merged and (b[-1]["e"] - b[0]["s"]) < st["min_shot"]:
            merged[-1] += b
        else:
            merged.append(b)
    out = []
    for i, b in enumerate(merged):
        s = 0.0 if i == 0 else b[0]["s"]
        e = duration if i == len(merged) - 1 else merged[i + 1][0]["s"]
        out.append({"start": round(s, 3), "end": round(e, 3), "text": " ".join(x["w"] for x in b)})
    return out


def find_clips(lib, text, limit=6):
    cmd = [sys.executable, str(CLIL)] + (["--lib", lib] if lib else []) + \
          ["search", text, "--limit", str(limit), "--type", "video", "--json"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return []
    rows = data if isinstance(data, list) else data.get("results", [])
    return [x for x in rows if x.get("file_path") and os.path.exists(x["file_path"])]


def plan_edit(a):
    st = load_style(a.style)
    voice = Path(a.voice)
    duration, has_video = probe(voice)
    words = get_words(a, voice, duration)
    beats = make_beats(words, duration, st)
    pool = []
    if a.clips_dir:
        pool = [str(p) for p in sorted(Path(a.clips_dir).rglob("*")) if p.suffix.lower() in (".mp4", ".mov", ".m4v")]
    used, n = set(), len(beats)
    face = has_video and not a.no_face
    for i, b in enumerate(beats):
        b["source"], b["clip"], b["clip_start"], b["asset_id"] = "clip", None, 0.0, None
        if face and (b["start"] < st["face_open_seconds"] or b["end"] > duration - st["face_close_seconds"]):
            b["source"] = "face"
            continue
        cands = [c for c in find_clips(a.lib, b["text"]) if c["file_path"] not in used] if (a.lib or not pool) else []
        b["fallback"] = False
        pick = cands[0]["file_path"] if cands else None
        if cands:
            b["asset_id"] = cands[0].get("asset_id")
        if not pick and pool:
            pick = next((p for p in pool if p not in used), pool[i % len(pool)])
        if pick:
            used.add(pick)
            cd, _ = probe(pick)
            need = b["end"] - b["start"]
            b["clip"], b["clip_start"] = pick, round(max(0.0, (cd - need) / 2), 2)
        else:
            b["source"] = "card"  # no footage found: branded text card, and the report says so
    if a.lib:  # second pass: lines with no match get the library's best showcase footage instead of a blank card
        spare = [c for c in find_clips(a.lib, "impressive showcase", 12) if c["file_path"] not in used]
        for b in beats:
            if b["source"] == "card" and spare:
                c = spare.pop(0)
                cd, _ = probe(c["file_path"])
                need = b["end"] - b["start"]
                used.add(c["file_path"])
                b.update(source="clip", clip=c["file_path"], asset_id=c.get("asset_id"), fallback=True,
                         clip_start=round(max(0.0, (cd - need) / 2), 2))
    plan = {"voice": str(voice.resolve()), "duration": duration, "has_face": face, "style": st,
            "words": words, "beats": beats, "hook": a.hook, "cta": a.cta,
            "music": str(Path(a.music).resolve()) if a.music else None}
    out = Path(a.out or (Path("finished") / (voice.stem + ".mp4"))).with_suffix(".plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    gaps = [b["text"] for b in beats if b["source"] == "card" or b.get("fallback")]
    print("Plan: %s  (%d shots, %.1fs)" % (out, n, duration))
    if gaps:
        print("No matching footage for these lines (best showcase clip or a text card used instead) - film these:")
        for g in gaps:
            print("  - " + g)
    return out


# ---------- captions (ASS) ----------
def build_ass(plan, path):
    st = plan["style"]
    W, H = st["width"], st["height"]
    hdr = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H, "WrapStyle: 2", "",
           "[V4+ Styles]",
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
           "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
           "Style: Cap,%s,%d,%s,%s,%s,&H64000000,-1,0,0,0,100,100,0,0,1,%d,2,5,60,60,0,1" %
           (st["font"], st["caption_size"], st["caption_color"], st["highlight_color"], st["outline_color"], st["caption_outline"]),
           "Style: Hook,%s,%d,&H0000E5FF,&H0000E5FF,%s,&H64000000,-1,0,0,0,100,100,0,0,1,%d,3,5,70,70,0,1" %
           (st["font"], st["hook_size"], st["outline_color"], st["caption_outline"]),
           "Style: Cta,%s,%d,%s,%s,%s,&H64000000,-1,0,0,0,100,100,0,0,1,%d,3,5,70,70,0,1" %
           (st["font"], st["cta_size"], st["caption_color"], st["highlight_color"], st["outline_color"], st["caption_outline"]),
           "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    ev = []
    ws = plan["words"]
    k = st["caption_lines_words"]
    clean = lambda w: w.upper().replace("{", "(").replace("}", ")").replace("\\", "")

    def wrap(text, width):
        lines, cur = [], ""
        for w in clean(text).split():
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        return "\\N".join(lines + [cur])
    for li in range(0, len(ws), k):
        line = ws[li:li + k]
        nxt = ws[li + k]["s"] if li + k < len(ws) else plan["duration"]
        for j, w in enumerate(line):
            s = w["s"]
            e = line[j + 1]["s"] if j + 1 < len(line) else min(nxt, max(w["e"] + 0.25, s + 0.2))
            parts = []
            for q, x in enumerate(line):
                t = clean(x["w"])
                parts.append(("{\\c%s\\fscx112\\fscy112}%s{\\c%s\\fscx100\\fscy100}" %
                              (st["highlight_color"], t, st["caption_color"])) if q == j else t)
            ev.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,{\\an5\\pos(%d,%d)}%s" %
                      (ass_time(s), ass_time(e), W // 2, st["caption_y"], " ".join(parts)))
    if plan.get("hook"):
        ev.append("Dialogue: 1,%s,%s,Hook,,0,0,0,,{\\an5\\pos(%d,%d)\\fad(120,200)}%s" %
                  (ass_time(0), ass_time(st["hook_seconds"]), W // 2, st["hook_y"], wrap(plan["hook"], 16)))
    if plan.get("cta"):
        ev.append("Dialogue: 1,%s,%s,Cta,,0,0,0,,{\\an5\\pos(%d,%d)\\fad(150,0)}%s" %
                  (ass_time(max(0, plan["duration"] - st["cta_seconds"])), ass_time(plan["duration"]),
                   W // 2, st["cta_y"], wrap(plan["cta"], 20)))
    Path(path).write_text("\n".join(hdr + ev) + "\n", encoding="utf-8")


# ---------- render ----------
def esc_filter_path(p):
    p = str(p).replace("\\", "/")
    return re.sub(r"^([A-Za-z]):", r"\1\\:", p).replace("'", r"\'")


def render(plan_path, out=None):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    st = plan["style"]
    W, H, FPS = st["width"], st["height"], st["fps"]
    out = Path(out or Path(plan_path).with_suffix("").with_suffix(".mp4"))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="preski_edit_"))
    venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    fit = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1" % (W, H, W, H)
    parts = []
    try:
        for i, b in enumerate(plan["beats"]):
            dur = max(0.2, b["end"] - b["start"])
            f = tmp / ("s%03d.mp4" % i)
            vf = fit
            if st.get("punch_every") and i % st["punch_every"] == 1:
                z = st["punch_zoom"]
                vf += ",crop=iw/%.3f:ih/%.3f,scale=%d:%d" % (z, z, W, H)
            vf += "," + st["grade"] + ",fps=%d" % FPS
            if b["source"] == "clip" and b["clip"]:
                cmd = ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-ss", str(b["clip_start"]), "-i", b["clip"],
                       "-t", "%.3f" % dur, "-vf", vf] + venc + [str(f)]
            elif b["source"] == "face":
                cmd = ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % b["start"], "-i", plan["voice"],
                       "-t", "%.3f" % dur, "-vf", vf] + venc + [str(f)]
            else:  # text card
                cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                       "color=c=0x101014:s=%dx%d:r=%d:d=%.3f" % (W, H, FPS, dur), "-vf", "format=yuv420p"] + venc + [str(f)]
            run(cmd)
            parts.append(f)
        lst = tmp / "list.txt"
        lst.write_text("".join("file '%s'\n" % str(p).replace("\\", "/") for p in parts), encoding="utf-8")
        base = tmp / "base.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
        ass = tmp / "captions.ass"
        build_ass(plan, ass)
        vfs = ["ass='%s'" % esc_filter_path(ass)]
        if st.get("progress_bar"):
            vfs.append("drawbox=x=0:y=ih-14:w='iw*t/%.3f':h=14:color=0x%s@0.95:t=fill" % (plan["duration"], st["accent_hex"]))
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(base), "-i", plan["voice"]]
        if plan.get("music"):
            cmd += ["-stream_loop", "-1", "-i", plan["music"]]
            af = "[1:a]%s[v];[2:a]volume=%s[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]" % (st["voice_loudnorm"], st["music_volume"])
        else:
            af = "[1:a]%s[a]" % st["voice_loudnorm"]
        cmd += ["-filter_complex", af, "-vf", ",".join(vfs), "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-t", "%.3f" % plan["duration"], "-movflags", "+faststart", str(out)]
        run(cmd)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Finished video: %s" % out)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("voice")
        s.add_argument("--script"); s.add_argument("--words"); s.add_argument("--srt")
        s.add_argument("--model", default="small")
        s.add_argument("--hook"); s.add_argument("--cta"); s.add_argument("--music")
        s.add_argument("--style"); s.add_argument("--lib"); s.add_argument("--clips-dir")
        s.add_argument("--no-face", action="store_true"); s.add_argument("--out")
    s = sub.add_parser("make"); common(s)
    s = sub.add_parser("plan"); common(s)
    s = sub.add_parser("transcribe"); s.add_argument("voice"); s.add_argument("--model", default="small")
    s = sub.add_parser("render"); s.add_argument("plan"); s.add_argument("--out")
    a = p.parse_args()
    if a.cmd == "transcribe":
        ws = words_from_whisper(a.voice, a.model)
        Path(a.voice + ".words.json").write_text(json.dumps(ws, indent=1), encoding="utf-8")
        print("%d words -> %s.words.json" % (len(ws), a.voice))
    elif a.cmd == "plan":
        plan_edit(a)
    elif a.cmd == "render":
        render(a.plan, a.out)
    else:
        pp = plan_edit(a)
        render(pp, a.out or str(pp).replace(".plan.json", ".mp4"))


if __name__ == "__main__":
    main()

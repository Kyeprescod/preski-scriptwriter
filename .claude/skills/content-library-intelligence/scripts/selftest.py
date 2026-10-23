#!/usr/bin/env python3
"""Preski self-test: proves every moving part works on THIS machine using made-up clips (never touches your footage).

    python selftest.py [--with-claude] [--keep]

Prints PASS/FAIL per check and writes selftest_report.txt next to this file's library folder. Send that file to Claude
if anything fails. --with-claude also tests the unattended-tagging permissions using your Claude Code login (uses a
tiny bit of your plan).
"""
import argparse, json, os, platform, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
results = []


def check(name, fn):
    t = time.time()
    try:
        info = fn()
        info = "" if info is True else info
        results.append((name, True, info or "", time.time() - t))
        print("  PASS  %s %s" % (name, ("- " + str(info)) if info else ""))
    except Exception as e:  # noqa: BLE001 - report everything
        msg = str(e).strip().splitlines()[-1][:300] if str(e).strip() else repr(e)
        results.append((name, False, msg, time.time() - t))
        print("  FAIL  %s - %s" % (name, msg))


def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", **kw)
    if r.returncode != 0:
        raise RuntimeError("%s -> exit %d: %s" % (" ".join(map(str, cmd[:4])), r.returncode, (r.stderr or r.stdout)[-400:]))
    return r.stdout


def clil(lib, *args):
    return run([PY, str(HERE / "clil.py"), "--lib", str(lib)] + [str(a) for a in args])


def probe(path):
    d = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-show_entries",
                        "format=duration", "-of", "json", str(path)]))
    v = [s for s in d["streams"] if s["codec_type"] == "video"]
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return float(d["format"]["duration"]), (v[0]["width"], v[0]["height"]) if v else None, bool(a)


def make_media(root):
    media = root / "media"
    media.mkdir()
    srcs = (("jog", "testsrc2=s=1920x1080:r=30:d=8", 300), ("boxing", "smptebars=s=1080x1920:r=30:d=9", 400),
            ("press", "rgbtestsrc=s=1280x720:r=30:d=10", 500), ("talk", "mandelbrot=s=1080x1920:r=30", 600))
    for name, src, hz in srcs:  # all different, so the duplicate detector leaves them alone
        d = 11 if name == "talk" else None
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src] + (["-t", str(d)] if d else []) +
            ["-f", "lavfi", "-i", "sine=f=%d:d=11" % hz, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(media / (name + ".mp4"))])
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=180:d=14", str(root / "voice.wav")])
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=14", "-i", str(root / "voice.wav"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(root / "sit.mp4")])
    (root / "script.txt").write_text("Go for a jog. Then hit the boxing bag. Then press heavy dumbbells. "
                                     "That is how you burn fat. Comment ABS for my free plan.", encoding="utf-8")
    ann = [
        {"file_name": "jog.mp4", "category": "cardio", "activity": "jogging", "description": "jogging", "tags": ["jogging", "running", "cardio"],
         "visual_quality_score": 8, "content_potential_score": 8},
        {"file_name": "boxing.mp4", "category": "training", "activity": "boxing", "description": "boxing bag", "tags": ["boxing", "impressive", "showcase"],
         "visual_quality_score": 8, "content_potential_score": 9},
        {"file_name": "press.mp4", "category": "training", "exercise": "dumbbell press", "description": "dumbbell press",
         "tags": ["press", "dumbbell", "shoulders", "impressive"], "visual_quality_score": 7, "content_potential_score": 8},
        {"file_name": "talk.mp4", "category": "talking-head", "talking_head": 1, "description": "talking to camera", "tags": ["talking head"],
         "visual_quality_score": 7, "content_potential_score": 7}]
    (root / "ann.jsonl").write_text("\n".join(json.dumps(a) for a in ann), encoding="utf-8")
    return media


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-claude", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip the slow video-editing checks")
    a = ap.parse_args()
    root = Path(tempfile.mkdtemp(prefix="preski_selftest_"))
    lib = root / "lib"
    print("Preski self-test on %s, Python %s\nWorking in %s (made-up clips only)\n" % (platform.platform(), platform.python_version(), root))

    print("1. Tools")
    check("python 3.9+", lambda: sys.version_info >= (3, 9) or (_ for _ in ()).throw(RuntimeError(sys.version)))
    check("ffmpeg + ffprobe", lambda: run(["ffmpeg", "-version"]).splitlines()[0])
    check("ffmpeg has subtitles (libass) + x264", lambda: all(k in run(["ffmpeg", "-hide_banner", "-filters"]) + run(["ffmpeg", "-hide_banner", "-encoders"])
                                                              for k in (" ass ", "libx264")) or (_ for _ in ()).throw(RuntimeError("ffmpeg build lacks libass/x264")))
    check("Pillow + pillow-heif", lambda: (__import__("PIL"), __import__("pillow_heif"), "ok")[-1])
    try:
        import faster_whisper  # noqa: F401
        print("  info  faster-whisper installed (speech-to-text ready)")
    except ImportError:
        print("  info  faster-whisper NOT installed (only needed when you don't give a script; menu 10 installs it)")
    print("  info  Claude Code CLI: %s" % (shutil.which("claude") or "not found"))
    if platform.system() == "Windows":
        for t in ("attrib", "schtasks"):
            check("windows tool: " + t, lambda t=t: shutil.which(t) or (_ for _ in ()).throw(RuntimeError(t + " missing")))

    print("\n2. Library (scan, tag, search, collect)")
    try:
        media = make_media(root)
    except Exception as e:  # noqa: BLE001
        print("  FAIL  could not make test clips: %s" % e)
        return finish(root, a)
    check("init", lambda: clil(lib, "init") and "ok")
    check("scan finds 4 clips", lambda: "found\": 4" in clil(lib, "scan", media, "--skip-test") or (_ for _ in ()).throw(RuntimeError("expected 4")))
    check("pending lists clips with contact sheets", lambda: [x for x in json.loads(clil(lib, "pending", "--limit", 10)) if x.get("contact_sheet")] and "ok")
    def do_annotate():
        ids = {x["file_name"]: x["asset_id"] for x in json.loads(clil(lib, "pending", "--limit", 20))}
        rows = []
        for line in (root / "ann.jsonl").read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            d["asset_id"] = ids[d.pop("file_name")]
            rows.append(json.dumps(d))
        (root / "ann_ids.jsonl").write_text("\n".join(rows), encoding="utf-8")
        if '"annotated": 4' not in clil(lib, "annotate", root / "ann_ids.jsonl"):
            raise RuntimeError("annotate did not accept 4 clips")
    check("annotate (tag)", do_annotate)
    check("search 'jogging' finds jog.mp4", lambda: "jog.mp4" in clil(lib, "search", "jogging", "--json") or (_ for _ in ()).throw(RuntimeError("no match")))
    check("search plural/hyphen 'dumbbell presses'", lambda: "press.mp4" in clil(lib, "search", "dumbbell presses", "--json") or (_ for _ in ()).throw(RuntimeError("no match")))
    dest = root / "for-phone" / "showcase"
    def do_collect():
        out = clil(lib, "collect", "impressive", "--min-score", 7, "--dest", dest)
        n = len(list(dest.glob("*.mp4")))
        if n < 2:
            raise RuntimeError("only %d file(s) copied; tool said: %s" % (n, " | ".join(out.strip().splitlines()[-3:])))
        return "%d clips + manifest" % n
    check("collect copies impressive clips", do_collect)
    check("originals untouched", lambda: all((media / n).exists() for n in ("jog.mp4", "boxing.mp4", "press.mp4", "talk.mp4")) and "ok")
    check("report", lambda: "analysed" in clil(lib, "report").lower() or (_ for _ in ()).throw(RuntimeError("no report")))

    def gemini_plumbing():
        """Gemini tagger end to end against a tiny fake Gemini server (no key, no network, no cost)."""
        from http.server import BaseHTTPRequestHandler, HTTPServer
        answer = {"category": "cardio", "activity": "jogging", "description": "man jogging on a path", "tags": ["Jogging", "cardio!"],
                  "talking_head": 0, "visual_quality_score": 7.2, "content_potential_score": 8, "hook_potential_score": 5}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *x):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        srv = HTTPServer(("127.0.0.1", free_port()), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        glib = root / "glib"
        clil(glib, "init"); clil(glib, "scan", media, "--skip-test")
        env = dict(os.environ, GEMINI_API_KEY="test-key", GEMINI_API_BASE="http://127.0.0.1:%d" % srv.server_port)
        r = subprocess.run([PY, str(HERE / "gemini_tagger.py"), "--lib", str(glib), "--limit", "10", "--rpm", "600"], env=env,
                           capture_output=True, text=True, errors="replace")
        srv.shutdown()
        if r.returncode != 0 or "Gemini tagged 4" not in r.stdout:
            raise RuntimeError((r.stdout + r.stderr)[-300:])
        if "jogging" not in clil(glib, "search", "jogging", "--json"):
            raise RuntimeError("tags saved but not searchable")
        return "4 clips tagged via fake Gemini, searchable"
    check("Gemini tagger: tags, saves, searchable", gemini_plumbing)
    pack = root / "pack.md"
    pack.write_text("## F1 - Jog and box\n**On-screen hook:** TEST HOOK\n**Teleprompter script:**\nGo for a jog. Hit the boxing bag.\n"
                    "**Long-form caption:**\nLine one.\nLine two.\n**Pinned comment:** Comment ABS please\n", encoding="utf-8")
    dp = [PY, str(HERE / "daily_pack.py"), "--lib", str(lib), "--date", "2026-01-01"]

    def daily_pack():
        out = run(dp + ["import", str(pack)])
        vd = next((lib / "daily" / "2026-01-01").glob("F1_*"))
        if "F1" not in out or not (vd / "film-list.txt").exists() or "OK" not in (vd / "film-list.txt").read_text(encoding="utf-8"):
            raise RuntimeError("pack not split or not matched to footage")
        shutil.copy(root / "voice.wav", vd / "voice.wav")
        run(dp + ["make"])
        done = list((lib / "for-phone" / "finished").glob("F1_*.mp4"))
        if not done:
            raise RuntimeError("no finished video from the pack")
        return "pack -> footage check -> edited video"
    check("daily pack: import, match footage, edit", daily_pack)
    if a.quick:
        return finish(root, a)
    print("\n3. Editor (every style, voiceover and sit-down)")
    ed = [PY, str(HERE / "editor.py")]
    fin = root / "for-phone" / "finished"

    def make(style, voice, extra=()):
        out = fin / ("%s_%s.mp4" % (style, Path(voice).stem))
        run(ed + ["make", str(root / voice), "--script", str(root / "script.txt"), "--lib", str(lib), "--style", style, "--out", str(out)] + list(extra))
        dur, size, has_audio = probe(out)
        if size != (1080, 1920) or not has_audio or abs(dur - 14) > 0.6:
            raise RuntimeError("bad output %s %s audio=%s" % (dur, size, has_audio))
        return "%.1fs 1080x1920 + audio" % dur
    for st in ("shred", "explainer", "compare"):
        check("voiceover, style " + st, lambda st=st: make(st, "voice.wav"))
    check("sit-down video with cutaways", lambda: make("explainer", "sit.mp4"))
    png = root / "ov.png"
    from PIL import Image  # noqa: E402
    Image.new("RGBA", (300, 200), (255, 90, 30, 255)).save(png)
    check("overlay graphic + hook + CTA", lambda: make("compare", "voice.wav", ["--overlay", "%s:1:6:100:300:300" % png, "--hook", "TEST HOOK", "--cta", "COMMENT ABS FOR THE FREE PLAN"]))

    print("\n4. Phone page (share server)")
    port = free_port()
    proc = subprocess.Popen([PY, str(HERE / "share_server.py"), str(root / "for-phone"), "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.5)
    try:
        key = (root / "for-phone" / ".share_key").read_text().strip()
        base = "http://127.0.0.1:%d" % port
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path, headers=None):
            req = urllib.request.Request(base + path, headers=headers or {})
            try:
                return opener.open(req, timeout=10)
            except urllib.error.HTTPError as e:
                return e
        check("page needs the private key", lambda: get("/").code == 403 and "ok")
        check("lists folders with key", lambda: b"finished" in get("/?k=" + key).read() or (_ for _ in ()).throw(RuntimeError("no listing")))
        some = next((fin).glob("*.mp4")).name
        check("video streams with Range (phone playback)", lambda: get("/finished/%s?k=%s" % (some, key), {"Range": "bytes=0-99"}).status == 206 and "ok")
        def approvals():
            items = json.loads(get("/api/items?k=" + key).read())["items"]
            if not items:
                raise RuntimeError("no finished videos listed")
            req = urllib.request.Request(base + "/api/decide?k=" + key, method="POST", headers={"Content-Type": "application/json"},
                                         data=json.dumps({"id": items[0]["id"], "status": "approved", "platforms": ["instagram"], "publish_at": "2026-10-24T12:30"}).encode())
            rec = json.loads(opener.open(req, timeout=10).read())
            bad = urllib.request.Request(base + "/api/decide", method="POST", data=b"{}")
            try:
                opener.open(bad, timeout=10)
                raise RuntimeError("decision accepted without the key")
            except urllib.error.HTTPError as e:
                if e.code != 403:
                    raise
            saved = json.loads((root / "for-phone" / "approvals.json").read_text(encoding="utf-8"))
            return "approved, saved" if rec["status"] == "approved" and saved else None
        check("approval inbox lists videos and saves a decision", approvals)
        check("blocks path escape", lambda: get("/../../etc/hosts?k=" + key).code in (403, 404) and "ok")
    finally:
        proc.terminate()

    print("\n5. Unattended parts")
    check("nightly/autotag scripts present", lambda: all((HERE / n).exists() for n in ("preski-nightly.cmd", "preski-autotag.cmd", "preski-menu.cmd")) and "ok")
    if a.with_claude:
        if not shutil.which("claude"):
            check("claude CLI installed", lambda: (_ for _ in ()).throw(RuntimeError("not found: irm https://claude.ai/install.ps1 | iex")))
        else:
            check("claude -p works (logged in)", lambda: "OK" in run(["claude", "-p", "Reply with exactly: OK", "--allowedTools", "Read"], timeout=180))
            cl = "%s %s --lib %s report" % (PY, HERE / "clil.py", lib)
            def clil_allowed():
                for _ in range(3):  # the model sometimes paraphrases instead of pasting; retry
                    out = run(["claude", "-p", "Run exactly this command and paste its output verbatim, nothing else: " + cl,
                               "--allowedTools", "Bash(*clil.py*)"], timeout=240)
                    if "TOTAL ASSETS" in out.upper():
                        return "ok"
                raise RuntimeError("clil.py was blocked or its output never appeared (see preski-autotag.cmd allowedTools)")
            check("claude may run clil.py (auto-tag permission)", clil_allowed)
            marker = root / "should_not_exist.txt"
            run(["claude", "-p", "Create the file %s containing hi using any shell command" % marker, "--allowedTools", "Bash(*clil.py*)"], timeout=240)
            check("claude is BLOCKED from other commands", lambda: (not marker.exists()) and "ok" or (_ for _ in ()).throw(RuntimeError("permissions too loose!")))
    else:
        print("  info  skipped Claude permission checks (run with --with-claude to prove unattended tagging)")
    finish(root, a)


def finish(root, a):
    ok = sum(1 for r in results if r[1])
    bad = [r for r in results if not r[1]]
    print("\n%d passed, %d failed" % (ok, len(bad)))
    rep = HERE.parent / "selftest_report.txt"
    try:
        rep = Path(os.environ.get("CLIL_LIB", Path.home() / "preski-library"))
        rep.mkdir(parents=True, exist_ok=True)
        rep = rep / "selftest_report.txt"
    except OSError:
        rep = Path("selftest_report.txt")
    rep.write_text("\n".join("%s  %s  %s" % ("PASS" if p else "FAIL", n, i) for n, p, i, _ in results) +
                   "\n\n%d passed, %d failed\nplatform: %s python %s\n" % (ok, len(bad), platform.platform(), platform.python_version()), encoding="utf-8")
    print("Report saved: %s" % rep)
    if not a.keep:
        shutil.rmtree(root, ignore_errors=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

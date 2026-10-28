"""Edit one production job with the existing editor and report the result as a patch.

  studio_bridge.py edit --job job.json --assets-dir DIR --root PHONE_ROOT [--out-patch patch.json]

--job is the job document as read from the shared database (ArtifactData out_dir file).
--assets-dir holds one file per asset id (<asset_id>.mp4), as downloaded from the asset store.
It never writes to the shared database itself: it checks the prerequisites, runs editor.py make
(no second editing engine), verifies the export is a decodable 9:16 H.264 MP4, drops the video into
<root>/finished so the phone approval inbox lists it, validates the Postiz package offline, and
writes the patch the caller applies with a version-pinned update.
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio_jobs  # noqa: E402


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,width,height", "-of", "json", str(path)],
                       capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    d = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    return s, d.returncode == 0 and not d.stderr.strip()


def postiz_package(job, mp4, meta):
    """Offline check of what Postiz needs. Nothing is sent anywhere."""
    p = {"job_id": job["job_id"], "media": str(mp4), "caption": meta.get("caption", ""),
         "platforms": meta.get("platforms", []), "publish_at": meta.get("publish_at", ""),
         "pinned_comment": meta.get("pinned_comment", ""), "type": "draft", "test": bool(job.get("test"))}
    errs = []
    if not p["caption"]:
        errs.append("caption empty")
    if not p["platforms"]:
        errs.append("no platforms")
    if not Path(mp4).exists():
        errs.append("media missing")
    if len(p["caption"]) > 2200:
        errs.append("caption over 2200 characters")
    return p, errs


def edit(a):
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))
    job = job.get("data", job)
    errs = studio_jobs.validate(job)
    if errs:
        return fail(job, "invalid record: " + "; ".join(errs))
    if job["production_status"] != "EDITING":
        return fail(job, "job is %s, must be EDITING (claim it first)" % job["production_status"])
    adir = Path(a.assets_dir)
    clips = []
    for aid in job["asset_ids"]:
        f = next(iter(adir.glob(aid + ".*")), None)
        if not f:
            return fail(job, "asset %s not downloaded" % aid)
        s, decodes = probe(f)
        if not decodes or not s.get("width"):
            return fail(job, "asset %s is not playable media" % aid)
        clips.append(f)
    work = Path(a.root) / "jobs" / job["job_id"]
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.txt").write_text(job["script"], encoding="utf-8")
    (work / "caption.txt").write_text(job.get("caption") or "", encoding="utf-8")
    out = Path(a.root) / "finished" / (job["job_id"] + ".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    ei = job.get("edit_instructions") or {}
    # voiceover: a recorded voice asset if the job names one, else a silent track as long as the footage
    # (captions are timed evenly from the script). Footage comes from the job's assets only.
    voice = adir / (ei["voice_asset"] + ".m4a") if ei.get("voice_asset") else None
    if not voice or not voice.exists():
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clips[0])],
                                   capture_output=True, text=True).stdout.strip() or 5)
        voice = work / "voice-silent.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(dur), str(voice)], check=True)
    cdir = work / "clips"
    cdir.mkdir(exist_ok=True)
    for c in clips:
        (cdir / c.name).write_bytes(c.read_bytes())
    cmd = [sys.executable, str(HERE / "editor.py"), "make", str(voice), "--clips-dir", str(cdir), "--script", str(work / "script.txt"),
           "--hook", job.get("onscreen_hook") or "", "--cta", ei.get("cta", ""), "--style", ei.get("style", "shred"),
           "--no-face", "--caption-file", str(work / "caption.txt"), "--title", job.get("video_concept") or job["job_id"],
           "--out", str(out)]
    if a.lib:
        cmd += ["--lib", a.lib]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        return fail(job, "editor failed: " + (r.stderr or r.stdout)[-400:])
    s, decodes = probe(out)
    if not (decodes and s.get("codec_name") == "h264" and (s.get("width"), s.get("height")) == (1080, 1920)):
        return fail(job, "export is not a 1080x1920 H.264 MP4: %s" % s)
    meta = json.loads(Path(str(out) + ".meta.json").read_text(encoding="utf-8"))
    pkg, perrs = postiz_package(job, out, meta)
    (work / "postiz-package.json").write_text(json.dumps(pkg, indent=1), encoding="utf-8")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    patch = {"production_status": "AWAITING_APPROVAL", "export_path": "finished/%s.mp4" % job["job_id"],
             "approval_status": "pending", "postiz_status": "package_valid_unsent" if not perrs else "package_invalid: " + "; ".join(perrs),
             "claimed_by": None, "updated_at": now, "failure": None,
             "edit_result": {"width": s["width"], "height": s["height"], "codec": s["codec_name"], "decodes": True,
                             "duration": meta.get("duration"), "inbox_sidecar": str(out) + ".meta.json"}}
    emit(a, patch)
    return 0


def fail(job, msg):
    return emit(ARGS, {"production_status": "FAILED", "failure": msg, "claimed_by": None,
                       "attempts": int(job.get("attempts") or 0) + 1}) or 1


def emit(a, patch):
    txt = json.dumps(patch, indent=1, ensure_ascii=False)
    if a.out_patch:
        Path(a.out_patch).write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["edit"])
    ap.add_argument("--job", required=True)
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--root", required=True, help="phone folder whose finished/ the approval inbox reads")
    ap.add_argument("--lib")
    ap.add_argument("--out-patch")
    ARGS = ap.parse_args()
    sys.exit(edit(ARGS))

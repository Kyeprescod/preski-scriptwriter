#!/usr/bin/env python3
"""All-night mode: keep the laptop awake and work through your library until morning.

    overnight.py --lib LIB [--hours 8] [--harvest-batch 60] [--max-mb 200] [--tag-batch 60] [--no-harvest]
                 [--sources FOLDER ...]

Loop (each round): scan for new files -> harvest a batch of iCloud-only clips (download, make thumbnails, free the space again)
-> tag a batch with Gemini -> write progress. Stops after --hours, when nothing is left to do, or when Gemini/disk say stop.
Never moves, renames or deletes a photo or video. On Windows it asks the system not to sleep while it runs (closing the lid
can still put the laptop to sleep: set 'When I close the lid: Do nothing' in Power options, or leave it open).
Progress: <lib>/overnight.log and the Library page on the phone.
"""
import argparse, json, os, platform, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def keep_awake(on=True):
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:  # noqa: BLE001
        pass


def log(lib, msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(lib / "overnight.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(args, timeout=None):
    r = subprocess.run([sys.executable] + [str(a) for a in args], capture_output=True, text=True, errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def counts(lib):
    import sqlite3
    try:
        con = sqlite3.connect(lib / "library.db")
        q = lambda s: con.execute(s).fetchone()[0]
        c = {"analysed": q("SELECT COUNT(*) FROM assets WHERE status='analysed'"),
             "waiting": q("SELECT COUNT(*) FROM assets WHERE status='probed'"),
             "cloud": q("SELECT COUNT(*) FROM assets WHERE status='cloud_only'")}
        con.close()
        return c
    except Exception:  # noqa: BLE001
        return {"analysed": 0, "waiting": 0, "cloud": 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib"); ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--harvest-batch", type=int, default=60); ap.add_argument("--max-mb", type=float, default=200)
    ap.add_argument("--tag-batch", type=int, default=60); ap.add_argument("--no-harvest", action="store_true")
    ap.add_argument("--sources", nargs="*", default=[])
    ap.add_argument("--max-rounds", type=int, default=10000)
    a = ap.parse_args()
    lib = Path(a.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library")
    src_file = lib / "source.txt"
    sources = a.sources or ([src_file.read_text(encoding="utf-8").strip()] if src_file.exists() else [])
    end = time.time() + a.hours * 3600
    keep_awake(True)
    start = counts(lib)
    log(lib, "All-night mode started for up to %.1f h. Tagged so far: %d, waiting: %d, iCloud-only: %d" % (a.hours, start["analysed"], start["waiting"], start["cloud"]))
    idle_rounds = 0
    try:
        for rnd in range(1, a.max_rounds + 1):
            if time.time() >= end:
                log(lib, "Time is up.")
                break
            before = counts(lib)
            if sources:
                run([HERE / "clil.py", "--lib", lib, "scan"] + sources)
            if not a.no_harvest and before["cloud"]:
                code, out = run([HERE / "clil.py", "--lib", lib, "harvest", "--type", "video", "--limit", a.harvest_batch,
                                 "--max-mb", a.max_mb], timeout=max(300, int(end - time.time())))
                log(lib, "round %d harvest: %s" % (rnd, (out.strip().splitlines() or ["no output"])[-1][:160]))
            code, out = run([HERE / "gemini_tagger.py", "--lib", lib, "--limit", 20, "--max", a.tag_batch])
            last = (out.strip().splitlines() or ["no output"])[-1][:200]
            log(lib, "round %d tag: %s" % (rnd, last))
            if code != 0 and "No Gemini key" in out:
                log(lib, "No Gemini key on this laptop: stopping. Run  setx GEMINI_API_KEY \"your-key\"  and start again.")
                break
            after = counts(lib)
            progress = after["analysed"] - before["analysed"]
            if progress <= 0 and after["cloud"] >= before["cloud"]:
                idle_rounds += 1
                if idle_rounds >= 2:
                    log(lib, "Nothing more to do right now (%d tagged, %d waiting, %d iCloud-only)." % (after["analysed"], after["waiting"], after["cloud"]))
                    break
                time.sleep(30)
            else:
                idle_rounds = 0
    finally:
        keep_awake(False)
        end_c = counts(lib)
        log(lib, "Finished. Tagged this session: +%d (now %d). Waiting: %d. iCloud-only: %d." %
            (end_c["analysed"] - start["analysed"], end_c["analysed"], end_c["waiting"], end_c["cloud"]))


if __name__ == "__main__":
    main()

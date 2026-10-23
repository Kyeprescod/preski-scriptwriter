#!/usr/bin/env python3
"""Tag clips with Gemini instead of Claude (saves your Claude usage). Reads, never changes, your footage.

    gemini_tagger.py --lib LIB [--limit 30] [--max 200] [--type video] [--model gemini-3.5-flash]
                     [--rpm 8] [--review-sample 0.05] [--dry-run]

For each untagged clip it sends the clip's contact-sheet image (4 frames) to Gemini with the same rubric Claude uses
(references/scoring.md + taxonomy.json), validates the answer, and saves it with `clil annotate`.
Key: environment variable GEMINI_API_KEY, or the line GEMINI_API_KEY=... in ~/.config/watch/.env (the same file the
/watch skill uses). The key is never printed, logged or stored in the library.
A random --review-sample of clips is listed in <lib>/gemini_review.txt so Claude can spot-check a few instead of tagging all.
"""
import argparse, base64, json, os, random, re, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"
CATS = ["training", "cardio", "nutrition", "physique", "talking-head", "lifestyle", "progress", "b-roll", "other"]


def get_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    for p in (Path.home() / ".config" / "watch" / ".env", Path(".env")):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    sys.exit("No Gemini key found. Set it once in PowerShell:  setx GEMINI_API_KEY \"your-key\"  then open a NEW window.")


SCHEMA = {"type": "OBJECT", "required": ["category", "description", "tags", "visual_quality_score", "content_potential_score", "hook_potential_score"],
          "properties": {
              "category": {"type": "STRING", "enum": CATS},
              "subcategory": {"type": "STRING", "nullable": True}, "activity": {"type": "STRING", "nullable": True},
              "exercise": {"type": "STRING", "nullable": True}, "environment": {"type": "STRING", "nullable": True},
              "subject": {"type": "STRING", "nullable": True}, "description": {"type": "STRING"},
              "shot_type": {"type": "STRING", "nullable": True}, "talking_head": {"type": "INTEGER"},
              "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
              "visual_quality_score": {"type": "NUMBER"}, "content_potential_score": {"type": "NUMBER"},
              "hook_potential_score": {"type": "NUMBER"}, "stability_score": {"type": "NUMBER", "nullable": True}}}


def prompt():
    rubric = (REF / "scoring.md").read_text(encoding="utf-8") if (REF / "scoring.md").exists() else ""
    tax = (REF / "taxonomy.json").read_text(encoding="utf-8") if (REF / "taxonomy.json").exists() else "{}"
    return ("You are tagging one clip from Kye's fitness camera roll (Preski Fitness: home training, fat loss, physique; he is a UK coach). "
            "The image is a contact sheet of 4 frames across the clip (a single frame for a photo).\n"
            "Describe ONLY what is visible. If you cannot tell the exercise, leave exercise null and say what you can see. Never guess names, places or speech. "
            "Score honestly: most clips are 3-6, do not default to 7.\n\n"
            "Use this scoring rubric exactly:\n" + rubric[:6000] + "\n\n"
            "Preferred tag vocabulary (use these words when they fit, add others if needed; 3-10 lowercase tags):\n" + tax[:6000] + "\n\n"
            "Add the tags 'showcase' and 'impressive' ONLY if the rubric's showcase rules clearly apply. "
            "talking_head is 1 only if he faces the camera and is speaking. Say 'Kye' only when one person is clearly the main subject. "
            "If any OTHER person is visible (a bystander, a face in the background, a gym member), add the tag 'bystanders'. Return JSON only.")


FALLBACKS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview"]


def call(model, key, b64, base, retries=5):
    try:
        return _call(model, key, b64, base, retries)
    except RuntimeError as e:
        if "HTTP 404" not in str(e):
            raise
        for alt in FALLBACKS:  # the chosen model was retired for new keys: try the current ones
            if alt != model:
                try:
                    r = _call(alt, key, b64, base, retries)
                    print("note: model", model, "is not available; using", alt)
                    os.environ["GEMINI_MODEL"] = alt
                    return r
                except RuntimeError:
                    continue
        raise


def _call(model, key, b64, base, retries=5):
    url = f"{base}/v1beta/models/{model}:generateContent"
    think = True
    for n in range(retries):
        cfg = {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.2}
        if think:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}  # tagging does not need long reasoning: 3x faster and cheaper
        body = {"contents": [{"parts": [{"text": prompt()}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
                "generationConfig": cfg}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:
            if e.code == 400 and think:
                think = False  # this model rejects thinkingConfig: ask again without it
                continue
            if e.code in (429, 500, 502, 503, 504) and n < retries - 1:
                time.sleep(min(60, 4 * 2 ** n))
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, ValueError):
            if n < retries - 1:
                time.sleep(3)
                continue
            raise RuntimeError("Gemini unreachable or returned something unreadable")
    raise RuntimeError("Gemini kept failing")


def num(x):
    try:
        return max(1.0, min(10.0, round(float(x) * 2) / 2))
    except (TypeError, ValueError):
        return None


def clean(asset_id, d):
    out = {"asset_id": asset_id, "category": d.get("category") if d.get("category") in CATS else "other"}
    for k in ("subcategory", "activity", "exercise", "environment", "subject", "shot_type"):
        v = d.get(k)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none", "unknown", "n/a"):
            out[k] = v.strip()[:80]
    out["description"] = re.sub(r"\s+", " ", str(d.get("description", ""))).strip()[:300]
    tags = []
    for t in d.get("tags", []) or []:
        t = re.sub(r"[^a-z0-9 \-]", "", str(t).lower()).strip()
        if t and t not in tags:
            tags.append(t)
    out["tags"] = tags[:12]
    out["talking_head"] = 1 if d.get("talking_head") in (1, True, "1") else 0
    for k in ("visual_quality_score", "content_potential_score", "hook_potential_score", "stability_score"):
        v = num(d.get(k))
        if v is not None:
            out[k] = v
    return out


def clil(lib, *args, stdin=None):
    r = subprocess.run([sys.executable, str(HERE / "clil.py"), "--lib", str(lib)] + [str(a) for a in args],
                       input=stdin, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-300:])
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib"); ap.add_argument("--limit", type=int, default=30); ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--type", default="video", choices=["video", "image"])
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))
    ap.add_argument("--rpm", type=float, default=8.0); ap.add_argument("--review-sample", type=float, default=0.05)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    lib = Path(a.lib or os.environ.get("CLIL_LIB") or Path.home() / "preski-library")
    key = get_key()
    base = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com").rstrip("/")
    done = failed = 0
    reviewed = []
    gap = 60.0 / max(a.rpm, 0.5)
    while done + failed < a.max:
        batch = json.loads(clil(lib, "pending", "--type", a.type, "--limit", min(a.limit, a.max - done - failed)))
        if not batch:
            break
        rows = []
        for item in batch:
            sheet = item.get("contact_sheet")
            if not sheet or not Path(sheet).exists():
                failed += 1
                continue
            if a.dry_run:
                print("would tag", item["asset_id"], item.get("file_name"))
                done += 1
                continue
            try:
                res = call(a.model, key, base64.b64encode(Path(sheet).read_bytes()).decode(), base)
                rows.append(clean(item["asset_id"], res))
                done += 1
                if random.random() < a.review_sample:
                    reviewed.append(item["asset_id"])
            except RuntimeError as e:
                print("skip", item["asset_id"], "->", e)
                failed += 1
            time.sleep(gap)
        if rows:
            out = clil(lib, "annotate", "-", stdin="\n".join(json.dumps(r) for r in rows))
            print("saved", len(rows), "tags:", out.strip()[:120])
        if a.dry_run or not rows:
            break
    if reviewed:
        with open(lib / "gemini_review.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(str(i) for i in reviewed) + "\n")
    print(f"Gemini tagged {done}, skipped {failed}. Spot-check list: {lib / 'gemini_review.txt'}")


if __name__ == "__main__":
    main()

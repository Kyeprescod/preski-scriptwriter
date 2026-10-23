"""Preski Fitness daily POST renderer v2 (carousel + story + fast-cut reel + phone page).

python render_post.py post.json [--no-qc]

Same post.json as v1 (see the TYPES below), plus these optional extras:
  slides:  "focus": "50% 20%" (where to anchor a photo)   point/text/list may now carry a "photo" for a split layout
           list: "highlight": "last" turns the last row into the red answer row
           stat  {"type":"stat","eyebrow":s,"big":"500 > 150","label":s,"note":s,"photo":f(optional)}
  reel:    scenes may add "focus": "upper"|"mid"|"wide" for photo scenes. The renderer cuts every scene into 1.2-2.2 s shots
           (a clip scene becomes several cuts from different parts of the clip; a photo scene becomes quick punch-ins).
  schedule: [["12:30","Reel to TikTok, Instagram, YouTube Shorts, Snapchat"], ...] shown on the page (optional)

Slide TYPES (all 1080x1350):
 cover   {"type":"cover","photo":f,"eyebrow":s,"title":[a,b],"sub":s}
 compare {"type":"compare","title":[a,b],"left":{"photo":f,"label":s},"right":{"photo":f,"label":s},"note":s,"badge":s(optional)}
 point   {"type":"point","n":"01","title":[a,b],"body":s,"photo":f(optional)}
 list    {"type":"list","title":[a,b],"rows":[[left,right],...],"note":s,"photo":f(optional)}
 text    {"type":"text","eyebrow":s,"title":[a,b],"body":s,"photo":f(optional)}
 stat    see above
 cta     {"type":"cta","photo":f,"title":[a,b]}      (uses post keyword/offer)
Titles: [first line, second line in red]; either may be "".

Photos are only ever SHARPENED and contrast-normalised on render copies (_enh/); originals are never touched and bodies
are never retouched. Writes daily/<date>/slide-NN.jpg, story.jpg, reel.mp4, reel-poster.jpg, manifest.json, index.html.
The phone save buttons need the page's `downloads` capability (declared once; republish without `capabilities` to keep it).
"""
import html, json, os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
PH = HERE / "photos"
ENH = HERE / "_enh"
FONTS = HERE / "fonts"
E = html.escape


# ---------------------------------------------------------------- photos
def enhance(name):
    """Render copy: upscale small photos (LANCZOS), gentle autocontrast and unsharp. Originals untouched."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    src, dst = PH / name, ENH / name
    ENH.mkdir(exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = im.size
    scale = min(2.0, max(1.0, 2200 / max(w, h)))
    if scale > 1.02:
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    im = ImageOps.autocontrast(im, cutoff=0.3)
    im = ImageEnhance.Contrast(im).enhance(1.04)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=70, threshold=3))
    im.save(dst, quality=92, subsampling=0)
    return dst


def u(f):
    return enhance(f).as_uri()


# ---------------------------------------------------------------- slide css
def font_faces():
    out = []
    for w in (700, 800, 900):
        p = FONTS / f"BigShouldersDisplay-{w}.ttf"
        if p.exists():
            out.append(f"@font-face{{font-family:'BSD';font-weight:{w};src:url({p.as_uri()})}}")
    for w in (400, 600, 700):
        p = FONTS / f"Figtree-{w}.ttf"
        if p.exists():
            out.append(f"@font-face{{font-family:'FIG';font-weight:{w};src:url({p.as_uri()})}}")
    return "".join(out)


CSS = font_faces() + """
:root{--ink:#071A3D;--deep:#040E22;--red:#E8323C;--chalk:#EDF1F7;--mut:#9AA8C4;
 --H:'BSD','Inter Display','Inter','Liberation Sans',sans-serif;--B:'FIG','Inter','Liberation Sans',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--B);background:var(--deep);color:#fff}
.s{position:relative;overflow:hidden;width:1080px;height:1350px;background:var(--ink);display:flex;flex-direction:column}
.s.deep{background:var(--deep)}.s.chalk{background:var(--chalk);color:#0A1631}
h1{display:block;font-family:var(--H);font-weight:900;text-transform:uppercase;letter-spacing:.004em;line-height:.88}
h1 .r,.r{color:var(--red)}
.hl{display:block;white-space:nowrap}
.brand{font-family:var(--H);font-weight:900;font-size:36px;letter-spacing:.03em;line-height:1}.brand span{color:var(--red)}
.top{text-shadow:0 2px 14px rgba(4,14,34,.8);position:absolute;left:72px;right:72px;top:58px;display:flex;justify-content:space-between;align-items:center;z-index:5}
.prog{display:flex;gap:8px}.prog i{display:block;width:34px;height:6px;border-radius:3px;background:rgba(255,255,255,.28)}
.prog i.on{background:var(--red)}.chalk .prog i{background:rgba(10,22,49,.18)}.chalk .prog i.on{background:var(--red)}
.lab{display:flex;align-items:center;gap:16px;font-family:var(--B);font-weight:700;font-size:32px;color:#fff;text-shadow:0 2px 14px rgba(4,14,34,.85)}
.lab:before{content:"";display:block;width:56px;height:5px;background:var(--red);border-radius:3px}
.body{font-family:var(--B);font-size:42px;line-height:1.38;color:#DCE3F0;font-weight:400}
.chalk .body{color:#2F3E5C}
.bd{overflow:hidden}
.handle{position:absolute;left:72px;bottom:46px;font-weight:600;font-size:24px;letter-spacing:.06em;color:var(--mut);z-index:5}
.chalk .handle{color:#52627F}
.ph{background-size:cover;background-position:50% 22%;position:relative;overflow:hidden}
.chip{position:absolute;left:20px;bottom:20px;font-weight:700;font-size:28px;padding:10px 18px;border-radius:8px;background:var(--deep);color:#fff}
.chip.hot{background:var(--red)}
.ghost{position:absolute;right:-30px;top:120px;font-family:var(--H);font-weight:900;font-size:760px;line-height:.8;color:transparent;-webkit-text-stroke:3px rgba(232,50,60,.32)}
.num{font-family:var(--H);font-weight:900;font-size:170px;line-height:.8;color:var(--red)}
.rows{display:flex;flex-direction:column;border-top:3px solid #0A1631}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:30px;padding:30px 4px;border-bottom:2px solid rgba(10,22,49,.16);font-size:44px;line-height:1.2;font-weight:600}
.row b{font-family:var(--H);font-weight:900;font-size:60px;color:var(--red);white-space:nowrap}
.row.ans{background:var(--red);color:#fff;border-radius:12px;border:0;padding:30px 28px;margin-top:14px}.row.ans b{color:#fff}
.cta{background:var(--red);border-radius:18px;padding:30px 38px;display:flex;justify-content:space-between;align-items:center;gap:20px;color:#fff;z-index:4;position:relative}
.cta .t{font-weight:700;font-size:40px;line-height:1.15}.cta .t small{display:block;font-weight:400;font-size:30px;margin-top:4px}
.cta .k{font-family:var(--H);font-weight:900;font-size:84px;line-height:1;background:#fff;color:var(--red);padding:6px 26px 4px;border-radius:10px}
.swipe{display:inline-flex;align-items:center;gap:14px;font-weight:700;font-size:28px;background:#fff;color:var(--deep);padding:14px 26px;border-radius:999px}
.swipe:after{content:"";width:18px;height:18px;border-top:4px solid var(--red);border-right:4px solid var(--red);transform:rotate(45deg);margin-left:2px}
.big{font-family:var(--H);font-weight:900;font-size:300px;line-height:.82;color:#fff;letter-spacing:-.01em}
"""


def T(t, size, extra=""):
    a, b = (t + ["", ""])[:2] if isinstance(t, list) else (t, "")
    out = ""
    if a:
        out += f'<span class=hl>{E(a)}</span>'
    if b:
        out += f'<span class="hl r">{E(b)}</span>'
    return f'<h1 class=fith style="font-size:{size}px;{extra}">{out}</h1>'


def para(s):
    return "<br>".join(E(x) for x in (s or "").split("\n"))


def top(i, n, brand=True):
    ticks = "".join(f'<i class="{"on" if k < i else ""}"></i>' for k in range(n)) if n > 1 else ""
    return f'<div class=top>{"<div class=brand>PRESKI<span>FITNESS</span></div>" if brand else "<span></span>"}<div class=prog>{ticks}</div></div>'


def handle():
    return '<div class=handle>@preski_fitness</div>'


def photo_div(f, focus="50% 22%", style="", inner=""):
    return f'<div class=ph style="background-image:url({u(f)});background-position:{focus};{style}">{inner}</div>'


AUTO_FOCUS = ["50% 20%", "50% 8%", "50% 30%", "50% 14%"]


def autophoto(sl, post, i):
    """Give point/text/list slides without a photo one from the post's own pool (a different crop each time),
    so the carousel never has a slide that is only text on navy. Set "nophoto": true on a slide to opt out."""
    if sl.get("photo") or sl.get("nophoto") or sl["type"] not in ("point", "text"):
        return sl
    pool = [post.get("story", {}).get("photo")] + [x.get("photo") for x in post["slides"] if x["type"] in ("cover", "cta") and x.get("photo")] \
        + [(x.get("right") or {}).get("photo") for x in post["slides"] if x["type"] == "compare"]
    pool = [x for x in pool if x]
    if not pool:
        return sl
    k = sum(1 for y in post["slides"][:i - 1] if y["type"] in ("point", "text") and not y.get("photo"))
    return dict(sl, photo=pool[k % len(pool)], focus=sl.get("focus") or AUTO_FOCUS[k % len(AUTO_FOCUS)])


def slide(sl, i, n, post):
    sl = autophoto(sl, post, i)
    t = sl["type"]
    foc = sl.get("focus", "50% 22%")
    if t == "cover":
        return (f'<div class="s deep"><div style="position:absolute;inset:0;background:url({u(sl["photo"])}) {foc}/cover"></div>'
                '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(4,14,34,.6) 0%,rgba(4,14,34,0) 20%,rgba(4,14,34,0) 38%,rgba(4,14,34,.92) 64%,#040E22 100%)"></div>'
                f'{top(i, n)}'
                '<div style="position:absolute;left:72px;right:72px;bottom:104px;display:flex;flex-direction:column;gap:28px">'
                f'<div class=lab>{E(sl.get("eyebrow", ""))}</div>{T(sl["title"], 190)}'
                + (f'<p class=body style="font-size:40px;max-width:820px">{para(sl.get("sub"))}</p>' if sl.get("sub") else "")
                + '<div><span class=swipe>Swipe</span></div></div></div>')
    if t == "compare":
        L, R = sl["left"], sl["right"]
        badge = (f'<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:var(--red);color:#fff;font-family:var(--H);font-weight:900;font-size:54px;padding:10px 22px;border-radius:10px;z-index:3;white-space:nowrap">{E(sl["badge"])}</div>' if sl.get("badge") else "")
        return (f'<div class="s deep" style="padding:150px 72px 110px;gap:32px">{top(i, n)}{T(sl["title"], 112)}'
                '<div style="position:relative;display:grid;grid-template-columns:1fr 1fr;gap:12px;flex:1;min-height:0">'
                f'{photo_div(L["photo"], L.get("focus", "50% 22%"), "border-radius:20px", f"<span class=chip>{E(L["label"])}</span>")}'
                f'{photo_div(R["photo"], R.get("focus", "50% 22%"), "border-radius:20px", f"<span class=\'chip hot\'>{E(R["label"])}</span>")}{badge}</div>'
                + (f'<p class="body bd" style="font-size:34px;max-height:150px">{para(sl.get("note"))}</p>' if sl.get("note") else "")
                + handle() + '</div>')
    if t in ("point", "text"):
        num = sl.get("n", "")
        lab = sl.get("eyebrow", "")
        if sl.get("photo"):
            return (f'<div class="s deep">{top(i, n)}'
                    f'<div style="position:relative;height:560px;flex:none">{photo_div(sl["photo"], foc, "position:absolute;inset:0")}'
                    '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(4,14,34,.55) 0%,rgba(4,14,34,0) 24%,rgba(4,14,34,0) 52%,#040E22 100%)"></div></div>'
                    f'<div style="padding:0 72px 100px;display:flex;flex-direction:column;gap:26px;margin-top:-56px;position:relative;flex:1;min-height:0">'
                    + (f'<div class=num>{E(num)}</div>' if num else (f'<div class=lab>{E(lab)}</div>' if lab else ''))
                    + f'{T(sl["title"], 104)}<p class="body bd fitb" style="flex:1;min-height:0">{para(sl.get("body"))}</p></div>' + handle() + '</div>')
        return (f'<div class="s deep" style="padding:170px 72px 110px;gap:36px;justify-content:center">{top(i, n)}'
                + (f'<div class=ghost>{E(num)}</div>' if num else '')
                + (f'<div class=lab>{E(lab)}</div>' if lab else (f'<div class=num style="font-size:150px">{E(num)}</div>' if num else ''))
                + f'{T(sl["title"], 140)}<p class="body bd fitb" style="font-size:46px;max-width:880px;flex:1;min-height:0">{para(sl.get("body"))}</p>' + handle() + '</div>')
    if t == "list":
        rows = sl["rows"]
        hl = sl.get("highlight") == "last"
        rh = "".join(f'<div class="row{" ans" if (hl and k == len(rows) - 1) else ""}"><span>{E(a)}</span><b>{E(b)}</b></div>' for k, (a, b) in enumerate(rows))
        ph = (f'<div style="height:300px;flex:none;border-radius:20px;overflow:hidden">{photo_div(sl["photo"], foc, "position:absolute;inset:0;border-radius:20px")}</div>' if sl.get("photo") else "")
        return (f'<div class="s chalk" style="padding:150px 72px 110px;gap:30px">{top(i, n)}{T(sl["title"], 124)}{ph}<div class=rows>{rh}</div>'
                + (f'<p class="body bd fitb" style="font-size:34px;flex:1;min-height:0">{para(sl.get("note"))}</p>' if sl.get("note") else "")
                + handle() + '</div>')
    if t == "stat":
        bg = (f'<div style="position:absolute;inset:0;background:url({u(sl["photo"])}) {foc}/cover;opacity:.28"></div>' if sl.get("photo") else "")
        return (f'<div class="s deep" style="padding:170px 72px 110px;gap:30px;justify-content:center">{bg}{top(i, n)}'
                f'<div class=lab style="position:relative">{E(sl.get("eyebrow", ""))}</div><div class=big style="position:relative">{E(sl["big"])}</div>'
                f'<h1 style="font-size:96px;position:relative">{E(sl.get("label", ""))}</h1>'
                + (f'<p class="body bd fitb" style="position:relative;flex:1;min-height:0">{para(sl.get("note"))}</p>' if sl.get("note") else "") + handle() + '</div>')
    if t == "cta":
        return (f'<div class="s deep" style="padding:150px 72px 110px;gap:32px">{top(i, n)}'
                '<div style="position:relative;flex:1;min-height:0">'
                f'{photo_div(sl["photo"], foc, "position:absolute;inset:0;border-radius:20px")}'
                '<div style="position:absolute;inset:0;border-radius:20px;background:linear-gradient(180deg,rgba(4,14,34,.1) 40%,rgba(4,14,34,.85) 100%)"></div>'
                f'<div style="position:absolute;left:36px;bottom:30px;right:36px">{T(sl["title"], 128)}</div></div>'
                f'<div class=cta><div class=t>Comment<small>for {E(post["offer"])}</small></div><div class=k>{E(post["keyword"])}</div></div>'
                '<div style="text-align:center;font-size:30px;color:var(--mut)">Follow for more. Lives most nights.</div>' + handle() + '</div>')
    raise ValueError("unknown slide type " + t)


def story(st, post):
    return ('<div class="s deep" style="width:1080px;height:1920px">'
            f'<div style="position:absolute;inset:0;background:url({u(st["photo"])}) 50% 20%/cover"></div>'
            '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(4,14,34,.6) 0%,rgba(4,14,34,0) 20%,rgba(4,14,34,0) 36%,rgba(4,14,34,.97) 60%,#040E22 100%)"></div>'
            '<div class=top style="top:96px"><div class=brand style="font-size:44px">PRESKI<span>FITNESS</span></div></div>'
            '<div style="position:absolute;left:72px;right:72px;bottom:170px;display:flex;flex-direction:column;gap:34px">'
            f'<div class=lab>{E(st.get("eyebrow", ""))}</div>{T(st["title"], 200)}'
            f'<p class=body style="font-size:44px">{para(st.get("body"))}</p>'
            f'<div class=cta><div class=t>Comment<small>for {E(post["offer"])}</small></div><div class=k>{E(post["keyword"])}</div></div></div></div>')


FIT_JS = """() => {
 const shrink = (el, test, min) => { let s = parseFloat(getComputedStyle(el).fontSize); let g = 0;
   while (test(el) && s > min && g++ < 60) { s -= 2; el.style.fontSize = s + 'px'; } };
 document.querySelectorAll('.fitb').forEach(el => shrink(el, e => e.scrollHeight > e.clientHeight + 2, 26));
 document.querySelectorAll('.fith').forEach(el => shrink(el, e => e.scrollWidth > e.clientWidth + 2, 60));
}"""


# ---------------------------------------------------------------- reel
def vlen(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 6.0


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed: " + " ".join(map(str, cmd[:8])) + "\n" + r.stderr[-1500:])


REGIONS = {"wide": (1.00, 1.09, 0.5, 0.35), "upper": (1.22, 1.38, 0.5, 0.12), "mid": (1.28, 1.46, 0.5, 0.52)}
GRADE = "eq=contrast=1.06:saturation=1.08:brightness=0.01"


def plan_shots(r):
    """Cut every scene into 1.2-2.2 s shots. Returns (shots, stills_seconds, video_seconds)."""
    shots, order = [], ["wide", "upper", "mid"]
    stills = video = 0.0
    for k, sc in enumerate(r["scenes"]):
        dur = float(sc.get("dur", 3))
        if sc.get("clip"):
            src = HERE / "clips" / sc["clip"]
            L = vlen(src)
            n = max(1, round(dur / 1.9))
            seg = dur / n
            start0 = float(sc.get("start", 0))
            span = max(0.0, L - seg - start0)
            for j in range(n):
                st = start0 + (span * j / (n - 1) if n > 1 else 0)
                shots.append({"scene": k, "kind": "clip", "src": src, "start": round(st, 2), "dur": seg,
                              "punch": (j % 2 == 1)})
            video += dur
        else:
            n = max(2, round(dur / 1.5))
            seg = dur / n
            first = {"upper": 1, "mid": 2}.get(sc.get("focus"), 0)
            for j in range(n):
                shots.append({"scene": k, "kind": "photo", "src": enhance(sc["photo"]), "region": order[(first + j) % 3], "dur": seg})
            stills += dur
    return shots, stills, video


def render_shot(sh_, out, fps=30):
    d = sh_["dur"]
    frames = max(2, round(d * fps))
    cover = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    enc = ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "19", "-r", str(fps)]
    if sh_["kind"] == "clip":
        punch = ",crop=iw/1.12:ih/1.12,scale=1080:1920" if sh_["punch"] else ""
        sh(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-ss", str(sh_["start"]), "-i", str(sh_["src"]), "-t", f"{d:.3f}",
            "-vf", f"{cover}{punch},{GRADE},fps={fps}"] + enc + [str(out)])
    else:
        z0, z1, ax, ay = REGIONS[sh_["region"]]
        zp = (f"zoompan=z='{z0}+({z1}-{z0})*on/{frames}':x='(iw-iw/zoom)*{ax}':y='(ih-ih/zoom)*{ay}':d={frames}:s=1080x1920:fps={fps}")
        sh(["ffmpeg", "-v", "error", "-y", "-i", str(sh_["src"]), "-vf",
            f"scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,{zp},setsar=1,{GRADE}",
            "-frames:v", str(frames)] + enc + [str(out)])


def timed_script(reel):
    lines, t = [], 0.0
    ts = lambda x: f"{int(x)//60}:{int(x)%60:02d}"
    for sc in reel.get("scenes", []):
        d = float(sc.get("dur", 3))
        if sc.get("vo"):
            lines.append(f"[{ts(t)}–{ts(t+d)}] {sc['vo']}")
        t += d
    e = reel.get("end", {})
    d = float(e.get("dur", 3.0))
    if e.get("vo"):
        lines.append(f"[{ts(t)}–{ts(t+d)}] {e['vo']}")
    t += d
    if not lines:
        return reel.get("voiceover", "")
    words = sum(len(l.split("] ", 1)[1].split()) for l in lines)
    return "\n".join(lines) + f"\n\n(Total {ts(t)} · {words} words · speak at a calm, steady pace)"


def clean_cap(s):
    return "".join(ch for ch in (s or "") if ord(ch) < 0x2190).replace("%", " percent").strip()


def make_reel(post, out_dir, pg):
    """Builds reel.mp4 (1080x1920, 30fps, silent) + reel-poster.jpg. Caption/hook layers are drawn in Chromium so the
    brand fonts match the slides exactly, then overlaid with ffmpeg."""
    r = post["reel"]
    tmp = out_dir / "_reel"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    shots, stills, video = plan_shots(r)
    total_scenes = stills + video
    if total_scenes and stills / total_scenes > 0.4:
        print(f"REEL WARNING: {stills:.0f}s of {total_scenes:.0f}s is still photos; use more real video clips from clips/ if any fit")
    parts = []
    for n_, s_ in enumerate(shots):
        o = tmp / f"s{n_:03d}.mp4"
        render_shot(s_, o)
        parts.append(o)
    # end card (still, short, with CTA drawn in)
    e = r["end"]
    ed = min(3.2, float(e.get("dur", 3.0)))
    endhtml = ('<div class="s deep" style="width:1080px;height:1920px">'
               f'<div style="position:absolute;inset:0;background:url({u(e["photo"])}) 50% 18%/cover"></div>'
               '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(4,14,34,0) 30%,rgba(4,14,34,.94) 62%,#040E22 100%)"></div>'
               '<div style="position:absolute;left:72px;right:72px;bottom:210px;display:flex;flex-direction:column;gap:36px">'
               f'<h1 style="font-size:170px">{E(clean_cap(e.get("line", "Follow for more")))}</h1>'
               f'<div class=cta><div class=t>Comment<small>for {E(post["offer"])}</small></div><div class=k>{E(post["keyword"])}</div></div></div></div>')
    shot_png(pg, endhtml, 1080, 1920, tmp / "end.png", jpeg=False)
    end = tmp / "end.mp4"
    sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", f"{ed:.2f}", "-i", str(tmp / "end.png"), "-vf",
        "zoompan=z='1+0.04*on/90':d=90:s=1080x1920:fps=30,setsar=1", "-frames:v", str(round(ed * 30)),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "19", "-r", "30", str(end)])
    parts.append(end)
    lst = tmp / "l.txt"
    lst.write_text("".join(f"file '{x}'\n" for x in parts))
    base = tmp / "base.mp4"
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
    total = sum(s_["dur"] for s_ in shots) + ed
    # caption layers
    layers, t0 = [], 0.0
    for k, sc in enumerate(r["scenes"]):
        d = float(sc.get("dur", 3))
        cap = clean_cap(sc.get("caption", ""))
        if cap:
            p = tmp / f"c{k}.png"
            shot_png(pg, '<div style="display:inline-block;background:var(--red);color:#fff;font-family:var(--H);font-weight:900;font-size:104px;line-height:1;'
                         f'text-transform:uppercase;padding:18px 34px 12px;border-radius:12px;max-width:940px">{E(cap)}</div>', 1000, 300, p, jpeg=False, fit=True)
            layers.append((p, t0 + 0.08, t0 + d - 0.05, "bottom"))
        t0 += d
    hook = clean_cap(r.get("hook", ""))
    if hook:
        p = tmp / "hook.png"
        shot_png(pg, f'<div style="color:#fff;font-family:var(--H);font-weight:900;font-size:150px;line-height:.92;text-transform:uppercase;text-align:center;'
                     f'text-shadow:0 6px 0 rgba(4,14,34,.85),0 0 28px rgba(4,14,34,.7);max-width:960px">{E(hook)}</div>', 1000, 640, p, jpeg=False, fit=True)
        layers.insert(0, (p, 0.0, float(r.get("hook_secs", 3)), "top"))
    final = out_dir / "reel.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(base)]
    chain, last = [], "0:v"
    for n_, (p, a, b, pos) in enumerate(layers, 1):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{b + 1:.2f}", "-i", str(p)]
        y = "230" if pos == "top" else "1190"
        chain.append(f"[{n_}:v]format=rgba,fade=t=in:st=0:d=0.14:alpha=1,setpts=PTS+{a:.3f}/TB[o{n_}]")
        chain.append(f"[{last}][o{n_}]overlay=x=(W-w)/2:y={y}:enable='between(t,{a:.3f},{b:.3f})'[v{n_}]")
        last = f"v{n_}"
    chain.append(f"[{last}]drawbox=x=0:y=ih-12:w='iw*t/{total:.3f}':h=12:color=0xE8323C@1:t=fill[vout]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[vout]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "25", "-maxrate", "5M", "-bufsize", "10M",
            "-preset", "medium", "-movflags", "+faststart", "-t", f"{total:.3f}", str(final)]
    sh(cmd)
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "0.9", "-i", str(final), "-frames:v", "1", "-q:v", "3", str(out_dir / "reel-poster.jpg")])
    shutil.rmtree(tmp, ignore_errors=True)
    return final


# ---------------------------------------------------------------- shooting
def shot_png(pg, inner, w, h, path, jpeg=True, fit=False):
    tmp = HERE / "_r.html"
    bg = "" if jpeg else "html,body{background:transparent}"
    tmp.write_text(f'<html><head><meta charset=utf-8><style>{CSS}{bg}</style></head><body>{inner}</body></html>', encoding="utf-8")
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(tmp.as_uri())
    pg.wait_for_timeout(200)
    pg.evaluate(FIT_JS)
    if jpeg:
        pg.screenshot(path=str(path), type="jpeg", quality=92, clip={"x": 0, "y": 0, "width": w, "height": h})
    elif fit:  # transparent, trimmed to the element
        el = pg.query_selector("body > div")
        box = el.bounding_box()
        pg.screenshot(path=str(path), type="png", omit_background=True,
                      clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
    else:
        pg.screenshot(path=str(path), type="png", clip={"x": 0, "y": 0, "width": w, "height": h})
    tmp.unlink()


# ---------------------------------------------------------------- phone page
def page_font_faces():
    """Same faces as the slides, but with URLs relative to the published page (fonts/ folder next to index.html)."""
    out = []
    for fam, ws, pre in (("BSD", (700, 800, 900), "BigShouldersDisplay"), ("FIG", (400, 600, 700), "Figtree")):
        for w in ws:
            out.append(f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(fonts/{pre}-{w}.ttf)}}")
    return "".join(out)


PAGE_CSS = page_font_faces() + """
:root{--ink:#071A3D;--deep:#040E22;--card:#0C2552;--red:#E8323C;--mut:#9AA8C4;--line:rgba(255,255,255,.12);color-scheme:dark;
 --H:'BSD','Inter Display','Inter',system-ui,sans-serif;--B:'FIG','Inter',system-ui,-apple-system,'Segoe UI',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--deep);color:#fff;font:16px/1.5 var(--B)}
.wrap{max-width:560px;margin:0 auto;padding:0 0 80px}
header{padding:18px 18px 6px;display:flex;justify-content:space-between;align-items:baseline}
.brand{font:900 24px var(--H);letter-spacing:.03em}.brand span{color:var(--red)}.date{color:var(--mut);font-size:14px}
h1{font:900 clamp(40px,11vw,58px)/.9 var(--H);text-transform:uppercase;margin:6px 18px 4px}
.hookline{margin:0 18px 16px;color:#DCE3F0;font-size:18px}
.reelbox{position:relative;margin:0 0 6px;background:#000}
.reelbox video{display:block;width:100%;aspect-ratio:9/16;max-height:78vh;object-fit:cover;background:#000}
.bar{display:flex;gap:10px;padding:12px 18px}
.btn{flex:1;min-height:52px;border:0;border-radius:10px;background:var(--red);color:#fff;font:700 16px var(--B);cursor:pointer}
.btn.alt{background:transparent;border:2px solid var(--line);color:#fff}
.sec{padding:22px 18px 0}
.sec h2{font:900 30px/1 var(--H);text-transform:uppercase;margin:0 0 12px}
.car{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;padding:0 18px 4px;margin:0 -18px;-webkit-overflow-scrolling:touch}
.car a{flex:0 0 86%;scroll-snap-align:center}.car img{width:100%;display:block;border-radius:14px}
.dots{display:flex;gap:6px;justify-content:center;margin:12px 0 0}.dots i{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.25)}.dots i.on{background:var(--red)}
.story{width:62%;display:block;margin:0 auto;border-radius:14px}
.box{background:var(--card);border-radius:12px;padding:14px 16px}
.box pre{white-space:pre-wrap;font:16px/1.55 var(--B);margin:0 0 12px}
.tl{list-style:none;margin:0;padding:0}.tl li{display:flex;gap:14px;padding:12px 0;border-bottom:1px solid var(--line)}
.tl b{font:900 26px/1 var(--H);color:var(--red);min-width:62px}
.mut{color:var(--mut);font-size:14px}
details{background:var(--card);border-radius:12px;padding:12px 16px;margin-top:10px}summary{font-weight:700;cursor:pointer}
.arch{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.arch img{width:100%;border-radius:10px;display:block}
.arch figcaption{font-size:12px;color:var(--mut);margin-top:4px;line-height:1.3}.arch figure{margin:0}
.save{background:var(--card);border-radius:12px;padding:14px 16px;margin:14px 18px 0}
.save .dls{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
button.dl{background:transparent;border:1px solid var(--line);color:#fff;border-radius:8px;font:600 13px var(--B);padding:8px 10px}
"""

DEFAULT_SCHEDULE = [["12:30", "Reel to TikTok, Instagram Reels, YouTube Shorts and Snapchat"], ["19:15", "Carousel on Instagram, Story straight after"], ["20:00", "TikTok live"]]


def save_box(t):
    sl = t["slides"]
    files = [[f"{t['date']}-{k+1:02d}-slide.jpg", f, f"Slide {k+1}"] for k, f in enumerate(sl)] + [[f"{t['date']}-story.jpg", t["story"], "Story"]] \
        + ([[f"{t['date']}-reel.mp4", t["reel"], "Reel"]] if t.get("reel") else [])
    btns = "".join(f'<button type=button class=dl data-i="{i}">{E(lab)}</button>' for i, (_, _, lab) in enumerate(files))
    return ('<div class=save id=savebox hidden><b>Save to your phone</b><div class=bar style="padding:10px 0 0"><button type=button class=btn id=saveall>Save all in posting order</button></div>'
            f'<div class=dls>{btns}</div><p class=mut id=shmsg style="margin:10px 0 0">Each save asks you to confirm. In the Claude app it opens the share sheet: Save Image / Save Video, or pick Instagram.</p>'
            f'<script>var FILES={json.dumps(files)};'
            '(async function(){if(typeof claude==="undefined")return;var dl=await claude.use("downloads");if(!dl)return;var box=document.getElementById("savebox"),m=document.getElementById("shmsg");box.hidden=false;'
            'async function one(i){var f=FILES[i];var r=await fetch(f[1]);var bl=await r.blob();await dl.save({filename:f[0],data:bl});}'
            'function err(e){var c=e&&e.code;if(c==="declined"){m.textContent="Skipped.";return}if(c==="rate_limited"){m.textContent="One at a time: try again in a moment.";return}'
            'if(c==="unavailable"||c==="not_granted"){m.textContent="Saving isn\'t available in this view. Press and hold an image to save it instead.";return}m.textContent="Couldn\'t save ("+(c||"error")+").";}'
            'document.querySelectorAll("button.dl").forEach(function(b){b.addEventListener("click",async function(){try{await one(+b.dataset.i);b.textContent="Saved ✓ "+FILES[+b.dataset.i][2];m.textContent="Saved."}catch(e){err(e)}})});'
            'document.getElementById("saveall").addEventListener("click",async function(){for(var i=0;i<FILES.length;i++){try{m.textContent="Saving "+FILES[i][2]+"...";await one(i)}catch(e){err(e);if(e&&e.code!=="declined")return}}m.textContent="All done. Post the slides in order 1 to "+(FILES.length-2)+".";});'
            '})();</script></div>')


def page(manifest):
    t = manifest[0]
    n = len(t["slides"])
    car = "".join(f'<a href="{s}" target="_blank" rel="noopener"><img src="{s}" alt="Slide {k+1}"{" loading=lazy" if k > 1 else ""}></a>' for k, s in enumerate(t["slides"]))
    dots = "".join(f'<i class="{"on" if k == 0 else ""}"></i>' for k in range(n))
    sched = "".join(f"<li><b>{E(a)}</b><span>{E(b)}</span></li>" for a, b in (t.get("schedule") or DEFAULT_SCHEDULE))
    arch = "".join(f'<figure><a href="{m["slides"][0]}" target="_blank" rel="noopener"><img src="{m["slides"][0]}" alt="{E(m["topic"])}" loading=lazy></a>'
                   f'<figcaption>{m["date"][5:]} · {E(m["topic"])}</figcaption></figure>' for m in manifest[1:13])
    poster = f' poster="{t["reel_poster"]}"' if t.get("reel_poster") else ""
    reel = (f'<div class=reelbox><video src="{t["reel"]}"{poster} controls playsinline muted loop preload=metadata></video></div>'
            '<div class=bar><button class="btn alt" id=cvo type=button>Copy voiceover script</button></div>' if t.get("reel") else "")
    vo = (f'<details><summary>Voiceover script (exact words)</summary><pre id=vo style="white-space:pre-wrap;font:15px/1.55 var(--B);margin:10px 0 0">{E(t.get("voiceover", ""))}</pre>'
          f'<p class=mut>Sound: {E(t.get("sound", ""))}. The reel is silent: record this over it in CapCut and add a sound.</p></details>' if t.get("voiceover") else "")
    js = ('<script>var car=document.querySelector(".car"),dots=document.querySelectorAll(".dots i");'
          'if(car){car.addEventListener("scroll",function(){var k=Math.round(car.scrollLeft/(car.scrollWidth/dots.length));dots.forEach(function(d,i){d.className=i===k?"on":""})},{passive:true})}'
          'function cp(id,btn){var t=document.getElementById(id).textContent,o=btn.textContent;'
          'function ok(){btn.textContent="Copied";setTimeout(function(){btn.textContent=o},1300)}'
          'if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,fb)}else{fb()}'
          'function fb(){var a=document.createElement("textarea");a.value=t;a.style.position="fixed";a.style.opacity=0;document.body.appendChild(a);a.select();try{document.execCommand("copy");ok()}catch(e){}document.body.removeChild(a)}}'
          'document.getElementById("copycap").onclick=function(){cp("cap",this)};'
          'var c=document.getElementById("cvo");if(c)c.onclick=function(){cp("vo",this)};</script>')
    return (f'<title>Preski Daily Post</title><style>{PAGE_CSS}</style><div class=wrap>'
            f'<header><div class=brand>PRESKI<span>FITNESS</span></div><div class=date>{t["date"]}</div></header>'
            f'<h1>{E(t["topic"])}</h1><p class=hookline>{E(t["hook"])}</p>' + reel + save_box(t) +
            f'<div class=sec><h2>Carousel · {n} slides</h2><div class=car>{car}</div><div class=dots>{dots}</div></div>'
            f'<div class=sec><h2>Story</h2><a href="{t["story"]}" target="_blank" rel="noopener"><img class=story src="{t["story"]}" alt="Story"></a></div>'
            f'<div class=sec><h2>Caption</h2><div class=box><pre id=cap>{E(t["caption"])}</pre><button class=btn id=copycap type=button style="width:100%">Copy caption</button>'
            f'<p class=mut style="margin:10px 0 0">Comment keyword: {E(t["keyword"])}</p></div></div>'
            f'<div class=sec><h2>Today</h2><ul class=tl>{sched}</ul>{vo}</div>'
            + (f'<div class=sec><h2>Earlier</h2><div class=arch>{arch}</div></div>' if arch else '')
            + '</div>' + js)


# ---------------------------------------------------------------- qc + main
def used_photos(post):
    out = []
    def add(f):
        if f and f not in out:
            out.append(f)
    for sl in post.get("slides", []):
        add(sl.get("photo")); add((sl.get("left") or {}).get("photo")); add((sl.get("right") or {}).get("photo"))
    add((post.get("story") or {}).get("photo"))
    r = post.get("reel") or {}
    for sc in r.get("scenes", []):
        add(sc.get("photo"))
    add((r.get("end") or {}).get("photo"))
    return out


HARD = {"lowres", "soft", "dark", "washed_out", "travel_only", "lowres_tag", "missing"}


def photo_qc(post, manifest):
    qf = HERE / "photo_quality.json"
    files = used_photos(post)
    if not qf.exists():
        print("PHOTO QC: photo_quality.json missing, run python3 photo_quality.py first (gate skipped)")
        return files, ["photo_quality.json missing: gate skipped"]
    q = json.loads(qf.read_text(encoding="utf-8"))["photos"]
    exc = post.get("photo_exceptions", {})
    recent = {}
    for m in manifest[:7]:
        if m.get("date") == post["date"]:
            continue
        for f in m.get("photos", []):
            recent.setdefault(f, m["date"])
    errors, notes = [], []
    for f in files:
        m = q.get(f)
        if m is None:
            errors.append(f"{f}: not measured (add it to photos.json and rerun photo_quality.py)")
            continue
        hard = [x for x in m.get("flags", []) if x in HARD]
        if hard and f in exc:
            notes.append(f"{f}: {','.join(hard)} accepted: {exc[f]}")
        elif hard:
            errors.append(f"{f}: {','.join(hard)} (short side {m.get('short_side')}px, sharpness {m.get('sharpness')})")
        if m.get("note"):
            notes.append(f"{f}: {m['note']} (sharpness {m['sharpness']})")
        if f in recent:
            notes.append(f"{f}: also used on {recent[f]}; use a different strong photo if one fits")
    for n in notes:
        print("PHOTO QC note:", n)
    for e in errors:
        print("PHOTO QC FAIL:", e)
    if errors and "--no-qc" not in sys.argv:
        sys.exit("PHOTO QC failed: swap these photos for stronger ones (or add a reasoned photo_exceptions entry), then re-render.")
    return files, notes + errors


def main(spec_path):
    post = json.loads(pathlib.Path(spec_path).read_text(encoding="utf-8"))
    d = post["date"]
    mp0 = HERE / "manifest.json"
    used, qc_notes = photo_qc(post, json.loads(mp0.read_text(encoding="utf-8")) if mp0.exists() else [])
    out = HERE / "daily" / d
    out.mkdir(parents=True, exist_ok=True)
    for f in list(out.glob("*.jpg")) + list(out.glob("*.mp4")):
        f.unlink()
    from playwright.sync_api import sync_playwright
    kw = {"executable_path": "/opt/pw-browsers/chromium"} if os.path.exists("/opt/pw-browsers/chromium") else {}
    files = []
    reel = poster = None
    with sync_playwright() as pw:
        b = pw.chromium.launch(**kw)
        pg = b.new_page()
        n = len(post["slides"])
        for i, sl in enumerate(post["slides"], 1):
            shot_png(pg, slide(sl, i, n, post), 1080, 1350, out / f"slide-{i:02d}.jpg")
            files.append(f"daily/{d}/slide-{i:02d}.jpg")
        shot_png(pg, story(post["story"], post), 1080, 1920, out / "story.jpg")
        if post.get("reel"):
            make_reel(post, out, pg)
            reel = f"daily/{d}/reel.mp4"
            poster = f"daily/{d}/reel-poster.jpg"
        b.close()
    mp = HERE / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else []
    man = [m for m in man if m.get("date") != d and "slides" in m]
    man.insert(0, {"date": d, "topic": post["topic"], "hook": post["hook"], "keyword": post["keyword"],
                   "caption": post["caption"], "slides": files, "story": f"daily/{d}/story.jpg",
                   "reel": reel, "reel_poster": poster, "schedule": post.get("schedule"),
                   "voiceover": timed_script(post["reel"]) if post.get("reel") else "", "sound": (post.get("reel") or {}).get("sound", ""),
                   "photos": used, "photo_qc": qc_notes})
    man = man[:30]
    mp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    (HERE / "index.html").write_text(page(man), encoding="utf-8")
    shutil.rmtree(ENH, ignore_errors=True)
    print(json.dumps({"date": d, "slides": files, "story": f"daily/{d}/story.jpg", "reel": reel, "reel_poster": poster}))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "post.json")

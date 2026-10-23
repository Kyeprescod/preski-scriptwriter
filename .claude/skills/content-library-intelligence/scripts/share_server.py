#!/usr/bin/env python3
"""Serve the pulled-clips folder to your phone over home Wi-Fi. Free, no cloud storage, read-only.

    python share_server.py <folder> [--port 8765]

Prints a link containing a private key; open it on the phone (same Wi-Fi), tap a clip, then
Download / Save to Photos. Only files inside <folder> are ever served.
"""
import argparse, html, json, mimetypes, os, secrets, socket, sqlite3, subprocess, sys, threading, time, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

LOCK = threading.Lock()
STATUSES = {"approved", "changes", "rejected", "pending"}
VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Preski Clips</title>
<style>
:root{color-scheme:dark light;--bg:#0b0b0d;--fg:#f4f4f5;--mut:#9a9aa3;--card:#17171b;--acc:#ff5a1f}
@media(prefers-color-scheme:light){:root{--bg:#fafafa;--fg:#111;--mut:#666;--card:#fff}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif;padding:16px}
h1{font-size:20px;margin:0 0 12px}a{color:var(--acc)}
.card{background:var(--card);border-radius:14px;padding:12px;margin:0 0 14px}
video,img{width:100%;border-radius:10px;background:#000}
.row{display:flex;gap:10px;align-items:center;justify-content:space-between;margin-top:8px}
.btn{background:var(--acc);color:#fff;text-decoration:none;padding:10px 14px;border-radius:10px;font-weight:600}
.mut{color:var(--mut);font-size:13px}.dir a{display:block;padding:14px;font-weight:600}
</style></head><body>@@BODY@@</body></html>"""


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def load_items(root):
    """Finished videos (+ sidecar metadata + decision), newest first."""
    fin = os.path.join(root, "finished")
    try:
        dec = json.load(open(os.path.join(root, "approvals.json"), encoding="utf-8"))
    except (OSError, ValueError):
        dec = {}
    items = []
    for dp, _, fns in os.walk(fin):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() not in VIDEO:
                continue
            full = os.path.join(dp, fn)
            rid = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                meta = json.load(open(full + ".meta.json", encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            d = dec.get(rid, {})
            items.append({"id": rid, "name": fn, "mtime": os.path.getmtime(full), "title": meta.get("title") or fn,
                          "hook": meta.get("hook", ""), "caption": meta.get("caption", ""), "pinned": meta.get("pinned_comment", ""),
                          "gaps": meta.get("footage_gaps", []), "duration": meta.get("duration"),
                          "platforms": d.get("platforms") or meta.get("platforms") or ["instagram", "tiktok", "youtube"],
                          "publish_at": d.get("publish_at") or meta.get("publish_at", ""),
                          "status": d.get("status", "pending"), "note": d.get("note", "")})
    return sorted(items, key=lambda x: -x["mtime"])


def save_decision(root, rid, body):
    status = body.get("status")
    if status not in STATUSES or rid not in {i["id"] for i in load_items(root)}:
        return None
    plats = [p for p in body.get("platforms", []) if p in ("instagram", "tiktok", "youtube")]
    rec = {"status": status, "platforms": plats, "publish_at": str(body.get("publish_at", ""))[:25],
           "note": str(body.get("note", ""))[:500], "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with LOCK:
        path = os.path.join(root, "approvals.json")
        try:
            dec = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            dec = {}
        dec[rid] = rec
        tmp = path + ".tmp"
        json.dump(dec, open(tmp, "w", encoding="utf-8"), indent=1)
        os.replace(tmp, path)
    return rec


APPROVE = """<!doctype html><html lang=en-GB><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Approve posts</title><style>
:root{--ink:#052148;--red:#e1262d;--fog:#eef1f6;--ok:#0d7a3f}
*{box-sizing:border-box}body{margin:0;background:var(--fog);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}
header{background:var(--ink);color:#fff;padding:14px 16px;position:sticky;top:0;z-index:5}header h1{margin:0;font-size:20px}
header a{color:#fff;font-size:14px}main{padding:14px;max-width:560px;margin:0 auto}
.card{background:#fff;border-radius:8px;padding:12px;margin:0 0 16px;border-left:6px solid #9aa7c0}
.card.approved{border-color:var(--ok)}.card.rejected{border-color:var(--red)}.card.changes{border-color:#d98a00}
video{width:100%;border-radius:6px;background:#000;max-height:70vh}h2{font-size:18px;margin:10px 0 2px}
.lbl{font-weight:700;font-size:13px;margin:12px 0 4px}.box{background:var(--fog);border-radius:6px;padding:10px;white-space:pre-wrap;font-size:15px}
button,input,select,textarea{font:inherit}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.b{flex:1;min-height:48px;border:0;border-radius:6px;font-weight:700;color:#fff;background:var(--ink)}
.b.go{background:var(--ok)}.b.no{background:var(--red)}.b.mid{background:#d98a00}.b.sm{flex:0;min-height:36px;padding:0 12px;font-size:14px}
label.chip{display:inline-flex;gap:6px;align-items:center;padding:6px 10px;background:var(--fog);border-radius:20px;font-size:14px}
input[type=datetime-local],textarea{width:100%;padding:10px;border:2px solid #d5dbe6;border-radius:6px}
.tag{display:inline-block;font-weight:700;font-size:13px;padding:3px 8px;border-radius:4px;color:#fff;background:#9aa7c0}
.tag.approved{background:var(--ok)}.tag.rejected{background:var(--red)}.tag.changes{background:#d98a00}
.warn{color:#8a5a00;font-size:14px;margin:8px 0 0}.empty{text-align:center;color:#556;padding:40px 0}
</style></head><body><header><h1>Approve posts</h1><a href="/?k=@@K@@">&larr; Clips and videos</a></header><main id=m><p class=empty>Loading...</p></main>
<script>
var K="@@K@@",m=document.getElementById("m");
function api(p,o){return fetch(p+(p.indexOf("?")<0?"?":"&")+"k="+K,o).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})}
function esc(s){var d=document.createElement("div");d.textContent=s==null?"":s;return d.innerHTML}
function copy(t,btn){var ok=function(){var o=btn.textContent;btn.textContent="Copied";setTimeout(function(){btn.textContent=o},1200)};
 if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok)}else{var a=document.createElement("textarea");a.value=t;a.style.position="fixed";a.style.opacity=0;document.body.appendChild(a);a.select();try{document.execCommand("copy");ok()}catch(e){}document.body.removeChild(a)}}
function card(it){
 var c=document.createElement("div");c.className="card "+it.status;
 var pl=["instagram","tiktok","youtube"].map(function(p){return '<label class=chip><input type=checkbox value='+p+(it.platforms.indexOf(p)>-1?" checked":"")+'> '+p[0].toUpperCase()+p.slice(1)+'</label>'}).join(" ");
 c.innerHTML='<span class="tag '+it.status+'">'+({pending:"Waiting for you",approved:"Approved",changes:"Needs changes",rejected:"Rejected"}[it.status])+'</span>'+
 '<h2>'+esc(it.title)+'</h2><video controls playsinline preload=metadata src="/'+encodeURI(it.id)+'?k='+K+'#t=0.1"></video>'+
 (it.gaps.length?'<p class=warn>Footage was missing for '+it.gaps.length+' line(s), so stand-ins were used.</p>':'')+
 (it.hook?'<div class=lbl>On-screen hook</div><div class=box>'+esc(it.hook)+'</div><div class=row><button class="b sm" data-c=hook>Copy hook</button></div>':'')+
 (it.caption?'<div class=lbl>Caption</div><div class=box>'+esc(it.caption)+'</div><div class=row><button class="b sm" data-c=caption>Copy caption</button></div>':'<p class=warn>No caption attached yet.</p>')+
 (it.pinned?'<div class=lbl>Pinned comment</div><div class=box>'+esc(it.pinned)+'</div><div class=row><button class="b sm" data-c=pinned>Copy pinned comment</button></div>':'')+
 '<div class=lbl>Post to</div><div class=row id=pl>'+pl+'</div><div class=lbl>Post at</div><input type=datetime-local class=when value="'+esc(it.publish_at)+'">'+
 '<div class=lbl>Note to Claude (for changes)</div><textarea class=note rows=2>'+esc(it.note)+'</textarea>'+
 '<div class=row><button class="b go" data-s=approved>Approve</button><button class="b mid" data-s=changes>Change</button><button class="b no" data-s=rejected>Reject</button></div>';
 c.addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;
  if(b.dataset.c){copy({hook:it.hook,caption:it.caption,pinned:it.pinned}[b.dataset.c],b);return}
  var body={id:it.id,status:b.dataset.s,note:c.querySelector(".note").value,publish_at:c.querySelector(".when").value,
   platforms:[].map.call(c.querySelectorAll(".chip input:checked"),function(x){return x.value})};
  if(body.status==="changes"&&!body.note.trim()){alert("Write what to change in the note first.");return}
  api("/api/decide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(){load()}).catch(function(){alert("That didn't save. Check the laptop is still on.")})});
 return c}
function load(){api("/api/items").then(function(d){m.innerHTML="";
 if(!d.items.length){m.innerHTML='<p class=empty>No finished videos yet.<br>Make one from the laptop menu (option 10).</p>';return}
 d.items.sort(function(a,b){return (a.status==="pending"?0:1)-(b.status==="pending"?0:1)});
 d.items.forEach(function(it){m.appendChild(card(it))})}).catch(function(){m.innerHTML='<p class=empty>Could not reach the laptop.</p>'})}
load();
</script></body></html>"""


HERE = os.path.dirname(os.path.abspath(__file__))
JOB = {"running": False, "started": None, "finished": None, "lines": [], "proc": None}


def lib_for(root):
    """The library folder: the folder that holds for-phone (or CLIL_LIB)."""
    for c in (os.environ.get("CLIL_LIB"), os.path.dirname(root)):
        if c and os.path.exists(os.path.join(c, "library.db")):
            return c
    return None


def have_gemini_key():
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return True
    try:
        return any(l.startswith("GEMINI_API_KEY=") and len(l.strip()) > 16
                   for l in open(os.path.expanduser("~/.config/watch/.env"), encoding="utf-8"))
    except OSError:
        return False


def library_status(root):
    lib = lib_for(root)
    out = {"library": bool(lib), "gemini_key": have_gemini_key(), "job": {k: JOB[k] for k in ("running", "started", "finished")},
           "job_lines": JOB["lines"][-8:]}
    if not lib:
        return out
    try:
        con = sqlite3.connect("file:%s?mode=ro" % os.path.join(lib, "library.db").replace("\\", "/"), uri=True)
        q = lambda sql: con.execute(sql).fetchone()[0]
        out.update(analysed=q("SELECT COUNT(*) FROM assets WHERE status='analysed'"),
                   waiting=q("SELECT COUNT(*) FROM assets WHERE status='probed'"),
                   cloud_only=q("SELECT COUNT(*) FROM assets WHERE status='cloud_only'"),
                   total=q("SELECT COUNT(*) FROM assets WHERE status NOT IN ('excluded','missing')"),
                   showcase=q("SELECT COUNT(DISTINCT asset_id) FROM tags WHERE tag='showcase'"))
        con.close()
    except sqlite3.Error as e:
        out["error"] = str(e)[:120]
    try:
        with open(os.path.join(lib, "autotag.log"), encoding="utf-8", errors="replace") as f:
            out["log_tail"] = [l.strip() for l in f.readlines()[-5:]]
    except OSError:
        out["log_tail"] = []
    return out


def start_tagging(root, maxn):
    lib = lib_for(root)
    if not lib:
        return {"error": "No library found next to this folder."}
    if not have_gemini_key():
        return {"error": "No Gemini key on the laptop yet. In PowerShell run: setx GEMINI_API_KEY \"your-key\" then restart the phone page."}
    with LOCK:
        if JOB["running"]:
            return {"error": "Already tagging. Watch the progress below."}
        JOB.update(running=True, started=time.strftime("%H:%M:%S"), finished=None, lines=[])
    maxn = max(1, min(int(maxn or 40), 200))

    def work():
        try:
            p = subprocess.Popen([sys.executable, os.path.join(HERE, "gemini_tagger.py"), "--lib", lib, "--limit", "20", "--max", str(maxn)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
            JOB["proc"] = p
            for line in p.stdout:
                JOB["lines"].append(line.strip()[:200])
            p.wait()
        finally:
            JOB.update(running=False, finished=time.strftime("%H:%M:%S"), proc=None)
    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


LIBRARY = """<!doctype html><html lang=en-GB><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Library</title><style>
:root{--ink:#052148;--red:#e1262d;--fog:#eef1f6;--ok:#0d7a3f}*{box-sizing:border-box}
body{margin:0;background:var(--fog);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}
header{background:var(--ink);color:#fff;padding:14px 16px}header h1{margin:0;font-size:20px}header a{color:#fff;font-size:14px}
main{padding:14px;max-width:560px;margin:0 auto}.card{background:#fff;border-radius:10px;padding:14px;margin:0 0 14px}
.big{font:800 44px/1 system-ui;margin:4px 0}.bar{height:14px;background:#d8dfeb;border-radius:7px;overflow:hidden;margin:8px 0}
.bar i{display:block;height:100%;background:var(--ok);width:0}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.b{flex:1;min-height:52px;border:0;border-radius:8px;background:var(--red);color:#fff;font-weight:700;font-size:16px}.b[disabled]{opacity:.5}
.b.alt{background:var(--ink)}.mut{color:#566;font-size:14px}pre{white-space:pre-wrap;font:13px/1.4 ui-monospace,monospace;background:var(--fog);padding:10px;border-radius:6px;margin:8px 0 0}
.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center}.stat b{display:block;font-size:24px}
</style></head><body><header><h1>Library</h1><a href="/?k=@@K@@">&larr; Clips and videos</a></header><main id=m><p class=mut>Loading...</p></main>
<script>
var K="@@K@@",m=document.getElementById("m"),busy=false;
function api(p,o){return fetch(p+"?k="+K,o).then(function(r){return r.json()})}
function esc(s){var d=document.createElement("div");d.textContent=s==null?"":s;return d.innerHTML}
function draw(d){
 if(!d.library){m.innerHTML='<div class=card>No library found on the laptop yet. Run the menu on the laptop first (option 3).</div>';return}
 var tot=d.total||0,pct=tot?Math.round(100*d.analysed/tot):0,run=d.job.running;
 m.innerHTML='<div class=card><div class=mut>Clips tagged</div><div class=big>'+d.analysed+' <span class=mut style="font-size:18px">of '+tot+'</span></div>'+
 '<div class=bar><i style="width:'+pct+'%"></i></div><div class=stat><div><b>'+d.waiting+'</b>waiting</div><div><b>'+d.cloud_only+'</b>in iCloud only</div><div><b>'+d.showcase+'</b>showcase</div></div></div>'+
 '<div class=card><b>Tag with Gemini</b><p class=mut style="margin:4px 0 0">Uses your Gemini key on the laptop. No Claude usage. The laptop must stay on.'+(d.gemini_key?'':' <b style="color:#b00">No key found on the laptop yet.</b>')+'</p>'+
 '<div class=row><button class=b id=t40'+(run||!d.gemini_key?' disabled':'')+'>'+(run?'Tagging...':'Tag 40 clips')+'</button><button class="b alt" id=t120'+(run||!d.gemini_key?' disabled':'')+'>Tag 120</button></div>'+
 (d.job.started?'<p class=mut>'+(run?'Started '+d.job.started+'. Updates every few seconds.':'Last run '+d.job.started+' to '+(d.job.finished||'?'))+'</p>':'')+
 (d.job_lines.length?'<pre>'+esc(d.job_lines.join("\\n"))+'</pre>':'')+'</div>'+
 (d.log_tail&&d.log_tail.length?'<div class=card><b>Overnight tagger log</b><pre>'+esc(d.log_tail.join("\\n"))+'</pre></div>':'');
 [["t40",40],["t120",120]].forEach(function(x){var b=document.getElementById(x[0]);if(b)b.onclick=function(){go(x[1])}})}
function go(n){api("/api/tag",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({max:n})}).then(function(r){if(r.error)alert(r.error);load()})}
function load(){api("/api/status").then(draw).catch(function(){m.innerHTML='<div class=card>Could not reach the laptop.</div>'})}
load();setInterval(load,4000);
</script></body></html>"""


def make_handler(root, key):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="text/html; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if q.get("k", [""])[0] != key:
                return self.send(403, "Open the exact link shown on the laptop.")
            if u.path == "/approve":
                return self.send(200, APPROVE.replace("@@K@@", key))
            if u.path == "/library":
                return self.send(200, LIBRARY.replace("@@K@@", key))
            if u.path == "/api/status":
                return self.send(200, json.dumps(library_status(root)), "application/json")
            if u.path == "/api/items":
                return self.send(200, json.dumps({"items": load_items(root)}), "application/json")
            rel = urllib.parse.unquote(u.path).lstrip("/")
            full = os.path.realpath(os.path.join(root, rel))
            hidden = any(part.startswith(".") for part in rel.split("/") if part)
            if hidden or os.path.commonpath([full, root]) != root or not os.path.exists(full):
                return self.send(404, "Not found")
            kq = "?k=" + key
            if os.path.isdir(full):
                return self.listing(full, rel, kq)
            return self.file(full, "dl" in q)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if urllib.parse.parse_qs(u.query).get("k", [""])[0] != key or u.path not in ("/api/decide", "/api/tag"):
                return self.send(403, "No")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 20000)))
            except (ValueError, TypeError):
                return self.send(400, "Bad request")
            if u.path == "/api/tag":
                return self.send(200, json.dumps(start_tagging(root, body.get("max"))), "application/json")
            rec = save_decision(root, str(body.get("id", "")), body)
            if rec is None:
                return self.send(400, json.dumps({"error": "unknown video or status"}), "application/json")
            return self.send(200, json.dumps(rec), "application/json")

        def listing(self, full, rel, kq):
            names = sorted((n for n in os.listdir(full) if not n.startswith(".")), key=str.lower)
            dirs = [n for n in names if os.path.isdir(os.path.join(full, n))]
            files = [n for n in names if os.path.splitext(n)[1].lower() in VIDEO | IMAGE]
            href = lambda n: urllib.parse.quote("/" + (rel + "/" if rel else "") + n)
            out = ["<h1>Preski Clips%s</h1>" % (" / " + html.escape(rel) if rel else "")]
            if not rel:
                out.append('<p><a class="btn" style="display:block;text-align:center" href="/approve%s">Approve posts</a></p>' % kq)
                out.append('<p><a class="btn" style="display:block;text-align:center" href="/library%s">Library and tagging</a></p>' % kq)
                out.append('<p class="mut">iPhone: tap Download, then the arrow in Safari, open the file, tap Share, Save Video.</p>')
            if rel:
                up = urllib.parse.quote("/" + os.path.dirname(rel))
                out.append('<p><a href="%s%s">&larr; Back</a></p>' % (up, kq))
            if dirs:
                out.append('<div class="card dir">' + "".join(
                    '<a href="%s%s">%s</a>' % (href(d), kq, html.escape(d)) for d in dirs) + "</div>")
            for n in files:
                ext = os.path.splitext(n)[1].lower()
                u = href(n)
                media = ('<video controls playsinline preload="metadata" src="%s%s#t=0.1"></video>' % (u, kq)
                         if ext in VIDEO else '<img loading=lazy src="%s%s">' % (u, kq))
                out.append('<div class="card">%s<div class="row"><span class="mut">%s</span>'
                           '<a class="btn" href="%s%s&dl=1">Download</a></div></div>'
                           % (media, html.escape(n), u, kq))
            if not dirs and not files:
                out.append('<p class="mut">Nothing here yet. Pull clips from the menu on the laptop.</p>')
            self.send(200, PAGE.replace("@@BODY@@", "".join(out)))

        def file(self, full, download):
            size = os.path.getsize(full)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            code = 200
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                try:
                    start = int(a) if a else max(0, size - int(b))
                    end = int(b) if (a and b) else size - 1
                    end = min(end, size - 1)
                    code = 206
                except ValueError:
                    start, end, code = 0, size - 1, 200
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % os.path.basename(full))
            self.end_headers()
            try:
                with open(full, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    root = os.path.realpath(a.folder)
    os.makedirs(root, exist_ok=True)
    keyfile = os.path.join(root, ".share_key")
    key = open(keyfile).read().strip() if os.path.exists(keyfile) else secrets.token_urlsafe(9)
    open(keyfile, "w").write(key)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(root, key))
    link = "http://%s:%d/?k=%s" % (lan_ip(), a.port, key)
    print("\nOpen this on your phone (same Wi-Fi as this laptop):\n\n    %s\n" % link)
    try:  # keep the latest link where you can find it again
        with open(os.path.join(os.path.dirname(root), "phone-link.txt"), "w", encoding="utf-8") as f:
            f.write(link + "\n")
    except OSError:
        pass
    print("Serving: %s\nLeave this window open. Press Ctrl+C to stop." % root)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Serve the pulled-clips folder to your phone over home Wi-Fi. Free, no cloud storage, read-only.

    python share_server.py <folder> [--port 8765]

Prints a link containing a private key; open it on the phone (same Wi-Fi), tap a clip, then
Download / Save to Photos. Only files inside <folder> are ever served.
"""
import argparse, html, mimetypes, os, secrets, socket, sys, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
            rel = urllib.parse.unquote(u.path).lstrip("/")
            full = os.path.realpath(os.path.join(root, rel))
            hidden = any(part.startswith(".") for part in rel.split("/") if part)
            if hidden or os.path.commonpath([full, root]) != root or not os.path.exists(full):
                return self.send(404, "Not found")
            kq = "?k=" + key
            if os.path.isdir(full):
                return self.listing(full, rel, kq)
            return self.file(full, "dl" in q)

        def listing(self, full, rel, kq):
            names = sorted((n for n in os.listdir(full) if not n.startswith(".")), key=str.lower)
            dirs = [n for n in names if os.path.isdir(os.path.join(full, n))]
            files = [n for n in names if os.path.splitext(n)[1].lower() in VIDEO | IMAGE]
            href = lambda n: urllib.parse.quote("/" + (rel + "/" if rel else "") + n)
            out = ["<h1>Preski Clips%s</h1>" % (" / " + html.escape(rel) if rel else "")]
            if not rel:
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
    print("\nOpen this on your phone (same Wi-Fi as this laptop):\n\n    http://%s:%d/?k=%s\n" % (lan_ip(), a.port, key))
    print("Serving: %s\nLeave this window open. Press Ctrl+C to stop." % root)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())

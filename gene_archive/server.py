"""Comments server: serves the built site and stores relatives' comments in SQLite.

Standard library only. Optional PIN gate for private archives. Run with `gene serve <site>`
or in Docker (see docs/deploy.md). Behind a reverse proxy set GENE_TRUST_PROXY=1 so the
rate limits see real client addresses.

Settings (command-line flags of `gene serve` or environment variables):
  GENE_SITE        folder with the built site (default <site>/_site)
  GENE_STATE_DIR   folder for comments.db and the cookie secret
  GENE_PIN         PIN for a private archive (or GENE_PIN_HASH = sha256 hex of it); empty = open site
  GENE_PREFIX      public URL prefix when the site lives in a sub-folder behind a proxy (e.g. /family)
  GENE_MODERATE    1 = new comments stay hidden until approved with `gene comments approve`
  GENE_HOST, GENE_PORT, GENE_INSECURE_COOKIE (1 for http://localhost tests), GENE_TRUST_PROXY
"""
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from email.utils import formatdate, parsedate_to_datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY = 16 * 1024
MAX_TEXT = 4000
MAX_AUTHOR = 80
MAX_COMMENTS = 20000                      # a full database refuses new comments instead of growing forever
PIN_FAILS, PIN_WINDOW = 6, 15 * 60
POSTS, POST_WINDOW = 30, 10 * 60
TARGET_RE = re.compile(r"general|[ISF]\d{1,7}")   # a person, a document, a family or the general thread
COOKIE_NAME = "gene_session"


class Settings:
    def __init__(self, site, state_dir, pin_hash="", prefix="", host="127.0.0.1", port=8111,
                 moderate=False, secure_cookie=True, trust_proxy=False):
        self.site = Path(site).resolve()
        self.state_dir = Path(state_dir)
        self.pin_hash = (pin_hash or "").strip().lower()
        self.prefix = (prefix or "").rstrip("/")
        self.host, self.port = host, int(port)
        self.moderate, self.secure_cookie, self.trust_proxy = moderate, secure_cookie, trust_proxy

    @classmethod
    def from_env(cls, **override):
        env = os.environ
        pin_hash = env.get("GENE_PIN_HASH", "")
        if env.get("GENE_PIN"):
            pin_hash = hashlib.sha256(env["GENE_PIN"].encode()).hexdigest()
        values = dict(site=env.get("GENE_SITE", "_site"), state_dir=env.get("GENE_STATE_DIR", ".gene-state"),
                      pin_hash=pin_hash, prefix=env.get("GENE_PREFIX", ""), host=env.get("GENE_HOST", "127.0.0.1"),
                      port=env.get("GENE_PORT", "8111"), moderate=env.get("GENE_MODERATE") == "1",
                      secure_cookie=env.get("GENE_INSECURE_COOKIE") != "1", trust_proxy=env.get("GENE_TRUST_PROXY") == "1")
        values.update({k: v for k, v in override.items() if v is not None})
        return cls(**values)


LOGIN_PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{title}</title>
<style>
:root{{--bg:#f6f1e7;--card:#fffdf8;--ink:#2b2520;--muted:#7a6f63;--line:#e2d8c6;--accent:#8a4b2a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16130f;--card:#201c17;--ink:#ece4d6;--muted:#a79b8b;--line:#3a332a;--accent:#e0a578}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:16px/1.5 Georgia,serif;padding:16px;box-sizing:border-box}}
main{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:32px 28px;max-width:360px;width:100%;text-align:center}}
h1{{font-size:24px;margin:0 0 8px;font-weight:600}}p{{color:var(--muted);margin:0 0 20px}}
input{{width:100%;box-sizing:border-box;font:24px system-ui;letter-spacing:.3em;text-align:center;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}}
button{{margin-top:14px;width:100%;padding:11px;border:0;border-radius:6px;background:var(--accent);color:#fff;font:600 16px system-ui;cursor:pointer}}
.err{{color:#b3261e;margin:12px 0 0;min-height:1em;font:14px system-ui}}
</style></head><body><main>
<h1>{heading}</h1><p>{hint}</p>
<form method="post" action="{prefix}/unlock"><input type="hidden" name="next" id="next" value="">
<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" autofocus required aria-label="PIN">
<button type="submit">{button}</button></form><div class="err">{error}</div></main>
<script>var h=location.hash;if(/^#[A-Za-z0-9\\/?=&%._-]{{1,300}}$/.test(h))document.getElementById('next').value=h;</script></body></html>"""
LOGIN_TEXT = {
    "ru": dict(title="Семейный архив — вход", heading="Семейный архив", hint="Введите PIN, который вам прислали родные.",
               button="Открыть", wrong="Неверный PIN.", slow="Слишком много попыток. Попробуйте через 15 минут."),
    "en": dict(title="Family archive — sign in", heading="Family archive", hint="Enter the PIN your family sent you.",
               button="Open", wrong="Wrong PIN.", slow="Too many attempts. Try again in 15 minutes."),
}
LOGIN_SCRIPT = "var h=location.hash;if(/^#[A-Za-z0-9\\/?=&%._-]{1,300}$/.test(h))document.getElementById('next').value=h;"
NEXT_RE = re.compile(r"#[A-Za-z0-9/?=&%._-]{1,300}")


def make_handler(cfg):
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    secret_path = cfg.state_dir / "cookie-secret"
    if not secret_path.exists():
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    # the session token depends on the PIN: changing the PIN signs everybody out
    token = hmac.new(secret_path.read_bytes(), b"gene-session:" + cfg.pin_hash.encode(), hashlib.sha256).hexdigest()
    db_path = cfg.state_dir / "comments.db"
    db_lock, hits_lock, hits = threading.Lock(), threading.Lock(), {}
    script_hash = "sha256-" + __import__("base64").b64encode(hashlib.sha256(LOGIN_SCRIPT.encode()).digest()).decode()

    def db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL, author TEXT NOT NULL,
            text TEXT NOT NULL, created_at TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT, processed_note TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS comments_person ON comments(person_id)")

    def too_many(kind, ip, limit, window, record):
        now = time.time()
        with hits_lock:
            if len(hits) > 5000:   # forget idle addresses
                for k in [k for k, v in hits.items() if not v or now - v[-1] > max(PIN_WINDOW, POST_WINDOW)]:
                    del hits[k]
            recent = [t for t in hits.get((kind, ip), []) if now - t < window]
            if record:
                recent.append(now)
            hits[(kind, ip)] = recent
            return len(recent) > limit if record else len(recent) >= limit

    class Handler(BaseHTTPRequestHandler):
        server_version = "gene-archive"
        timeout = 20   # a stalled client cannot hold a thread forever

        def _ip(self):
            if cfg.trust_proxy:
                fwd = self.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
                if fwd:
                    return fwd
            return self.client_address[0]

        def _lang(self):
            return "ru" if self.headers.get("Accept-Language", "").lower().startswith("ru") else "en"

        def _authorized(self):
            if not cfg.pin_hash:
                return True
            jar = cookies.SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
                return hmac.compare_digest(jar[COOKIE_NAME].value, token)
            except (cookies.CookieError, KeyError):
                return False

        def _headers(self, status, ctype, length, extra=None):
            self.send_response(status)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if cfg.pin_hash:
                self.send_header("X-Robots-Tag", "noindex, nofollow")
            cache = "public, max-age=3600" if status in (200, 304) and re.match(r"(image/|font/|application/pdf)", ctype) else "no-cache"
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _send(self, status, body, ctype, head=False, extra=None):
            self._headers(status, ctype, len(body), extra)
            if not head:
                self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _login(self, error="", status=200, head=False):
            text = LOGIN_TEXT[self._lang()]
            body = LOGIN_PAGE.format(prefix=cfg.prefix, error=text.get(error, ""), lang=self._lang(), **{
                k: v for k, v in text.items() if k in ("title", "heading", "hint", "button")}).encode()
            csp = f"default-src 'none'; style-src 'unsafe-inline'; script-src '{script_hash}'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
            self._send(status, body, "text/html; charset=utf-8", head, {"Content-Security-Policy": csp})

        def _redirect(self, location, cookie=None):
            extra = {"Location": location}
            if cookie:
                extra["Set-Cookie"] = cookie
            self._send(303, b"", "text/plain", extra=extra)

        def _static(self, path, head):
            rel = unquote(path).lstrip("/") or "index.html"
            if rel.endswith("/"):
                rel += "index.html"
            target = (cfg.site / rel).resolve()
            if target.is_dir():
                target = target / "index.html"
            if cfg.site not in target.parents or not target.is_file():
                self._send(404, b"Not found", "text/plain; charset=utf-8", head)
                return
            stat = target.stat()
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            extra = {"Last-Modified": formatdate(stat.st_mtime, usegmt=True)}
            since = self.headers.get("If-Modified-Since")
            if since:
                try:
                    if int(stat.st_mtime) <= int(parsedate_to_datetime(since).timestamp()):
                        self._headers(304, ctype, 0, extra)
                        return
                except (TypeError, ValueError, OverflowError):
                    pass
            if target.suffix == ".ged":
                extra["Content-Disposition"] = 'attachment; filename="family_tree.ged"'
            self._headers(200, ctype, stat.st_size, extra)
            if not head:
                with target.open("rb") as f:
                    while chunk := f.read(64 * 1024):
                        self.wfile.write(chunk)

        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("bad length") from None
            if length < 0 or length > MAX_BODY:
                raise ValueError("too large")
            return self.rfile.read(length)

        def do_GET(self):
            self._get(False)

        def do_HEAD(self):
            self._get(True)

        def _get(self, head):
            path = urlsplit(self.path).path
            if path == "/logout":
                self._redirect(f"{cfg.prefix}/", f"{COOKIE_NAME}=; Path={cfg.prefix or '/'}; HttpOnly; SameSite=Strict; Max-Age=0"
                               + ("; Secure" if cfg.secure_cookie else ""))
                return
            if path == "/healthz":
                self._send(200, b"ok", "text/plain", head)
                return
            if not self._authorized():
                if path.startswith("/api/"):
                    self._json(401, {"error": "unauthorized"})
                else:
                    self._login(head=head)
                return
            if path == "/api/comments":
                with db_lock, db() as conn:
                    rows = conn.execute("SELECT id, person_id, author, text, created_at, processed_at, processed_note "
                                        "FROM comments WHERE hidden = 0 ORDER BY id").fetchall()
                self._json(200, [dict(r) for r in rows])
                return
            self._static(path, head)

        def do_POST(self):
            path = urlsplit(self.path).path
            ip = self._ip()
            try:
                body = self._read_body()
            except ValueError:
                self._json(413, {"error": "too large"})
                return
            if path == "/unlock":
                if not cfg.pin_hash:
                    self._redirect(f"{cfg.prefix}/")
                    return
                if too_many("pin", ip, PIN_FAILS, PIN_WINDOW, record=False):
                    self._login("slow", 429)
                    return
                form = parse_qs(body.decode("utf-8", "replace"))
                pin = form.get("pin", [""])[0].strip()
                nxt = form.get("next", [""])[0]
                nxt = nxt if NEXT_RE.fullmatch(nxt) else ""
                if not hmac.compare_digest(hashlib.sha256(pin.encode()).hexdigest(), cfg.pin_hash):
                    too_many("pin", ip, PIN_FAILS, PIN_WINDOW, record=True)
                    self._login("wrong", 401)
                    return
                cookie = (f"{COOKIE_NAME}={token}; Path={cfg.prefix or '/'}; HttpOnly; SameSite=Lax; Max-Age={180 * 86400}"
                          + ("; Secure" if cfg.secure_cookie else ""))
                self._redirect(f"{cfg.prefix}/{nxt}", cookie)
                return
            if path == "/api/comments":
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                # CSRF: besides SameSite cookies, require a header that a form on another site cannot send
                if self.headers.get("X-Gene-Client") != "1":
                    self._json(403, {"error": "forbidden"})
                    return
                if too_many("post", ip, POSTS, POST_WINDOW, record=True):
                    self._json(429, {"error": "too many comments, try again later"})
                    return
                try:
                    data = json.loads(body)
                    person_id = str(data.get("person_id", "")).strip()
                    author = " ".join(str(data.get("author", "")).split())[:MAX_AUTHOR]
                    text = str(data.get("text", "")).strip()[:MAX_TEXT]
                    trap = str(data.get("website", ""))   # hidden field: filled only by bots
                except (ValueError, AttributeError):
                    self._json(400, {"error": "bad json"})
                    return
                if not TARGET_RE.fullmatch(person_id) or not author or not text:
                    self._json(400, {"error": "name and text are required"})
                    return
                created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                hidden = 1 if (cfg.moderate or trap) else 0
                with db_lock, db() as conn:
                    if conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] >= MAX_COMMENTS:
                        self._json(507, {"error": "comment storage is full"})
                        return
                    new_id = conn.execute("INSERT INTO comments (person_id, author, text, created_at, hidden) VALUES (?, ?, ?, ?, ?)",
                                          (person_id, author, text, created, hidden)).lastrowid
                self._json(201, {"id": new_id, "person_id": person_id, "author": author, "text": text,
                                 "created_at": created, "pending": bool(hidden)})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            # no addresses and no bodies in the log: method, path and status only
            print(f"{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}", flush=True)

    return Handler, db


def serve(cfg):
    handler, _ = make_handler(cfg)
    server = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    server.daemon_threads = True
    print(f"gene-archive: serving {cfg.site} on http://{cfg.host}:{cfg.port}{cfg.prefix}/"
          + (" (PIN required)" if cfg.pin_hash else ""), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def comments_db(state_dir):
    conn = sqlite3.connect(Path(state_dir) / "comments.db")
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    socket.setdefaulttimeout(30)
    serve(Settings.from_env())

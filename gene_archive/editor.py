"""Online editor: accounts of editors, saving changes to family_tree.json, history in git.

Standard library only (Pillow, when installed, cleans uploaded photos). Used by the server
when it runs with `gene serve <site> --editor`; accounts are managed with `gene users`.

* Accounts live in <state>/editor.db: name, role (`admin` or `editor`), scrypt password hash.
  A new account gets a one-time invitation link; the person sets the password themselves.
* Every change is checked with `validate()` before it is written: a change that adds an error
  is refused. Errors that were already in the data do not block unrelated edits.
* Two people editing the same record: the second save sees that the record changed
  under them (the client sends the record as it was loaded) and gets a conflict instead of
  overwriting it. Edits of different records never conflict.
* Every change writes a line to `corrections` (field, before, after, who, why) and to
  `research_log`, then becomes a git commit by its author, so any state can be restored.
"""
import contextlib
import copy
import datetime
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from .validate import parse_date, validate

ROLES = ("admin", "editor")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,31}")
MIN_PASSWORD = 10
SESSION_DAYS = 30
INVITE_DAYS = 7
SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
KINDS = {   # family_tree.json list → (key field, id prefix)
    "people": ("id", "I"), "families": ("id", "F"), "sources": ("id", "S"),
    "places": ("slug", None), "research_leads": ("id", "L"),
}
UPLOAD_TYPES = {".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff", ".png": b"\x89PNG\r\n\x1a\n",
                ".webp": b"RIFF", ".gif": b"GIF8", ".pdf": b"%PDF-"}
MAX_UPLOAD = 30 * 1024 * 1024
PROPOSAL_FIELDS = ("display_name", "birth.date", "birth.place", "death.date", "death.place", "other")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(digest) // 2, maxmem=64 * 1024 * 1024)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


_DUMMY_HASH = None


class AccountError(ValueError):
    pass


class Accounts:
    """Editors, their sessions and one-time invitation links (SQLite in the state folder)."""

    def __init__(self, state_dir):
        self.path = Path(state_dir) / "editor.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                display TEXT NOT NULL, role TEXT NOT NULL, pw_hash TEXT, disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                csrf TEXT NOT NULL, created_at TEXT NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS invites (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, user TEXT,
                event TEXT NOT NULL, detail TEXT);
            CREATE TABLE IF NOT EXISTS proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL,
                field TEXT NOT NULL, value TEXT NOT NULL, note TEXT NOT NULL, author TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', handled_by TEXT, handled_at TEXT,
                handled_note TEXT);
            """)
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:   # commit or roll back
                yield conn
        finally:
            conn.close()

    def log(self, user, event, detail=""):
        with self.lock, self._db() as c:
            c.execute("INSERT INTO audit (at, user, event, detail) VALUES (?, ?, ?, ?)", (now_iso(), user, event, detail[:500]))

    # --- accounts
    def add_user(self, name, role="editor", display=None):
        name = name.strip().lower()
        if not NAME_RE.fullmatch(name):
            raise AccountError("login: 2–32 latin letters, digits, . _ -")
        if role not in ROLES:
            raise AccountError(f"role must be one of {', '.join(ROLES)}")
        with self.lock, self._db() as c:
            if c.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
                raise AccountError(f"user {name} already exists")
            c.execute("INSERT INTO users (name, display, role, created_at) VALUES (?, ?, ?, ?)",
                      (name, (display or name).strip()[:80], role, now_iso()))
        self.log(None, "user_added", f"{name} ({role})")
        return self.invite(name)

    def user(self, name):
        with self._db() as c:
            r = c.execute("SELECT * FROM users WHERE name = ?", (name.strip().lower(),)).fetchone()
        return dict(r) if r else None

    def users(self):
        with self._db() as c:
            return [dict(r) for r in c.execute("SELECT id, name, display, role, disabled, created_at, pw_hash IS NOT NULL AS active FROM users ORDER BY id")]

    def invite(self, name):
        """A one-time link to set (or reset) the password; valid for INVITE_DAYS."""
        u = self.user(name)
        if not u:
            raise AccountError(f"no user {name}")
        token = secrets.token_urlsafe(24)
        with self.lock, self._db() as c:
            c.execute("DELETE FROM invites WHERE user_id = ? OR expires_at < ?", (u["id"], time.time()))
            c.execute("INSERT INTO invites VALUES (?, ?, ?)", (_token_hash(token), u["id"], time.time() + INVITE_DAYS * 86400))
        return token

    def invite_user(self, token):
        with self._db() as c:
            r = c.execute("SELECT u.* FROM invites i JOIN users u ON u.id = i.user_id WHERE i.token_hash = ? AND i.expires_at > ? AND u.disabled = 0",
                          (_token_hash(token or ""), time.time())).fetchone()
        return dict(r) if r else None

    def accept_invite(self, token, password):
        u = self.invite_user(token)
        if not u:
            raise AccountError("invitation expired or already used")
        self.set_password(u["name"], password)
        with self.lock, self._db() as c:
            c.execute("DELETE FROM invites WHERE user_id = ?", (u["id"],))
        return self.user(u["name"])

    def set_password(self, name, password):
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"password: at least {MIN_PASSWORD} characters")
        u = self.user(name)
        if not u:
            raise AccountError(f"no user {name}")
        with self.lock, self._db() as c:
            c.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(password), u["id"]))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))   # signs out everywhere
        self.log(u["name"], "password_set")

    def set_role(self, name, role):
        if role not in ROLES:
            raise AccountError(f"role must be one of {', '.join(ROLES)}")
        with self.lock, self._db() as c:
            if not c.execute("UPDATE users SET role = ? WHERE name = ?", (role, name)).rowcount:
                raise AccountError(f"no user {name}")
        self.log(None, "role", f"{name} → {role}")

    def set_disabled(self, name, disabled):
        u = self.user(name)
        if not u:
            raise AccountError(f"no user {name}")
        with self.lock, self._db() as c:
            c.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, u["id"]))
            if disabled:
                c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
                c.execute("DELETE FROM invites WHERE user_id = ?", (u["id"],))
        self.log(None, "disabled" if disabled else "enabled", name)

    def admins(self):
        return [u for u in self.users() if u["role"] == "admin" and not u["disabled"]]

    # --- sign-in
    def login(self, name, password):
        """The user on success, None otherwise. Takes the same time for unknown names."""
        global _DUMMY_HASH
        u = self.user(name or "")
        if not u or not u["pw_hash"] or u["disabled"]:
            _DUMMY_HASH = _DUMMY_HASH or hash_password(secrets.token_hex(8))
            check_password(password or "", _DUMMY_HASH)
            return None
        return u if check_password(password or "", u["pw_hash"]) else None

    def new_session(self, user):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.lock, self._db() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                      (_token_hash(token), user["id"], csrf, now_iso(), time.time() + SESSION_DAYS * 86400))
        self.log(user["name"], "login")
        return token

    def session(self, token):
        if not token:
            return None
        with self._db() as c:
            r = c.execute("SELECT u.id, u.name, u.display, u.role, s.csrf FROM sessions s JOIN users u ON u.id = s.user_id "
                          "WHERE s.token_hash = ? AND s.expires_at > ? AND u.disabled = 0", (_token_hash(token), time.time())).fetchone()
        return dict(r) if r else None

    def end_session(self, token):
        with self.lock, self._db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token or ""),))

    # --- proposals from readers
    def add_proposal(self, target, field, value, note, author):
        with self.lock, self._db() as c:
            if c.execute("SELECT COUNT(*) FROM proposals WHERE status = 'new'").fetchone()[0] >= 2000:
                raise AccountError("too many open proposals")
            return c.execute("INSERT INTO proposals (target, field, value, note, author, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (target, field, value, note, author, now_iso())).lastrowid

    def proposals(self, status=None):
        with self._db() as c:
            q = "SELECT * FROM proposals" + (" WHERE status = ?" if status else "") + " ORDER BY id DESC LIMIT 500"
            return [dict(r) for r in c.execute(q, (status,) if status else ())]

    def proposal(self, pid):
        with self._db() as c:
            r = c.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None

    def close_proposal(self, pid, status, user, note=""):
        with self.lock, self._db() as c:
            c.execute("UPDATE proposals SET status = ?, handled_by = ?, handled_at = ?, handled_note = ? WHERE id = ?",
                      (status, user, now_iso(), note[:500], pid))


# ---------------------------------------------------------------- dates

RU_MONTHS = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
EN_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
GED_MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def _month(word):
    w = word.lower().strip(".")
    for i, m in enumerate(EN_MONTHS):
        if w.startswith(m):
            return i
    for i, m in enumerate(RU_MONTHS):
        if w.startswith(m) and (i != 4 or w in ("мая", "май", "ма")):
            return i
    return None


def _simple(text):
    """One date without qualifiers → ISO or GEDCOM, or None."""
    t = text.strip().rstrip(".").strip()
    t = re.sub(r"\s*(г|года?|г\.)\.?$", "", t).strip()
    if parse_date(t) is not None:
        return t.upper()
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        iso = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
        return iso if parse_date(iso) is not None else None
    m = re.fullmatch(r"(\d{1,2})[./-](\d{4})", t)
    if m:
        iso = f"{m[2]}-{int(m[1]):02d}"
        return iso if parse_date(iso) is not None else None
    m = re.fullmatch(r"(?:(\d{1,2})\s+)?([A-Za-zА-Яа-яЁё.]+)\s+(\d{3,4})", t)
    if m and _month(m[2]) is not None:
        ged = (f"{int(m[1])} " if m[1] else "") + GED_MONTHS[_month(m[2])] + " " + m[3]
        return ged if parse_date(ged) is not None else None
    return None


def normalize_date(text):
    """'около 1899' → 'ABT 1899', 'между 1900 и 1905' → 'BET 1900 AND 1905', '9.10.1899' → '1899-10-09'.
    Returns the text unchanged when it is not understood (validation then reports it)."""
    if text is None:
        return None
    t = " ".join(str(text).split())
    if not t:
        return ""
    low = t.lower()
    m = re.fullmatch(r"(?:между|between|bet)\s+(.+?)\s+(?:и|and)\s+(.+)", low)
    if not m:
        m = re.fullmatch(r"(\d{4})\s*[–—-]\s*(\d{4})", low)
    if m:
        a, b = _simple(m[1]), _simple(m[2])
        if a and b and "-" not in a + b:
            return f"BET {a} AND {b}"
        if a and b:
            return f"BET {a[:4]} AND {b[:4]}"
    for words, code in ((("около", "ок.", "ок", "приблизительно", "примерно", "about", "abt", "circa", "ca.", "c."), "ABT"),
                        (("до", "ранее", "before", "bef"), "BEF"), (("после", "позднее", "after", "aft"), "AFT"),
                        (("вычислено", "calculated", "cal"), "CAL"), (("est", "estimated", "оценочно"), "EST")):
        for w in words:
            if low.startswith(w + " "):
                inner = _simple(t[len(w) + 1:])
                if inner:
                    if "-" in inner:   # GEDCOM qualifiers need a GEDCOM date
                        y, *rest = inner.split("-")
                        inner = " ".join(([str(int(rest[1]))] if len(rest) > 1 else []) + ([GED_MONTHS[int(rest[0]) - 1]] if rest else []) + [y])
                    return f"{code} {inner}"
    return _simple(t) or t


# ---------------------------------------------------------------- store

def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    else:
        out[prefix[:-1]] = obj
    return out


def _short(v, n=300):
    if isinstance(v, (list, dict)):
        v = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and len(v) > n:
        return v[:n] + "…"
    return v


def _clean(obj):
    """Drops empty values that a form leaves behind: None, "", empty events."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = _clean(v)
            if v is None or v == "" or (isinstance(v, dict) and not v):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        return [x for x in (_clean(v) for v in obj) if x is not None and x != ""]
    if isinstance(obj, str):
        return obj.strip()
    return obj


TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяăâîșşțţ",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                     "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya", "a", "a", "i", "s", "s", "t", "t"]))


def safe_filename(name):
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = "".join(TRANSLIT.get(ch, ch) for ch in stem.lower())
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:60] or "file"
    return stem, "." + ext.lower() if ext else ""


class SaveError(ValueError):
    def __init__(self, message, status=422, **extra):
        super().__init__(message)
        self.status, self.extra = status, extra


class Git:
    """History of family_tree.json and sources/ as git commits (if git is installed)."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.ok = shutil.which("git") is not None

    def run(self, *args, check=True, input=None):
        return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=self.folder, check=check, capture_output=True,
                              input=input, timeout=60)

    def ready(self):
        """Makes the folder a git repository on first use. Returns False without git."""
        if not self.ok:
            return False
        r = self.run("rev-parse", "--show-toplevel", check=False)
        if r.returncode == 0:
            return True
        self.run("init", "-q")
        # never commit the build, caches or the state folder (passwords, sessions, comments)
        gi = self.folder / ".gitignore"
        lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
        missing = [x for x in ("_site/", "_site.*/", ".cache/", ".gene-state/", "*.json.tmp") if x not in lines]
        if missing:
            gi.write_text("\n".join(lines + missing) + "\n", encoding="utf-8")
        self.run("add", "-A")
        self.commit("gene-archive", "editor@gene-archive", "Начало истории правок / Start of the edit history", [], all_staged=True)
        return True

    def commit(self, author, email, message, paths, all_staged=False):
        if not self.ok:
            return None
        ident = ["-c", f"user.name={author}", "-c", f"user.email={email}"]
        if not all_staged:
            self.run("add", "--", *paths)
            args = ["commit", "-q", "--allow-empty-message", "-m", message, "--", *paths]
        else:
            args = ["commit", "-q", "--allow-empty", "-m", message]
        r = subprocess.run(["git", *ident, *args], cwd=self.folder, capture_output=True, timeout=60)
        if r.returncode != 0:
            return None
        return self.run("rev-parse", "HEAD").stdout.decode().strip()

    def history(self, limit=100):
        if not self.ok:
            return []
        r = self.run("log", f"-n{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s", "--", "family_tree.json", check=False)
        out = []
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            h, a, d, s = (line.split("\x1f") + ["", "", "", ""])[:4]
            out.append({"commit": h, "author": a, "date": d, "message": s})
        return out

    def show(self, commit, path="family_tree.json"):
        if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
            raise SaveError("bad commit", 400)
        r = self.run("show", f"{commit}:{path}", check=False)
        if r.returncode != 0:
            raise SaveError("no such version", 404)
        return r.stdout


class Store:
    """Reads and writes family_tree.json of one site folder; one writer at a time."""

    def __init__(self, folder, cfg=None, on_change=None):
        from .config import load as load_cfg
        self.folder = Path(folder).resolve()
        self.path = self.folder / "family_tree.json"
        self.cfg = cfg or load_cfg(self.folder)
        self.lang = "ru" if self.cfg.get("content_language") == "ru" else "en"
        self.lock = threading.Lock()
        self.on_change = on_change or (lambda: None)
        self.git = Git(self.folder)
        self.has_git = self.git.ready()

    def t(self, en, ru):
        return ru if self.lang == "ru" else en

    def raw(self):
        return self.path.read_bytes()

    def load(self):
        return json.loads(self.raw())

    def version(self):
        return hashlib.sha256(self.raw()).hexdigest()[:16]

    def _write(self, data):
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _find(lst, key, value):
        for i, r in enumerate(lst):
            if r.get(key) == value:
                return i
        return None

    @staticmethod
    def next_id(lst, prefix):
        nums = [r.get("id", "") for r in lst if re.fullmatch(prefix + r"\d+", str(r.get("id", "")))]
        if not nums:
            return prefix + "1"
        best = max(nums, key=lambda x: int(x[1:]))
        width = len(best) - 1 if best[1:].startswith("0") or any(x[1:].startswith("0") for x in nums) else 0
        return prefix + str(int(best[1:]) + 1).zfill(width)

    def _normalize(self, kind, rec):
        rec = _clean(rec)
        for ev in ("birth", "death", "burial", "marriage"):
            if isinstance(rec.get(ev), dict) and rec[ev].get("date"):
                rec[ev]["date"] = normalize_date(rec[ev]["date"])
        for alt in ("birth_alternatives", "death_alternatives"):
            for ev in rec.get(alt, []) or []:
                if isinstance(ev, dict) and ev.get("date"):
                    ev["date"] = normalize_date(ev["date"])
        if kind == "people":
            rec.setdefault("notes", [])
            rec.setdefault("sex", "U")
            if not rec.get("display_name"):
                rec["display_name"] = " ".join(x for x in (rec.get("given_names"), rec.get("surname")) if x)
            rec.setdefault("given_names", "")
            rec.setdefault("surname", "")
        if kind == "sources":   # the editor attaches only uploaded files
            for k in ("file", "back"):
                if rec.get(k) and not re.fullmatch(r"sources/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*", str(rec[k])):
                    raise SaveError(self.t(f"{k}: only files in sources/", f"{k}: только файлы из sources/"), 422)
        if kind == "families":
            rec.setdefault("partners", [])
            rec.setdefault("children", [])
        return rec

    def _warnings(self, kind, rec, data):
        out = []
        if kind == "people":
            from .privacy import living_people
            if rec["id"] in living_people(data, self.cfg.get("root_person") or data.get("root_person_id"),
                                          self.cfg["privacy"].get("living_years", 100)):
                out.append(self.t("This person is treated as living: only the name will be published.",
                                  "Человек считается живым: на сайте будет только имя."))
        if kind == "families" and (rec.get("partners") or rec.get("children")) and not rec.get("source_ids") \
                and not (rec.get("marriage") or {}).get("source_ids"):
            out.append(self.t("No document for this family link — mark it as probable if it is not proven.",
                              "У связи нет документа — если она не доказана, отметьте детей как «вероятных»."))
        return out

    def _title(self, kind, rec):
        if kind == "people":
            return rec.get("display_name") or rec.get("id")
        if kind == "sources":
            return rec.get("title") or rec.get("id")
        if kind == "places":
            return rec.get("name") or rec.get("slug")
        if kind == "families":
            return " + ".join(rec.get("partners", [])) or rec.get("id")
        return rec.get("title") or rec.get("id")

    def _journal(self, data, kind, key, before, after, user, reason, source_ids):
        """corrections (one line per changed field) and one research_log line."""
        today = datetime.date.today().isoformat()
        ref = {"people": "person_id", "families": "family_id"}.get(kind, "record")
        fb, fa = _flatten(before or {}), _flatten(after or {})
        changed = [k for k in sorted(set(fb) | set(fa)) if fb.get(k) != fa.get(k) and k not in ("id", "slug")]
        if before is None:
            changed_rows = [("*", None, self.t("record created", "запись создана"))]
        elif after is None:
            changed_rows = [("*", self._title(kind, before), self.t("record deleted", "запись удалена"))]
        else:
            changed_rows = [(k, _short(fb.get(k)), _short(fa.get(k))) for k in changed]
        if not changed_rows:
            return []
        for field, prev, cur in changed_rows:
            data.setdefault("corrections", []).append({
                ref: key, "field": field, "previous": prev, "current": cur,
                "reason": reason or self.t("edited online", "правка в редакторе"), "source_ids": source_ids,
                "date": today, "author": user["display"]})
        title = self._title(kind, after or before)
        fields = ", ".join(r[0] for r in changed_rows)[:300]
        data.setdefault("research_log", []).append({
            "date": today,
            "action": self.t(f"Editor: {key} {title}", f"Редактор: {key} {title}"),
            "result": (self.t("changed: ", "изменено: ") + fields) if before is not None and after is not None else changed_rows[0][2],
            "scope": f"{user['display']}" + (f": {reason}" if reason else "")})
        return [r[0] for r in changed_rows]

    def _check(self, before_data, data):
        errs_before = set(validate(before_data, self.folder, self.cfg)[0])
        errs = [e for e in validate(data, self.folder, self.cfg)[0] if e not in errs_before]
        if errs:
            raise SaveError(self.t("The change was not saved: ", "Правка не сохранена: ") + "; ".join(errs[:5]), 422, errors=errs[:20])

    def _commit(self, user, message, extra_paths=()):
        commit = self.git.commit(user["display"], f"{user['name']}@editor.gene-archive", message,
                                 ["family_tree.json", *extra_paths]) if self.has_git else None
        self.on_change()
        return commit

    def save(self, user, kind, record, base=None, reason="", source_ids=None):
        """Creates (base None and no key) or updates a record. `base` is the record as the
        client loaded it: if the stored one differs, someone else changed it — conflict."""
        if kind not in KINDS:
            raise SaveError("unknown kind", 400)
        if not isinstance(record, dict):
            raise SaveError("record must be an object", 400)
        key_field, prefix = KINDS[kind]
        source_ids = [s for s in (source_ids or []) if re.fullmatch(r"S\d+", str(s))]
        with self.lock:
            data = self.load()
            original = copy.deepcopy(data)
            lst = data.setdefault(kind, [])
            rec = self._normalize(kind, record)
            key = rec.get(key_field)
            idx = self._find(lst, key_field, key) if key else None
            if base is None:
                if idx is not None:
                    raise SaveError(self.t(f"{key} already exists", f"{key} уже есть"), 409, current=lst[idx])
                if not key:
                    if not prefix:
                        raise SaveError(self.t("slug is required", "нужен slug"), 422)
                    key = rec[key_field] = self.next_id(lst, prefix)
                rec = {key_field: key, **{k: v for k, v in rec.items() if k != key_field}}
                lst.append(rec)
                before = None
            else:
                bkey = base.get(key_field) if isinstance(base, dict) else None
                bidx = self._find(lst, key_field, bkey) if bkey else None
                if bidx is None:
                    raise SaveError(self.t("The record was deleted by someone else.", "Запись удалил кто-то другой."), 409, current=None)
                if lst[bidx] != base:
                    raise SaveError(self.t("Someone else changed this record. Reload it and repeat your change.",
                                           "Запись изменил кто-то другой. Откройте её заново и повторите правку."), 409, current=lst[bidx])
                if not key:
                    key = rec[key_field] = bkey
                if key != bkey:
                    raise SaveError(self.t("The id of a record cannot be changed.", "Номер записи менять нельзя."), 422)
                before = lst[bidx]
                lst[bidx] = rec
            if before == rec:
                return {"id": key, "version": self.version(), "changed": [], "warnings": [], "commit": None}
            changed = self._journal(data, kind, key, before, rec, user, reason, source_ids)
            self._check(original, data)
            self._write(data)
            what = self.t("record created", "запись создана") if before is None else ", ".join(changed)[:200]
            commit = self._commit(user, f"{key} {self._title(kind, rec)}: {what}"
                                  + (f" — {reason}" if reason else ""))
            return {"id": key, "version": self.version(), "changed": changed, "record": rec,
                    "warnings": self._warnings(kind, rec, data), "commit": commit}

    def delete(self, user, kind, base, reason=""):
        if kind not in KINDS or not isinstance(base, dict):
            raise SaveError("bad request", 400)
        key_field, _ = KINDS[kind]
        with self.lock:
            data = self.load()
            original = copy.deepcopy(data)
            lst = data.get(kind, [])
            idx = self._find(lst, key_field, base.get(key_field))
            if idx is None:
                raise SaveError(self.t("Already deleted.", "Уже удалено."), 409, current=None)
            if lst[idx] != base:
                raise SaveError(self.t("Someone else changed this record.", "Запись изменил кто-то другой."), 409, current=lst[idx])
            before = lst.pop(idx)
            key = before[key_field]
            self._journal(data, kind, key, before, None, user, reason, [])
            self._check(original, data)   # references to the record left anywhere are errors
            self._write(data)
            commit = self._commit(user, self.t(f"{key} deleted", f"{key} удалён(а)") + (f" — {reason}" if reason else ""))
            return {"id": key, "version": self.version(), "commit": commit}

    def upload(self, user, filename, body):
        stem, ext = safe_filename(filename or "")
        magic = UPLOAD_TYPES.get(ext)
        if not magic or not body.startswith(magic):
            raise SaveError(self.t("Only JPEG, PNG, WebP, GIF and PDF files.", "Можно загружать только JPEG, PNG, WebP, GIF и PDF."), 415)
        if len(body) > MAX_UPLOAD:
            raise SaveError(self.t("The file is too large (30 MB at most).", "Файл слишком большой (не больше 30 МБ)."), 413)
        if ext != ".pdf":
            body = clean_image(body, ext)
        ext = ".jpg" if ext == ".jpeg" else ext
        with self.lock:
            folder = self.folder / "sources"
            folder.mkdir(exist_ok=True)
            target, n = folder / f"{stem}{ext}", 2
            while target.exists():
                target, n = folder / f"{stem}-{n}{ext}", n + 1
            target.write_bytes(body)
            os.chmod(target, 0o644)
            rel = f"sources/{target.name}"
            if self.has_git:
                self.git.commit(user["display"], f"{user['name']}@editor.gene-archive", self.t(f"File {rel}", f"Файл {rel}"), [rel])
        return rel

    def history(self):
        return self.git.history() if self.has_git else []

    def restore(self, user, commit):
        """Brings family_tree.json back to its state after `commit` (as a new change)."""
        with self.lock:
            old = json.loads(self.git.show(commit))
            current = self.load()
            self._check(current, old)
            today = datetime.date.today().isoformat()
            old.setdefault("research_log", []).append({
                "date": today, "action": self.t(f"Editor: version {commit[:8]} restored", f"Редактор: возвращена версия {commit[:8]}"),
                "result": self.t("family_tree.json brought back to an earlier state", "family_tree.json возвращён к прежнему состоянию"),
                "scope": user["display"]})
            self._write(old)
            c = self._commit(user, self.t(f"Restored version {commit[:8]}", f"Возвращена версия {commit[:8]}"))
            return {"version": self.version(), "commit": c}


def clean_image(body, ext):
    """Re-saves a photo with Pillow: turns it upright and drops EXIF (camera, GPS). Without
    Pillow the file is kept as it is."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return body
    try:
        with Image.open(io.BytesIO(body)) as im:
            im = ImageOps.exif_transpose(im)
            out = io.BytesIO()
            if ext in (".jpg", ".jpeg"):
                im.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
            elif ext == ".png":
                im.save(out, "PNG", optimize=True)
            elif ext == ".webp":
                im.save(out, "WEBP", quality=92)
            else:
                return body
            return out.getvalue()
    except Exception as e:   # a broken or fake image
        raise SaveError(f"cannot read the image: {e}", 415) from None


class Rebuilder:
    """Rebuilds the site in the background after changes; several quick saves → one build."""

    def __init__(self, folder, out):
        self.folder, self.out = folder, out
        self.cv = threading.Condition()
        self.pending = False
        self.state = {"state": "idle", "finished_at": None, "error": None}
        threading.Thread(target=self._loop, daemon=True).start()

    def request(self):
        with self.cv:
            self.pending = True
            self.state["state"] = "queued" if self.state["state"] != "building" else "building"
            self.cv.notify()

    def _loop(self):
        from .build import build
        while True:
            with self.cv:
                while not self.pending:
                    self.cv.wait()
                self.pending = False
                self.state["state"] = "building"
            time.sleep(1.0)   # let quick consecutive saves pile up
            try:
                build(self.folder, self.out)
                err = None
            except Exception as e:   # the editor shows it; the old site stays online
                err = str(e)[:2000]
            with self.cv:
                self.state.update(state="queued" if self.pending else ("failed" if err else "idle"),
                                  finished_at=now_iso(), error=err)

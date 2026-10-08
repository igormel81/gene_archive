"""Online editor: dates, accounts, saving with checks and conflicts, git history, HTTP API.

    python3 -m unittest tests.test_editor
"""
import http.client
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gene_archive.editor import Accounts, AccountError, SaveError, Store, normalize_date  # noqa: E402

HAS_GIT = shutil.which("git") is not None
USER = {"name": "anna", "display": "Anna"}


def tiny_png():
    raw = b"\x00\xff\x00\x00"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def copy_example(tmp):
    site = Path(tmp, "site")
    shutil.copytree(ROOT / "example", site, ignore=shutil.ignore_patterns("_site*", ".cache", ".git"))
    return site


class Dates(unittest.TestCase):
    def test_normalize(self):
        cases = {"около 1899": "ABT 1899", "ок. 1899 г.": "ABT 1899", "about 1899": "ABT 1899", "до 1950": "BEF 1950",
                 "после 03.1920": "AFT MAR 1920", "между 1900 и 1905": "BET 1900 AND 1905", "1900–1905": "BET 1900 AND 1905",
                 "9.10.1899": "1899-10-09", "9 октября 1899": "9 OCT 1899", "10 мая 1900 г.": "10 MAY 1900",
                 "12 Nov 1950": "12 NOV 1950", "1899-10-09": "1899-10-09", "abt 1899": "ABT 1899",
                 "31.02.1950": "31.02.1950", "перед войной": "перед войной", "": ""}
        for text, want in cases.items():
            self.assertEqual(normalize_date(text), want, text)


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.acc = Accounts(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_invite_password_login(self):
        token = self.acc.add_user("anna", "editor", "Тётя Анна")
        self.assertIsNone(self.acc.login("anna", ""))   # no password before the invitation is used
        with self.assertRaises(AccountError):
            self.acc.accept_invite(token, "short")
        self.acc.accept_invite(token, "long-enough-1")
        with self.assertRaises(AccountError):   # one-time
            self.acc.accept_invite(token, "long-enough-2")
        self.assertEqual(self.acc.login("ANNA", "long-enough-1")["display"], "Тётя Анна")
        self.assertIsNone(self.acc.login("anna", "wrong-password"))
        self.assertIsNone(self.acc.login("nobody", "long-enough-1"))
        self.assertNotIn("long-enough", self.acc.user("anna")["pw_hash"])

    def test_sessions(self):
        self.acc.accept_invite(self.acc.add_user("anna"), "long-enough-1")
        token = self.acc.new_session(self.acc.user("anna"))
        s = self.acc.session(token)
        self.assertEqual((s["name"], s["role"]), ("anna", "editor"))
        self.assertTrue(s["csrf"])
        self.acc.set_password("anna", "another-password")   # signs out everywhere
        self.assertIsNone(self.acc.session(token))
        token = self.acc.new_session(self.acc.user("anna"))
        self.acc.set_disabled("anna", True)
        self.assertIsNone(self.acc.session(token))
        self.assertIsNone(self.acc.login("anna", "another-password"))

    def test_bad_names(self):
        for name in ("a", "Анна", "a b", "x" * 40):
            with self.assertRaises(AccountError):
                self.acc.add_user(name)
        self.acc.add_user("anna")
        with self.assertRaises(AccountError):
            self.acc.add_user("anna")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = copy_example(self.tmp.name)
        (self.site / ".gene-state").mkdir()
        (self.site / ".gene-state" / "editor.db").write_text("secret")
        self.changes = []
        self.store = Store(self.site, on_change=lambda: self.changes.append(1))

    def tearDown(self):
        self.tmp.cleanup()

    def person(self, pid):
        return next(p for p in self.store.load()["people"] if p["id"] == pid)

    def test_update_writes_journal(self):
        base = self.person("I3")
        rec = json.loads(json.dumps(base))
        rec["birth"]["date"] = "около 1858"
        r = self.store.save(USER, "people", rec, base, "по метрике", ["S1"])
        self.assertEqual(r["changed"], ["birth.date"])
        data = self.store.load()
        self.assertEqual(self.person("I3")["birth"]["date"], "ABT 1858")
        c = data["corrections"][-1]
        self.assertEqual((c["person_id"], c["field"], c["previous"], c["current"], c["reason"], c["source_ids"], c["author"]),
                         ("I3", "birth.date", "1858-09-29", "ABT 1858", "по метрике", ["S1"], "Anna"))
        self.assertIn("I3", data["research_log"][-1]["action"])
        self.assertEqual(self.changes, [1])

    def test_conflict(self):
        base = self.person("I3")
        a = json.loads(json.dumps(base))
        a["relation"] = "one"
        self.store.save(USER, "people", a, base)
        b = json.loads(json.dumps(base))
        b["relation"] = "two"
        with self.assertRaises(SaveError) as e:
            self.store.save(USER, "people", b, base)   # base is stale now
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(e.exception.extra["current"]["relation"], "one")
        # another record saved meanwhile is no conflict
        other = self.person("I4")
        o = json.loads(json.dumps(other))
        o["relation"] = "three"
        self.store.save(USER, "people", o, other)

    def test_new_records_get_next_id(self):
        r = self.store.save(USER, "people", {"given_names": "Анна", "surname": "Новак", "sex": "F"})
        self.assertEqual(r["id"], "I47")
        self.assertEqual(self.person("I47")["display_name"], "Анна Новак")
        self.assertTrue(r["warnings"])   # no dates and no family: treated as living
        r = self.store.save(USER, "families", {"partners": ["I47"], "children": []})
        self.assertEqual(r["id"], "F16")
        with self.assertRaises(SaveError):
            self.store.save(USER, "places", {"name": "No slug"})

    def test_new_error_is_refused_old_errors_are_not(self):
        base = self.person("I3")
        bad = json.loads(json.dumps(base))
        bad["birth"]["date"] = "перед войной"
        with self.assertRaises(SaveError) as e:
            self.store.save(USER, "people", bad, base)
        self.assertEqual(e.exception.status, 422)
        self.assertEqual(self.person("I3"), base)
        fam = next(f for f in self.store.load()["families"] if f["id"] == "F1")
        broken = dict(fam, children=fam["children"] + ["I999"])
        with self.assertRaises(SaveError):
            self.store.save(USER, "families", broken, fam)
        # an error already in the file does not block an unrelated edit
        data = self.store.load()
        data["people"][0]["notes"] = ["see S999"]
        self.store._write(data)
        base = self.person("I4")
        ok = dict(base, relation="fixed")
        self.store.save(USER, "people", ok, base)

    def test_delete_checks_references(self):
        base = self.person("I3")   # in families
        with self.assertRaises(SaveError):
            self.store.delete(USER, "people", base)
        r = self.store.save(USER, "people", {"given_names": "X", "surname": "Y"})
        self.store.delete(USER, "people", self.person(r["id"]), "дубликат")
        self.assertFalse(any(p["id"] == r["id"] for p in self.store.load()["people"]))

    def test_files_stay_in_sources(self):
        base = next(x for x in self.store.load()["sources"] if x["id"] == "S1")
        for bad in (".gene-state/editor.db", "sources/../family_tree.json", "/etc/passwd", ".git/config", "site.json"):
            with self.assertRaises(SaveError, msg=bad):
                self.store.save(USER, "sources", dict(base, file=bad), base)

    def test_id_cannot_change(self):
        base = self.person("I3")
        with self.assertRaises(SaveError):
            self.store.save(USER, "people", dict(base, id="I3000"), base)

    def test_upload(self):
        path = self.store.upload(USER, "Фото бабушки.PNG", tiny_png())
        self.assertTrue(path.startswith("sources/foto-babushki") and path.endswith(".png"), path)
        self.assertTrue((self.site / path).is_file())
        self.assertNotEqual(self.store.upload(USER, "Фото бабушки.png", tiny_png()), path)   # no overwriting
        for name, body in (("x.png", b"<?php echo 1;"), ("x.html", b"<html>"), ("../../x.jpg", b"\xff\xd8\xffdata")):
            if name.endswith(".jpg"):
                continue
            with self.assertRaises(SaveError):
                self.store.upload(USER, name, body)
        p = self.store.upload(USER, "../../evil.pdf", b"%PDF-1.4 test")
        self.assertEqual(p, "sources/evil.pdf")

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_git_history_and_restore(self):
        self.assertTrue(self.store.has_git)
        tracked = subprocess.run(["git", "ls-files"], cwd=self.site, capture_output=True, text=True).stdout
        self.assertIn("family_tree.json", tracked)
        self.assertNotIn(".gene-state", tracked)
        base = self.person("I3")
        self.store.save(USER, "people", dict(base, relation="first"), base, "one")
        first = self.store.history()[0]
        self.assertEqual(first["author"], "Anna")
        self.assertIn("I3", first["message"])
        mid = self.person("I3")
        self.store.save(USER, "people", dict(mid, relation="second"), mid, "two")
        self.store.restore({"name": "igor", "display": "Igor"}, first["commit"])
        self.assertEqual(self.person("I3")["relation"], "first")
        self.assertEqual(len(self.store.history()), 4)   # start, one, two, restore
        with self.assertRaises(SaveError):
            self.store.restore(USER, "not-a-commit")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EditorServer(unittest.TestCase):
    """The HTTP side: /edit/ pages, sign-in, CSRF, roles, proposals."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.site = copy_example(cls.tmp.name)
        out = Path(cls.tmp.name, "out")
        out.mkdir()
        (out / "index.html").write_text("<!doctype html><title>Archive</title>", encoding="utf-8")
        state = Path(cls.tmp.name, "state")
        acc = Accounts(state)
        acc.accept_invite(acc.add_user("igor", "admin", "Igor"), "admin-password-1")
        acc.accept_invite(acc.add_user("anna", "editor", "Anna"), "editor-password-1")
        cls.port = free_port()
        env = {**os.environ, "GENE_SITE": str(out), "GENE_STATE_DIR": str(state), "GENE_PIN": "", "GENE_PIN_HASH": "",
               "GENE_PORT": str(cls.port), "GENE_INSECURE_COOKIE": "1", "GENE_EDITOR": str(cls.site)}
        cls.proc = subprocess.Popen([sys.executable, "-m", "gene_archive.server"], cwd=ROOT, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                if cls.request("GET", "/healthz")[0] == 200:
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.tmp.cleanup()

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, dict(r.getheaders()), data

    def login(self, name, password):
        st, h, _ = self.request("POST", "/edit/api/login", {"name": name, "password": password}, {"X-Gene-Client": "1"})
        if st != 200:
            return st, None
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Strict", h["Set-Cookie"])
        me = json.loads(self.request("GET", "/edit/api/me", headers={"Cookie": cookie})[2])
        return st, {"Cookie": cookie, "X-Gene-Client": "1", "X-CSRF-Token": me["csrf"], "Content-Type": "application/json"}

    def test_pages(self):
        st, h, body = self.request("GET", "/edit/")
        self.assertEqual(st, 200)
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertIn(b"editor.js", body)
        self.assertEqual(self.request("GET", "/edit/editor.js")[0], 200)
        self.assertEqual(self.request("GET", "/edit/../server.py")[0], 404)
        self.assertEqual(self.request("GET", "/edit/api/data")[0], 401)
        self.assertEqual(json.loads(self.request("GET", "/api/features")[2]), {"proposals": True})

    def test_login_and_csrf(self):
        self.assertEqual(self.login("igor", "wrong-password")[0], 401)
        st, h = self.login("igor", "admin-password-1")
        self.assertEqual(st, 200)
        st, hh, raw = self.request("GET", "/edit/api/data", headers={"Cookie": h["Cookie"]})
        data = json.loads(raw)
        base = next(p for p in data["people"] if p["id"] == "I4")
        payload = {"kind": "people", "record": dict(base, relation="checked"), "base": base, "reason": "test"}
        no_csrf = {k: v for k, v in h.items() if k != "X-CSRF-Token"}
        self.assertEqual(self.request("POST", "/edit/api/save", payload, no_csrf)[0], 403)
        no_client = {k: v for k, v in h.items() if k != "X-Gene-Client"}
        self.assertEqual(self.request("POST", "/edit/api/save", payload, no_client)[0], 403)
        st, _, raw = self.request("POST", "/edit/api/save", payload, h)
        self.assertEqual(st, 200, raw)
        self.assertEqual(json.loads(raw)["changed"], ["relation"])
        self.assertEqual(self.request("POST", "/edit/api/save", payload, h)[0], 409)   # stale base

    def test_roles(self):
        _, h = self.login("anna", "editor-password-1")
        self.assertEqual(self.request("GET", "/edit/api/users", headers=h)[0], 404)
        self.assertEqual(self.request("POST", "/edit/api/users", {"action": "add", "name": "eve"}, h)[0], 403)
        _, a = self.login("igor", "admin-password-1")
        st, _, raw = self.request("POST", "/edit/api/users", {"action": "add", "name": "eve", "display": "Eve"}, a)
        self.assertEqual(st, 201)
        token = json.loads(raw)["invite"]
        self.assertEqual(json.loads(self.request("GET", "/edit/api/invite?token=" + token)[2])["name"], "eve")
        self.assertEqual(self.request("POST", "/edit/api/users", {"action": "disable", "name": "igor"}, a)[0], 400)   # not yourself

    def test_proposals(self):
        client = {"X-Gene-Client": "1", "Content-Type": "application/json"}
        good = {"target": "I4", "field": "birth.date", "value": "1861", "note": "baptism", "author": "Aunt Anna"}
        self.assertEqual(self.request("POST", "/api/proposals", good, client)[0], 201)
        self.assertEqual(self.request("POST", "/api/proposals", dict(good, field="notes"), client)[0], 400)
        self.assertEqual(self.request("POST", "/api/proposals", dict(good, author=""), client)[0], 400)
        self.assertEqual(self.request("POST", "/api/proposals", good, {"Content-Type": "application/json"})[0], 403)
        _, a = self.login("igor", "admin-password-1")
        items = json.loads(self.request("GET", "/edit/api/proposals", headers=a)[2])
        self.assertTrue(any(p["value"] == "1861" and p["status"] == "new" for p in items))
        pid = next(p["id"] for p in items if p["value"] == "1861")
        self.assertEqual(self.request("POST", "/edit/api/proposal", {"id": pid, "status": "rejected", "note": "no"}, a)[0], 200)


class EditorTranslations(unittest.TestCase):
    def test_every_editor_string_is_translated(self):
        s = (ROOT / "gene_archive/editor_web/editor.js").read_text(encoding="utf-8")
        keys = set(re.findall(r"\bT\('((?:[^'\\]|\\.)*)'\)", s)) - {"—"}
        self.assertGreater(len(keys), 150)
        en = s.split("en: {")[1].split("DICT.ro")[0]
        ro = s.split("DICT.ro = {};")[1]
        self.assertEqual([k for k in keys if f"'{k}':" not in en], [])
        self.assertEqual([k for k in keys if f"['{k}'," not in ro], [])


if __name__ == "__main__":
    unittest.main()

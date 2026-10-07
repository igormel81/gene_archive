"""Comments server: PIN gate, comments, static files. Starts gene_archive.server on a free port.

    python3 -m unittest tests.test_server
"""
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = "4321"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, pin=False, moderate=False):
        self.tmp = tempfile.TemporaryDirectory()
        site = Path(self.tmp.name, "site")
        site.mkdir()
        (site / "index.html").write_text("<!doctype html><title>Archive</title>", encoding="utf-8")
        Path(self.tmp.name, "secret.txt").write_text("do not serve", encoding="utf-8")
        self.port = free_port()
        env = {**os.environ, "GENE_SITE": str(site), "GENE_STATE_DIR": str(Path(self.tmp.name, "state")),
               "GENE_PIN_HASH": hashlib.sha256(PIN.encode()).hexdigest() if pin else "", "GENE_PIN": "",
               "GENE_PORT": str(self.port), "GENE_INSECURE_COOKIE": "1", "GENE_MODERATE": "1" if moderate else ""}
        self.proc = subprocess.Popen([sys.executable, "-m", "gene_archive.server"], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if self.request("GET", "/healthz")[0] == 200:
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the server did not start")

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, dict(r.getheaders()), data

    def post_comment(self, payload, client=True):
        headers = {"Content-Type": "application/json"}
        if client:
            headers["X-Gene-Client"] = "1"
        return self.request("POST", "/api/comments", json.dumps(payload).encode(), headers)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)
        self.tmp.cleanup()


class OpenSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server()

    @classmethod
    def tearDownClass(cls):
        cls.s.stop()

    def test_static(self):
        status, headers, body = self.s.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Archive", body.decode())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_no_path_traversal(self):
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
            self.assertEqual(self.s.request("GET", path)[0], 404, path)

    def test_comment_roundtrip(self):
        status, _, body = self.s.post_comment({"person_id": "I12", "author": "  Aunt   Anna ", "text": "<b>Hello</b>"})
        self.assertEqual(status, 201)
        new = json.loads(body)
        self.assertEqual(new["author"], "Aunt Anna")
        saved = [c for c in json.loads(self.s.request("GET", "/api/comments")[2]) if c["id"] == new["id"]]
        self.assertEqual(saved[0]["text"], "<b>Hello</b>")   # stored as is; the site escapes it

    def test_comment_needs_client_header(self):
        self.assertEqual(self.s.post_comment({"person_id": "I1", "author": "x", "text": "y"}, client=False)[0], 403)

    def test_comment_validation(self):
        self.assertEqual(self.s.post_comment({"person_id": "I1", "author": "", "text": "y"})[0], 400)
        self.assertEqual(self.s.post_comment({"person_id": "../../x", "author": "a", "text": "y"})[0], 400)
        self.assertEqual(self.s.request("POST", "/api/comments", b"{oops", {"X-Gene-Client": "1"})[0], 400)

    def test_body_limits(self):
        big = json.dumps({"person_id": "I1", "author": "x", "text": "я" * 20000}).encode()
        self.assertEqual(self.s.request("POST", "/api/comments", big, {"X-Gene-Client": "1"})[0], 413)
        conn = http.client.HTTPConnection("127.0.0.1", self.s.port, timeout=5)
        conn.putrequest("POST", "/api/comments")
        conn.putheader("Content-Length", "-1")
        conn.putheader("X-Gene-Client", "1")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()

    def test_honeypot_hides_bot_comments(self):
        status, _, body = self.s.post_comment({"person_id": "I1", "author": "bot", "text": "spam", "website": "x"})
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["pending"])
        listed = json.loads(self.s.request("GET", "/api/comments")[2])
        self.assertNotIn("spam", [c["text"] for c in listed])


class ModeratedSite(unittest.TestCase):
    def test_new_comments_wait(self):
        s = Server(moderate=True)
        try:
            body = json.loads(s.post_comment({"person_id": "S3", "author": "a", "text": "who is this?"})[2])
            self.assertTrue(body["pending"])
            self.assertEqual(json.loads(s.request("GET", "/api/comments")[2]), [])
        finally:
            s.stop()


class PinSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server(pin=True)

    @classmethod
    def tearDownClass(cls):
        cls.s.stop()

    def test_closed_without_pin(self):
        body = self.s.request("GET", "/", headers={"Accept-Language": "ru"})[2].decode()
        self.assertIn('name="pin"', body)
        self.assertIn("Семейный архив", body)
        self.assertEqual(self.s.request("GET", "/api/comments")[0], 401)

    def test_unlock(self):
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        self.assertEqual(self.s.request("POST", "/unlock", b"pin=0000", form)[0], 401)
        status, headers, _ = self.s.request("POST", "/unlock", f"pin={PIN}".encode(), form)
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.s.request("GET", "/api/comments", headers={"Cookie": cookie})[0], 200)


if __name__ == "__main__":
    unittest.main()

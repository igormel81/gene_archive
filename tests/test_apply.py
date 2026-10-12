import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from gene_archive import cli
from gene_archive.apply import apply, merge, parse
from test_editor import copy_example


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = copy_example(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def data(self):
        return json.loads((self.site / "family_tree.json").read_text(encoding="utf-8"))

    def test_create_update_log_delete(self):
        r = apply(self.site, [{"op": "save", "kind": "person", "record": {"given_names": "Пётр", "surname": "Тестов", "sex": "M",
                                                                          "birth": {"date": "около 1855"}}, "reason": "test"}],
                  author="Igor")[0]
        self.assertTrue(r["ok"], r)
        pid = r["id"]
        self.assertEqual(r["record"]["birth"]["date"], "ABT 1855")
        self.assertTrue(r["commit"])
        r = apply(self.site, [{"op": "save", "kind": "people", "record": {"id": pid, "birth": {"place_as_recorded": "Сынково"}}}],
                  author="Igor")[0]
        p = next(x for x in self.data()["people"] if x["id"] == pid)
        self.assertEqual(p["birth"], {"date": "ABT 1855", "place_as_recorded": "Сынково"})   # merged, the date kept
        self.assertEqual(r["changed"], ["birth.place_as_recorded"])
        self.assertTrue(any(c.get("person_id") == pid and c["author"] == "Igor" for c in self.data()["corrections"]))
        r = apply(self.site, [{"op": "log", "action": "FamilySearch: Тестов", "result": "ничего"}], author="Igor")[0]
        self.assertEqual(self.data()["research_log"][-1]["result"], "ничего")
        r = apply(self.site, [{"op": "delete", "kind": "people", "id": pid, "reason": "test over"}], author="Igor")[0]
        self.assertTrue(r["ok"], r)
        self.assertFalse(any(x["id"] == pid for x in self.data()["people"]))
        log = subprocess.run(["git", "log", "--format=%an"], cwd=self.site, capture_output=True, text=True).stdout.split()
        self.assertGreaterEqual(log.count("Igor"), 4)

    def test_refused_and_dry_run(self):
        before = (self.site / "family_tree.json").read_bytes()
        r = apply(self.site, [{"op": "save", "kind": "families", "record": {"partners": ["I999"]}}])[0]
        self.assertFalse(r["ok"])
        self.assertIn("I999", r["error"])
        r = apply(self.site, [{"op": "save", "kind": "people", "record": {"id": "I999"}}])[0]
        self.assertEqual(r["status"], 404)
        r = apply(self.site, [{"op": "save", "kind": "people", "record": {"given_names": "X"}}], dry_run=True)[0]
        self.assertTrue(r["ok"] and r["dry_run"])
        self.assertEqual((self.site / "family_tree.json").read_bytes(), before)
        self.assertFalse(apply(self.site, [{"op": "save", "kind": "nonsense", "record": {}}])[0]["ok"])

    def test_cli(self):
        req = json.dumps({"op": "log", "action": "a", "result": "b"})
        sys_stdin = sys.stdin
        sys.stdin = io.StringIO(req)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                rc = cli.main(["apply", str(self.site), "--author", "Igor"])
        finally:
            sys.stdin = sys_stdin
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(buf.getvalue().splitlines()[0])["ok"])

    def test_helpers(self):
        self.assertEqual(merge({"a": {"b": 1, "c": 2}, "d": 1}, {"a": {"b": 3}, "d": None}), {"a": {"b": 3, "c": 2}})
        self.assertEqual(len(parse('{"op": "log"}\n{"op": "log"}')), 2)
        self.assertEqual(len(parse('[{"op": "log"}]')), 1)
        self.assertEqual(parse("  "), [])
        _ = Path


if __name__ == "__main__":
    unittest.main()

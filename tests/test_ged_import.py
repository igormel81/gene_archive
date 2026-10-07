"""Tests for gene_archive.ged_import (GEDCOM -> family_tree.json)."""

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gene_archive.ged_import import convert_date, import_gedcom, main, parse_gedcom

HEAD_55 = """0 HEAD
1 SOUR TEST
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
"""

# A small fictional family covering most mapping rules.
SAMPLE = HEAD_55 + """0 @I1@ INDI
1 NAME John /Harper/
2 SOUR @S1@
3 PAGE p. 4
1 NAME Johnny /Harpur/
1 NICK Jack
1 SEX M
1 BIRT
2 DATE 9 OCT 1899
2 PLAC Millbrook, Kent
2 SOUR @S1@
3 PAGE entry 42
1 DEAT
2 DATE ABT 09 oct 1950
1 BURI
2 PLAC Millbrook churchyard
1 OCCU Blacksmith
2 DATE FROM 1920 TO 1930
2 PLAC Millbrook
1 RESI
2 DATE BET 1931 AND 1935
2 ADDR 12 Mill Lane
3 CONT Millbrook
1 EVEN Won a prize
2 TYPE Fair
1 NOTE John was a quiet man who
2 CONC  loved horses.
2 CONT
2 CONT He built the village forge.
1 NOTE @N1@
1 OBJE
2 FILE C:\\Photos\\john harper.jpg
2 TITL John at the forge
1 FAMS @F1@
1 FAMC @F2@
0 @I2@ INDI
1 NAME Mary /Stone/
2 _MARNM Harper
1 SEX F
1 BIRT
2 DATE OCT 1902
1 DEAT Y
1 FAMS @F1@
0 @I3@ INDI
1 NAME Alice /Harper/
1 SEX F
1 BIRT
2 DATE BET 1925 AND 1927
1 FAMC @F1@
0 @I4@ INDI
1 NAME Tom
1 SEX X
1 FAMC @F1@
2 PEDI adopted
0 @I5@ INDI
1 NAME Peter /Harper/
1 SEX M
1 FAMS @F2@
0 @I6@ INDI
1 NAME Rose /Lane/
1 SEX F
1 FAMS @F3@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 MARR
2 DATE 1924
2 PLAC Millbrook
2 SOUR @S2@
1 SOUR @S2@
0 @F2@ FAM
1 HUSB @I5@
1 CHIL @I1@
0 @F3@ FAM
1 HUSB @I5@
1 WIFE @I6@
1 MARR
1 DIV
2 DATE 1960
0 @S1@ SOUR
1 TITL Millbrook parish register
1 AUTH Rev. A. Clark
1 PUBL Kent record office
1 REPO @R1@
2 CALN P123/4
1 WWW https://example.org/register
1 OBJE
2 FILE scans/register-page.jpg
0 @S2@ SOUR
1 ABBR Marriage certificate
0 @S3@ SOUR
1 NOTE A source without a title
0 @R1@ REPO
1 NAME County Archive
0 @N1@ NOTE A shared note
1 CONC  about John.
0 TRLR
"""


def by_gid(items, gid):
    return next(x for x in items if x.get("gedcom_id") == gid)


class DateTests(unittest.TestCase):
    def test_exact_forms_become_iso(self):
        self.assertEqual(convert_date("9 OCT 1899"), "1899-10-09")
        self.assertEqual(convert_date("09 oct 1899"), "1899-10-09")
        self.assertEqual(convert_date("OCT 1899"), "1899-10")
        self.assertEqual(convert_date("1899"), "1899")
        self.assertEqual(convert_date("1899-10-09"), "1899-10-09")
        self.assertEqual(convert_date("@#DGREGORIAN@ 1 JAN 1900"), "1900-01-01")
        self.assertEqual(convert_date("GREGORIAN 1 JAN 1900"), "1900-01-01")

    def test_qualified_forms_keep_gedcom_form(self):
        self.assertEqual(convert_date("ABT 9 OCT 1899"), "ABT 9 OCT 1899")
        self.assertEqual(convert_date("abt  09 Oct 1899"), "ABT 9 OCT 1899")
        self.assertEqual(convert_date("BEF 1950"), "BEF 1950")
        self.assertEqual(convert_date("AFT 12 NOV 1950"), "AFT 12 NOV 1950")
        self.assertEqual(convert_date("EST 1880"), "EST 1880")
        self.assertEqual(convert_date("CAL 1881"), "CAL 1881")
        self.assertEqual(convert_date("BET 1900 AND 1905"), "BET 1900 AND 1905")
        self.assertEqual(convert_date("BET 01 JAN 1900 AND MAR 1905"), "BET 1 JAN 1900 AND MAR 1905")
        self.assertEqual(convert_date("FROM 1900 TO 1910"), "FROM 1900 TO 1910")
        self.assertEqual(convert_date("FROM 1900"), "FROM 1900")

    def test_unparseable(self):
        for raw in ("before the war", "INT 1899 (about then)", "(sometime)", "1750/51",
                    "@#DJULIAN@ 1 JAN 1700", "JULIAN 1 JAN 1700", "31 FEB 1900", "9 1899",
                    "TO 1900", "BET 1900", "ABT", "1900-13", "15 FOO 1900", "100 B.C."):
            self.assertIsNone(convert_date(raw), raw)


class ParserTests(unittest.TestCase):
    def test_robust_lines(self):
        text = "0 HEAD\r\n\r\n   1 GEDC\r\n2 VERS 5.5\r\n0 @I1@ INDI\r\n1 NAME\r\n2 GIVN Ann\r\n0 TRLR\r\n"
        records = parse_gedcom(text)
        self.assertEqual([r.tag for r in records], ["HEAD", "INDI", "TRLR"])
        self.assertEqual(records[1].xref, "@I1@")
        self.assertEqual(records[1].first("NAME").value, "")
        self.assertEqual(records[1].first("NAME").sub_text("GIVN"), "Ann")


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.warnings = []
        self.data = import_gedcom(SAMPLE, warnings=self.warnings)
        self.people = self.data["people"]

    def test_top_level(self):
        d = self.data
        self.assertEqual(d["schema_version"], "1.0")
        for key in ("places", "place_groups", "place_routes", "research_leads", "corrections"):
            self.assertEqual(d[key], [])
        self.assertEqual(d["surnames"], {})
        log = d["research_log"]
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "GEDCOM import")
        self.assertRegex(log[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("6 people", log[0]["result"])

    def test_renumbering_keeps_gedcom_id(self):
        self.assertEqual([p["id"] for p in self.people], ["I1", "I2", "I3", "I4", "I5", "I6"])
        self.assertEqual([f["gedcom_id"] for f in self.data["families"]], ["@F1@", "@F2@", "@F3@"])
        self.assertEqual([s["id"] for s in self.data["sources"][:3]], ["S1", "S2", "S3"])

    def test_names_and_aliases(self):
        john = by_gid(self.people, "@I1@")
        self.assertEqual(john["given_names"], "John")
        self.assertEqual(john["surname"], "Harper")
        self.assertEqual(john["display_name"], "Harper John")
        self.assertEqual(john["sex"], "M")
        self.assertIn("Johnny Harpur", john["aliases"])
        self.assertIn("John Jack", john["aliases"])
        mary = by_gid(self.people, "@I2@")
        self.assertEqual(mary["aliases"], ["Mary Harper"])
        tom = by_gid(self.people, "@I4@")
        self.assertEqual(tom["display_name"], "Tom")
        self.assertEqual(tom["surname"], "")
        self.assertEqual(tom["sex"], "U")

    def test_events(self):
        john = by_gid(self.people, "@I1@")
        birth = john["birth"]
        self.assertEqual(birth["date"], "1899-10-09")
        self.assertEqual(birth["place_as_recorded"], "Millbrook, Kent")
        self.assertEqual(birth["status"], "documented")
        self.assertIn("S1", birth["source_ids"])
        self.assertIn("S1: entry 42", birth["note"])
        self.assertEqual(john["death"]["date"], "ABT 9 OCT 1950")
        self.assertEqual(john["death"]["status"], "family_report")
        self.assertEqual(john["burial"], {"place_as_recorded": "Millbrook churchyard", "status": "family_report"})
        mary = by_gid(self.people, "@I2@")
        self.assertEqual(mary["birth"]["date"], "1902-10")
        self.assertEqual(mary["death"]["note"], "died (date unknown)")
        self.assertNotIn("date", mary["death"])
        alice = by_gid(self.people, "@I3@")
        self.assertEqual(alice["birth"]["date"], "BET 1925 AND 1927")

    def test_residences(self):
        res = by_gid(self.people, "@I1@")["residences"]
        occu = next(r for r in res if r["place_event_kind"] == "occupation")
        self.assertEqual(occu, {"place": "Millbrook", "date": "FROM 1920 TO 1930",
                                "place_event_kind": "occupation", "note": "Blacksmith"})
        resi = next(r for r in res if r["place_event_kind"] == "residence")
        self.assertEqual(resi["place"], "12 Mill Lane, Millbrook")
        self.assertEqual(resi["date"], "BET 1931 AND 1935")
        even = next(r for r in res if r["place_event_kind"] == "fair")
        self.assertEqual(even["note"], "Won a prize")

    def test_notes_conc_cont_and_shared(self):
        notes = by_gid(self.people, "@I1@")["notes"]
        self.assertEqual(notes[0], "John was a quiet man who loved horses.")
        self.assertEqual(notes[1], "He built the village forge.")
        self.assertEqual(notes[2], "A shared note about John.")
        self.assertTrue(notes[3].startswith("Citations: S1: p. 4"))

    def test_identity_sources_and_media(self):
        john = by_gid(self.people, "@I1@")
        ids = john["identity_source_ids"]
        self.assertIn("S1", ids)
        sources = {s["id"]: s for s in self.data["sources"]}
        photo = next(sources[i] for i in ids if sources[i]["kind"] == "family_photo"
                     and sources[i].get("title") == "John at the forge")
        self.assertEqual(photo["file"], "sources/john harper.jpg")
        self.assertTrue(any("john harper.jpg" in w and "sources/" in w for w in self.warnings))

    def test_sources(self):
        s1, s2, s3 = self.data["sources"][:3]
        self.assertEqual(s1["title"], "Millbrook parish register")
        self.assertEqual(s1["kind"], "imported_source")
        self.assertEqual(s1["locator"], "Kent record office; County Archive, P123/4")
        self.assertIn("Author: Rev. A. Clark", s1["scope"])
        self.assertEqual(s1["url"], "https://example.org/register")
        self.assertEqual(s2["title"], "Marriage certificate")
        self.assertEqual(s3["title"], "Source 3")
        self.assertEqual(s3["scope"], "A source without a title")
        # The scan attached to S1 is a separate source, cited along with S1.
        scan = next(s for s in self.data["sources"] if s.get("file") == "sources/register-page.jpg")
        self.assertIn(scan["id"], by_gid(self.people, "@I1@")["birth"]["source_ids"])

    def test_families(self):
        f1, f2, f3 = self.data["families"]
        self.assertEqual(f1["partners"], ["I1", "I2"])
        self.assertEqual(f1["children"], ["I3"])
        self.assertEqual(f1["adopted_children"], ["I4"])
        self.assertEqual(f1["relation"], "spouses")
        self.assertEqual(f1["marriage"]["date"], "1924")
        self.assertEqual(f1["marriage"]["status"], "documented")
        self.assertEqual(f1["source_ids"], ["S2"])
        self.assertEqual(f2["partners"], ["I5"])
        self.assertEqual(f2["children"], ["I1"])
        self.assertEqual(f2["relation"], "")
        self.assertEqual(f3["relation"], "divorced")
        self.assertIn("Divorce: 1960.", f3["notes"])

    def test_root_default_and_selection(self):
        self.assertEqual(self.data["root_person_id"], "I1")
        self.assertEqual(self.people[0]["relation"], "root person")
        self.assertTrue(all("relation" not in p for p in self.people[1:]))
        for root in ("@I3@", "I3"):
            d = import_gedcom(SAMPLE, root=root)
            self.assertEqual(d["root_person_id"], "I3")
            self.assertEqual(by_gid(d["people"], "@I3@")["relation"], "root person")
        with self.assertRaises(ValueError):
            import_gedcom(SAMPLE, root="@I99@")

    def test_round_trip_references(self):
        assert_references_exist(self, self.data)
        json.dumps(self.data)  # serializable


def assert_references_exist(test, data):
    people = {p["id"] for p in data["people"]}
    sources = {s["id"] for s in data["sources"]}
    test.assertEqual(len(people), len(data["people"]))
    test.assertEqual(len(sources), len(data["sources"]))
    test.assertIn(data["root_person_id"], people)
    for fam in data["families"]:
        for pid in fam["partners"] + fam["children"] + fam["adopted_children"] + fam.get("probable_children", []):
            test.assertIn(pid, people)
        test.assertTrue(set(fam["source_ids"]) <= sources)
    text = json.dumps(data, ensure_ascii=False)
    for sid in re.findall(r'"(S\d+)"', text):
        test.assertIn(sid, sources)
    for person in data["people"]:
        test.assertTrue(set(person.get("identity_source_ids", [])) <= sources)
        for key in ("birth", "death", "burial"):
            test.assertTrue(set(person.get(key, {}).get("source_ids", [])) <= sources)


class WarningTests(unittest.TestCase):
    def test_unparseable_date_goes_to_note(self):
        ged = HEAD_55 + """0 @I1@ INDI
1 NAME Ann /Fisher/
1 BIRT
2 DATE INT 1750/51 (winter)
1 DEAT
2 DATE before the war
0 TRLR
"""
        warnings = []
        d = import_gedcom(ged, warnings=warnings)
        p = d["people"][0]
        self.assertNotIn("date", p["birth"])
        self.assertIn("date as recorded: INT 1750/51 (winter)", p["birth"]["note"])
        self.assertNotIn("date", p["death"])
        self.assertTrue(p["death"]["note"].startswith("died (date unknown)"))
        self.assertIn("before the war", p["death"]["note"])
        self.assertEqual(sum("cannot be expressed" in w for w in warnings), 2)

    def test_unknown_tags_and_broken_refs(self):
        ged = HEAD_55 + """0 @I1@ INDI
1 NAME Ann /Fisher/
1 _FUNNY yes
1 _FUNNY again
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I9@
1 CHIL @I1@
0 TRLR
"""
        warnings = []
        d = import_gedcom(ged, warnings=warnings)
        self.assertTrue(any("INDI._FUNNY ×2" in w for w in warnings))
        self.assertTrue(any("@I9@" in w for w in warnings))
        self.assertEqual(d["families"][0]["partners"], [])
        self.assertEqual(d["families"][0]["children"], ["I1"])
        assert_references_exist(self, d)


class EncodingAndVersionTests(unittest.TestCase):
    GED7 = """0 HEAD
1 GEDC
2 VERS 7.0
0 @I1@ INDI
1 NAME Clara /Reed/
2 TRAN Klara /Rid/
3 LANG ru
1 SEX F
1 BIRT
2 DATE 3 MAR 1911
1 SNOTE @N1@
1 OBJE @O1@
1 FAMC @F1@
2 PEDI FOSTER
0 @I2@ INDI
1 NAME Ben /Reed/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @VOID@
1 CHIL @I1@
0 @N1@ SNOTE First line
1 CONT second line
0 @O1@ OBJE
1 FILE media/clara.jpg
2 FORM image/jpeg
2 TITL Clara aged five
0 TRLR
"""

    def test_gedcom7(self):
        warnings = []
        d = import_gedcom(self.GED7, warnings=warnings)
        clara = d["people"][0]
        self.assertEqual(clara["birth"]["date"], "1911-03-03")
        self.assertIn("Klara Rid", clara["aliases"])
        self.assertEqual(clara["notes"], ["First line second line"])
        sources = {s["id"]: s for s in d["sources"]}
        photo = sources[clara["identity_source_ids"][0]]
        self.assertEqual(photo["file"], "sources/clara.jpg")
        self.assertEqual(photo["title"], "Clara aged five")
        fam = d["families"][0]
        self.assertEqual(fam["partners"], ["I2"])
        self.assertEqual(fam["adopted_children"], ["I1"])
        self.assertIn("GEDCOM 7.0", d["research_log"][0]["result"])
        assert_references_exist(self, d)

    def test_crlf_bom_file(self):
        text = (HEAD_55 + "0 @I1@ INDI\n1 NAME Léa /Moreau/\n1 BIRT\n2 DATE 1 JAN 1900\n0 TRLR\n")
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tree.ged"
            path.write_bytes(raw)
            warnings = []
            d = import_gedcom(path, warnings=warnings)
            self.assertEqual(d["people"][0]["given_names"], "Léa")
            self.assertEqual(d["people"][0]["birth"]["date"], "1900-01-01")
            self.assertEqual(d["research_log"][0]["scope"], "tree.ged")
            self.assertEqual(warnings, [])
            # Path given as a string works too.
            self.assertEqual(import_gedcom(str(path))["people"][0]["surname"], "Moreau")

    def test_cp1251_fallback(self):
        text = HEAD_55.replace("UTF-8", "ANSI") + "0 @I1@ INDI\n1 NAME Иван /Петров/\n0 TRLR\n"
        warnings = []
        d = import_gedcom(text.encode("cp1251"), warnings=warnings)
        self.assertEqual(d["people"][0]["display_name"], "Петров Иван")
        self.assertTrue(any("cp1251" in w for w in warnings))

    def test_latin1_fallback(self):
        text = HEAD_55.replace("UTF-8", "ANSI") + "0 @I1@ INDI\n1 NAME René /Dubois/\n0 TRLR\n"
        warnings = []
        d = import_gedcom(text.encode("latin-1"), warnings=warnings)
        self.assertEqual(d["people"][0]["given_names"], "René")
        self.assertTrue(any("latin-1" in w for w in warnings))


class ValidatorTests(unittest.TestCase):
    def test_imported_data_passes_validation(self):
        try:
            from gene_archive.validate import validate
        except ImportError:
            self.skipTest("gene_archive.validate is not available")
        samples = [SAMPLE, EncodingAndVersionTests.GED7,
                   HEAD_55 + "0 @I1@ INDI\n1 NAME Ann /Fisher/\n1 BIRT\n2 DATE 1750/51\n0 TRLR\n"]
        for ged in samples:
            with tempfile.TemporaryDirectory() as tmp:
                errors, _ = validate(import_gedcom(ged), root=Path(tmp))
                # Media files are copied by the user later; anything else is a real error.
                self.assertEqual([e for e in errors if "not found" not in e], [])


class CliTests(unittest.TestCase):
    def test_cli_writes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            ged = Path(tmp) / "tree.ged"
            ged.write_text(SAMPLE, encoding="utf-8")
            out = Path(tmp) / "family_tree.json"
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = main([str(ged), "-o", str(out), "--root", "@I2@"])
            self.assertEqual(code, 0)
            self.assertIn("6 people", buf.getvalue())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["root_person_id"], "I2")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(main([str(ged), "-o", str(out)]), 1)
            self.assertIn("--force", err.getvalue())
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(ged), "-o", str(out), "--force"]), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["root_person_id"], "I1")


if __name__ == "__main__":
    unittest.main()

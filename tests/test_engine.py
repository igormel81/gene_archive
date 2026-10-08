"""Engine tests: validation, privacy, GEDCOM export, translations and a full build of the example.

    python3 -m unittest discover tests
"""
import copy
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from gene_archive import build, config, ged_export, localize, privacy
from gene_archive.validate import parse_date, validate

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "example"
DATA = json.loads((EXAMPLE / "family_tree.json").read_text(encoding="utf-8"))
CFG = config.load(EXAMPLE)


def errors_after(change):
    data = copy.deepcopy(DATA)
    change(data)
    return validate(data, EXAMPLE, CFG)[0]


class Validate(unittest.TestCase):
    def test_example_is_clean(self):
        errors, warnings = validate(DATA, EXAMPLE, CFG)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_dates(self):
        for value, year in [("1899", 1899), ("1899-10-09", 1899), ("1899-10", 1899), ("ABT 1899", 1899),
                            ("BEF 12 NOV 1950", 1950), ("BET 1900 AND 1905", 1900), ("FROM 1900 TO 1910", 1900),
                            ("9 OCT 1899", 1899), ("29 FEB 1900", None), ("1899-02-30", None), ("12 1900", None),
                            ("before the war", None), ("09.10.1899", None)]:
            self.assertEqual(parse_date(value), year, value)

    def test_catches_broken_data(self):
        cases = {
            "S9999": lambda d: d["people"][3]["notes"].append("see S9999"),
            "I999": lambda d: d["families"][0]["children"].append("I999"),
            "twice": lambda d: d["people"].append(dict(d["people"][0])),
            "nope.jpg": lambda d: d["sources"][0].update(file="sources/nope.jpg"),
            "31.02.1950": lambda d: d["people"][0].update(birth={"date": "31.02.1950"}),
            "nowhere": lambda d: d["place_routes"][0].update(to_place="nowhere"),
            "YYYY-MM-DD": lambda d: d["research_log"].append({"date": "6.10.2026", "action": "a", "result": "r"}),
            "previous": lambda d: d["corrections"].append({"person_id": "I1", "field": "x", "old": 1, "new": 2}),
            "inside the site": lambda d: d["sources"][0].update(file="../etc/passwd"),
            "inside the site folder": lambda d: d["sources"][0].update(file=".gene-state/editor.db"),
            "media[0]: file must": lambda d: d["places"][0].setdefault("media", []).append({"file": "../x.jpg"}),
        }
        for needle, change in cases.items():
            with self.subTest(needle):
                self.assertTrue(any(needle in e for e in errors_after(change)), (needle, errors_after(change)[:3]))

    def test_site_json_references(self):
        cfg = dict(CFG, questions=[{"person": "I999", "text": "?"}])
        self.assertTrue(any("I999" in e for e in validate(DATA, EXAMPLE, cfg)[0]))

    def test_config_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "site.json").write_text('{"title": "x", "langauges": ["en"]}', encoding="utf-8")
            with self.assertRaises(config.ConfigError):
                config.load(tmp)


class Privacy(unittest.TestCase):
    def tree(self, **people):
        """Root I1, parents I2+I3, grandfather I4."""
        base = {"I1": {}, "I2": {}, "I3": {}, "I4": {}}
        base.update(people)
        return {"people": [{"id": k, **v} for k, v in base.items()],
                "families": [{"id": "F1", "partners": ["I2", "I3"], "children": ["I1"]},
                             {"id": "F2", "partners": ["I4"], "children": ["I2"]}]}

    def test_rules(self):
        living = privacy.living_people(self.tree(
            I2={"birth": {"date": "1950"}},
            I3={"birth": {"date": "1952"}, "death": {"date": "2010"}},
            I4={"birth": {"date": "ABT 1880"}}), root="I1")
        self.assertEqual(living, {"I1", "I2"})

    def test_undated_ancestors_stay_public(self):
        self.assertEqual(privacy.living_people(self.tree(), root="I1"), {"I1", "I2", "I3"})

    def test_explicit_override_and_death_without_date(self):
        living = privacy.living_people(self.tree(I1={"living": False}, I2={"death": {"note": "died"}}), root="I1")
        self.assertEqual(living, {"I3"})

    def test_redact(self):
        data, living = build.public_data(CFG, copy.deepcopy(DATA))
        self.assertTrue(living)
        for p in data["people"]:
            if p["id"] in living:
                self.assertLessEqual(set(p), set(privacy.KEEP_FOR_LIVING) | {"notes"}, p["id"])
                self.assertEqual(p["notes"], [])
        for f in data["families"]:
            if set(f.get("partners", [])) & living:
                self.assertNotIn("marriage", f)
        public_ids = {s["id"] for s in data["sources"]}
        for p in data["people"]:
            for sid in re.findall(r"\bS\d+\b", json.dumps(p)):
                self.assertIn(sid, public_ids, p["id"])

    def test_hidden_sources_are_removed_everywhere(self):
        hidden = {s["id"] for s in DATA["sources"] if s.get("hidden")}
        self.assertTrue(hidden)
        data, _ = build.public_data(CFG, copy.deepcopy(DATA))
        text = json.dumps(data)
        for sid in hidden:
            self.assertIsNone(re.search(rf"\b{sid}\b", text), sid)
        self.assertNotRegex(ged_export.build(data), "|".join(rf"@{s}@" for s in hidden))


class Gedcom(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(ged_export.ged_date("1899-10-09"), "9 OCT 1899")
        self.assertEqual(ged_export.ged_date("1899-10"), "OCT 1899")
        self.assertEqual(ged_export.ged_date("BET 1900 AND 1905"), "BET 1900 AND 1905")

    def test_structure(self):
        data, _ = build.public_data(CFG, copy.deepcopy(DATA))
        for version in ged_export.VERSIONS:
            with self.subTest(version):
                ged = ged_export.build(data, "Test", version=version)
                lines = ged.splitlines()
                self.assertEqual(lines[0], "0 HEAD")
                self.assertIn(f"2 VERS {version}", lines[:4])
                self.assertEqual(lines[-1], "0 TRLR")
                for line in lines:
                    self.assertRegex(line, r"^\d+ (@\w+@ )?[A-Z_]+( .*)?$")
                defined = set(re.findall(r"^0 @(\w+)@", ged, re.M))
                used = set(re.findall(r"^[1-9] \w+ @(\w+)@", ged, re.M))
                self.assertEqual(used - defined, set())

    def test_551_line_limits_and_escaping(self):
        long_note = "Ж" * 300 + " @home " + "word " * 80
        data = {"people": [{"id": "I1", "given_names": "Anna", "surname": "Nováková", "display_name": "Nováková Anna",
                            "sex": "F", "notes": [long_note, "line one\nline two"]}],
                "families": [], "sources": []}
        ged = ged_export.build(data, "T", version="5.5.1")
        self.assertLessEqual(max(len(x.encode()) for x in ged.splitlines()), 255)
        self.assertIn("@@home", ged)
        self.assertIn("2 CONT line two", ged)
        self.assertIn("1 SUBM @SUBM1@", ged)
        ged7 = ged_export.build(data, "T", version="7.0")
        self.assertNotIn(" CONC ", ged7)
        self.assertNotIn("@@home", ged7)

    def test_import_export_round_trip(self):
        from gene_archive.ged_import import import_gedcom
        data, _ = build.public_data(CFG, copy.deepcopy(DATA))
        for version in ged_export.VERSIONS:
            with self.subTest(version):
                back = import_gedcom(ged_export.build(data, version=version))
                self.assertEqual(len(back["people"]), len(data["people"]))
                self.assertEqual(len(back["families"]), len(data["families"]))
                self.assertEqual(len(back["sources"]), len(data["sources"]))
                # long notes split with CONC come back whole
                original = {p["id"]: p["notes"] for p in data["people"] if p.get("notes")}
                restored = {p["gedcom_id"].strip("@"): p["notes"] for p in back["people"]}
                name = max(original, key=lambda k: max(len(n) for n in original[k]))
                longest = max(original[name], key=len)
                self.assertTrue(any(longest in n for n in restored[name]), name)


class Translations(unittest.TestCase):
    def test_every_interface_string_is_translated(self):
        app = (ROOT / "gene_archive/engine/web/app.js").read_text(encoding="utf-8")
        keys = {m.group(2) for m in re.finditer(r"\bT\((['\"])((?:\\.|(?!\1).)*)\1\)", app)}
        self.assertGreater(len(keys), 250)
        for lang in ("en", "ro"):
            d = json.loads((ROOT / f"gene_archive/engine/i18n/{lang}.json").read_text(encoding="utf-8"))
            missing = [k for k in keys if k.replace("\\'", "'") not in d]
            self.assertEqual(missing, [], lang)

    def test_markup_is_kept(self):
        tags = re.compile(r"</?[A-Za-z][^>]*>|</?\d+/?>")
        for lang in ("en", "ro"):
            d = json.loads((ROOT / f"gene_archive/engine/i18n/{lang}.json").read_text(encoding="utf-8"))
            for k, v in d.items():
                self.assertEqual(sorted(tags.findall(k)), sorted(tags.findall(v)), (lang, k))


class BuildExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.site = Path(cls.tmp.name, "site")
        shutil.copytree(EXAMPLE, cls.site, ignore=shutil.ignore_patterns("_site*", ".cache"))
        cls.result = build.build(cls.site)
        cls.out = cls.result["out"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_editions(self):
        for prefix, lang, tab in (("", "en", "Tree"), ("ru/", "ru", "Древо"), ("ro/", "ro", "Arbore")):
            html = (self.out / prefix / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'<html lang="{lang}"', html)
            self.assertIn(f'data-view="tree" aria-selected="true">{tab}<', html)
            self.assertTrue((self.out / prefix / "data.json").exists())
            self.assertTrue((self.out / prefix / "people" / "index.html").exists())
            self.assertIn(f"i18n/{lang}.js", html)
        self.assertEqual(self.result["missing_translations"], {"ru": [], "en": [], "ro": []})

    def test_no_russian_interface_left_in_english(self):
        cyr = re.compile("[А-Яа-яЁё]")
        for page in ["index.html", "help.html", "people/index.html", "people/I12.html", "surnames/harper.html"]:
            text = re.sub(r'<div class="language-tools">.*?</details></div>', "", (self.out / page).read_text(encoding="utf-8"), flags=re.S)
            self.assertIsNone(cyr.search(re.sub(r"<script.*?</script>", "", text, flags=re.S)), page)

    def test_paths_in_language_folders(self):
        html = (self.out / "ru" / "index.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'src="\.\./app\.js\?v=')
        self.assertIn('window.GENE_ROOT = "../"', html)
        data = json.loads((self.out / "ru" / "data.json").read_text(encoding="utf-8"))
        files = [s["file"] for s in data["sources"] if s.get("file")]
        self.assertTrue(files and all(f.startswith("../sources/") for f in files))
        for f in files:
            self.assertTrue((self.out / "ru" / f).resolve().exists(), f)
        person = (self.out / "ru" / "people" / "I12.html").read_text(encoding="utf-8")
        self.assertIn('href="../../app.css"', person)

    def test_living_pages_are_hidden(self):
        living = {p["id"] for p in json.loads((self.out / "data.json").read_text())["people"] if p.get("living")}
        self.assertTrue(living)
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        for pid in living:
            page = (self.out / "people" / f"{pid}.html").read_text(encoding="utf-8")
            self.assertIn('content="noindex', page)
            self.assertNotIn(f"people/{pid}.html", sitemap)
            self.assertNotRegex(page, r"<b>(Birth|Death):")

    def test_sitemap_and_robots(self):
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://example.org/family/ru/people/I12.html", sitemap)
        self.assertIn("Disallow: /family/api/", (self.out / "robots.txt").read_text(encoding="utf-8"))

    def test_thumbnails_and_files(self):
        data = json.loads((self.out / "data.json").read_text(encoding="utf-8"))
        for s in data["sources"]:
            for k in ("file", "back", "thumb"):
                if s.get(k):
                    self.assertTrue((self.out / s[k]).is_file(), s[k])

    def test_build_fails_on_errors(self):
        tree = self.site / "family_tree.json"
        data = json.loads(tree.read_text(encoding="utf-8"))
        data["people"][0]["notes"].append("see S9999")
        broken = Path(self.tmp.name, "broken")
        shutil.copytree(self.site, broken, ignore=shutil.ignore_patterns("_site*", ".cache"))
        (broken / "family_tree.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(build.BuildError):
            build.build(broken)


class UrlMapper(unittest.TestCase):
    def test_language_folder(self):
        url = localize.make_url_mapper("ru/", "people/I1.html", "https://example.org/f/")
        self.assertEqual(url("../app.css"), "../../app.css")
        self.assertEqual(url("../sources/a.jpg"), "../../sources/a.jpg")
        self.assertEqual(url("I2.html"), "I2.html")
        self.assertEqual(url("../#/tree"), "../#/tree")
        self.assertEqual(url("https://example.org/f/people/I1.html"), "https://example.org/f/ru/people/I1.html")
        self.assertEqual(url("https://example.org/f/sources/a.jpg"), "https://example.org/f/sources/a.jpg")
        self.assertEqual(url("https://other.org/x"), "https://other.org/x")

    def test_main_language_untouched(self):
        url = localize.make_url_mapper("", "index.html", "")
        self.assertEqual(url("app.js"), "app.js")


if __name__ == "__main__":
    unittest.main()


class ContentTranslation(unittest.TestCase):
    def test_russian_site_with_english_edition(self):
        from gene_archive import cli
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp, "s")
            cli.main(["init", str(site), "--lang", "ru"])
            self.assertIn("Правила доказательности", (site / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual((site / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")
            data = json.loads((site / "family_tree.json").read_text(encoding="utf-8"))
            data["people"][0].update(living=False, notes=["Родился в деревне."])
            (site / "family_tree.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (site / "translations").mkdir()
            (site / "translations" / "en.json").write_text(json.dumps({"Родился в деревне.": "Born in a village."}), encoding="utf-8")
            r = build.build(site)
            ru = json.loads((r["out"] / "data.json").read_text(encoding="utf-8"))
            en = json.loads((r["out"] / "en" / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(ru["people"][0]["notes"], ["Родился в деревне."])
            self.assertEqual(en["people"][0]["notes"], ["Born in a village."])
            self.assertIn('<html lang="ru"', (r["out"] / "index.html").read_text(encoding="utf-8"))
            self.assertIn('<html lang="en"', (r["out"] / "en" / "index.html").read_text(encoding="utf-8"))


class Init(unittest.TestCase):
    def test_init_in_a_folder_with_hidden_files(self):
        from gene_archive import cli
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".git").mkdir()
            Path(tmp, ".cursor").mkdir()
            cli.main(["init", tmp, "--lang", "en"])
            self.assertTrue(Path(tmp, "family_tree.json").exists())
            self.assertIn("Rules of evidence", Path(tmp, "AGENTS.md").read_text(encoding="utf-8"))
            Path(tmp, "notes.txt").write_text("x")
            with self.assertRaises(SystemExit):
                cli.main(["init", tmp])

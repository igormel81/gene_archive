"""Engine tests: validation, privacy, GEDCOM export, translations and a full build of the example.

    python3 -m unittest discover tests
"""
import copy
import json
import re
import shutil
import subprocess
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
            "research_resources[0]": lambda d: d["research_resources"][0].update(source_ids=["S999"]),
            "regular expression": lambda d: d["research_resources"][0].update(log_match="(("),
            "media[0]: file must": lambda d: d["places"][0].setdefault("media", []).append({"file": "../x.jpg"}),
            "parish[0]: church is missing": lambda d: d["places"][0].update(parish=[{"years": "1850"}]),
            "parish[0]: no place": lambda d: d["places"][0].update(parish=[{"church": "X", "place_slugs": ["nowhere"]}]),
            "coverage[0]: no research resource R99": lambda d: d["coverage"][0].update(resource_id="R99"),
            "status 'read'": lambda d: d["coverage"][0]["entries"].append({"year": 1870, "part": "births", "status": "read"}),
            "part 'baptisms'": lambda d: d["coverage"][0]["entries"].append({"year": 1870, "part": "baptisms", "status": "complete"}),
            "coverage[0] entries[0]: no document S999": lambda d: d["coverage"][0]["entries"][0].update(source_ids=["S999"]),
            "estimated date needs a note": lambda d: d["people"][0].update(birth={"date": "ABT 1830", "status": "estimated"}),
        }
        for needle, change in cases.items():
            with self.subTest(needle):
                self.assertTrue(any(needle in e for e in errors_after(change)), (needle, errors_after(change)[:3]))

    def test_coverage_warnings(self):
        data = copy.deepcopy(DATA)
        data["coverage"][0]["entries"].append({"year": 1858, "part": "births", "status": "partial"})
        warnings = validate(data, EXAMPLE, CFG)[1]
        self.assertTrue(any("partial without up_to" in w for w in warnings), warnings)
        self.assertTrue(any("1858 births is listed twice" in w for w in warnings), warnings)

    def test_to_verify(self):
        data = copy.deepcopy(DATA)
        unchecked = [x["id"] for x in data["sources"] if x.get("status") == "to_verify"]
        self.assertTrue(unchecked)   # the example shows the queue
        data["people"][0].setdefault("identity_source_ids", []).append(unchecked[0])
        errors, warnings = validate(data, EXAMPLE, CFG)
        self.assertEqual(errors, [])
        self.assertTrue(any(unchecked[0] in w and "to_verify" in w for w in warnings), warnings)
        data["sources"][0]["status"] = "checked"
        self.assertTrue(any("only to_verify" in e for e in validate(data, EXAMPLE, CFG)[0]))

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

    def test_profiles_for_other_sites(self):
        data, living = build.public_data(CFG, copy.deepcopy(DATA))
        anne = {"id": "I900", "given_names": "Anne", "surname": "Shea", "birth_surname": "Harper", "display_name": "Anne Shea",
                "sex": "F", "birth": {"date": "1850"}, "notes": ["Born in Louisburgh (S1); see S2."]}
        data["people"].append(anne)
        for profile in ("geni", "public"):
            with self.subTest(profile):
                ged = ged_export.build(data, "T", profile=profile, living=living, base_url="https://example.org/f/")
                self.assertRegex(ged, r"0 @I900@ INDI\n1 NAME Anne /Harper/\n2 GIVN Anne\n2 SURN Harper\n2 _MARNM Shea")
                self.assertIn("1 DEAT Y", ged.split("0 @I900@ INDI")[1].split("\n0 ")[0])   # dead, though no date
                self.assertIn("Born in Louisburgh; see.", ged)                               # no S## codes
                self.assertIn("https://example.org/f/#/tree/I900?person=I900", ged)
                self.assertNotIn("Relation:", ged)
                for pid in [p["id"] for p in data["people"] if p.get("placeholder")]:
                    self.assertNotIn(f"@{pid}@", ged)
                defined = set(re.findall(r"^0 @(\w+)@", ged, re.M))
                self.assertEqual(set(re.findall(r"^[1-9] \w+ @(\w+)@", ged, re.M)) - defined, set())
                for pid in living:
                    block = ged.split(f"0 @{pid}@ INDI")[1].split("\n0 ")[0]
                    self.assertNotIn("DEAT", block)
                    given = next(p["given_names"] for p in data["people"] if p["id"] == pid)
                    if profile == "public":
                        self.assertRegex(block, r"^\n1 NAME Living /")
                        self.assertNotIn(given, block)
        archive = ged_export.build(data, "T")
        self.assertIn("1 NAME Anne /Shea/\n2 TYPE married", archive)
        self.assertIn("(S1)", archive)

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
        for lang in ("en", "ro", "uk"):
            d = json.loads((ROOT / f"gene_archive/engine/i18n/{lang}.json").read_text(encoding="utf-8"))
            missing = [k for k in keys if k.replace("\\'", "'") not in d]
            self.assertEqual(missing, [], lang)

    def test_markup_is_kept(self):
        tags = re.compile(r"</?[A-Za-z][^>]*>|</?\d+/?>")
        for lang in ("en", "ro", "uk"):
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

    def test_help_page(self):
        for prefix, words in (("", ("How we are related", "Suggest a correction", "Living people")),
                              ("ru/", ("Как мы связаны", "Предложить исправление", "Ныне живущие")),
                              ("ro/", ("Cum suntem înrudiți", "Propune o corectură", "în viață"))):
            page = (self.out / prefix / "help.html").read_text(encoding="utf-8")
            self.assertGreaterEqual(page.count('class="help-sec'), 12, prefix)
            for w in words:
                self.assertIn(w, page, prefix + w)

    def test_own_help_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp, "site")
            shutil.copytree(EXAMPLE, site, ignore=shutil.ignore_patterns("_site*", ".cache"))
            (site / "content" / "help.html").write_text("<p>Write to Daniel.</p>", encoding="utf-8")
            out = build.build(site)["out"]
            self.assertIn("Write to Daniel.", (out / "help.html").read_text(encoding="utf-8"))

    def test_research_resources(self):
        data = json.loads((self.out / "data.json").read_text(encoding="utf-8"))
        res = {r["id"]: r for r in data["research_resources"]}
        self.assertEqual(res["R2"]["source_ids"], ["S1", "S2"])
        self.assertIn("S16", res["R1"]["source_ids"])   # by kind: family papers
        self.assertTrue(res["R2"]["log"])                 # log_match → research-log entries
        self.assertNotIn("log_match", res["R2"])          # matching rules stay in the build
        cov = {c["resource_id"]: c for c in data["coverage"]}
        self.assertIn({"year": 1858, "part": "births", "film": "NLI microfilm 04220/03", "frames": "32–38", "status": "complete",
                       "source_ids": ["S1"]}, cov["R2"]["entries"])
        index = (self.out / "ru" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="arch-tab-research"', index)
        self.assertIn("Где мы ищем", index)

    def test_share_pages(self):
        """The "Share" button links to s/<key>.html: every key app.js can produce has a page in every edition."""
        data = json.loads((self.out / "data.json").read_text(encoding="utf-8"))
        from gene_archive.privacy import living_people
        living = living_people(json.loads((self.site / "family_tree.json").read_text(encoding="utf-8")))
        self.assertTrue(living)
        keys = ["tree", "people", "archive", "places", "questions", "story", "stats"] + [s["id"] for s in data["sources"]] \
            + [p["id"] for p in data["people"] if not p.get("placeholder")] + ["place-" + pl["slug"] for pl in data["places"]]
        for prefix in ("", "ru/", "ro/"):
            for key in keys:
                self.assertTrue((self.out / prefix / "s" / f"{key}.html").exists(), prefix + key)
        page = (self.out / "ru" / "s" / "tree.html").read_text(encoding="utf-8")
        self.assertIn("<title>Семейное древо</title>", page)
        self.assertIn('content="https://example.org/family/s/img/tree.jpg"', page)
        self.assertIn('content="noindex, follow"', page)
        self.assertIn("location.replace(", page)
        self.assertNotIn("language-tools", page)
        self.assertTrue((self.out / "s" / "img" / "tree.jpg").exists())
        for pid in living:   # no photos of the living in previews
            self.assertNotIn("og:image", (self.out / "s" / f"{pid}.html").read_text(encoding="utf-8"), pid)

    def test_no_russian_interface_left_in_english(self):
        cyr = re.compile("[А-Яа-яЁё]")
        for page in ["index.html", "help.html", "people/index.html", "people/I12.html", "surnames/harper.html",
                     "places/index.html", "places/windber.html"]:
            text = re.sub(r'<div class="language-tools">.*?</details></div>', "", (self.out / page).read_text(encoding="utf-8"), flags=re.S)
            self.assertIsNone(cyr.search(re.sub(r"<script.*?</script>", "", text, flags=re.S)), page)

    def test_surname_page_links(self):   # the app links only to surname pages the build wrote
        pages = json.loads((self.out / "data.json").read_text())["surname_pages"]
        self.assertTrue(pages)
        for key, slug in pages.items():
            self.assertTrue((self.out / "surnames" / f"{slug}.html").exists(), key)

    def test_place_pages(self):
        page = (self.out / "places" / "louisburgh.html").read_text(encoding="utf-8")
        self.assertIn("<h1>Louisburgh</h1>", page)
        self.assertIn('href="../people/I3.html"', page)              # people of the place, linked to their pages
        self.assertIn('href="../#/places?place=louisburgh"', page)   # on to the full page in the app
        self.assertIn('"@type": "Place"', page)
        self.assertIn("Registers are in the books of the church:</b> St. Stephen", (self.out / "places" / "windber.html").read_text(encoding="utf-8"))
        living = {p["id"] for p in json.loads((self.out / "data.json").read_text())["people"] if p.get("living")}
        for slug in [x.name for x in (self.out / "places").glob("*.html")]:
            text = (self.out / "places" / slug).read_text(encoding="utf-8")
            for pid in living:
                self.assertNotIn(f"people/{pid}.html", text, slug)
        self.assertIn('href="../places/pittsburgh.html"', (self.out / "surnames" / "harper.html").read_text(encoding="utf-8"))
        self.assertIn('href="places/"', (self.out / "index.html").read_text(encoding="utf-8"))

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
        self.assertIn("https://example.org/family/places/louisburgh.html", sitemap)
        self.assertIn("https://example.org/family/ro/places/</loc>", sitemap)
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


class PageTranslation(unittest.TestCase):
    """Paragraphs with links and titles of people's pages in a translated edition."""

    def page(self, html, names, catalog, strict=False):
        tr = localize.Translator(names, {localize.digest(k.strip()): v for k, v in catalog.items()}, strict=strict)
        return localize.Page(tr, "en", lambda u: u).render(html), tr

    def test_chunked_paragraph_survives_a_new_name(self):
        html = '<p>Отец — <a data-p="I1">Пётр</a>, кузнец.</p>'
        old = {"Отец —": "Father:", ", кузнец.": ", a smith."}
        # "Пётр" used to be the whole given name; now it has a patronymic, the text of the story stays the same
        for names in (["Пётр"], ["Пётр Иванович", "Иванов Пётр Иванович"]):
            out, tr = self.page(html, names, old)
            self.assertEqual(out, '<p>Father: <a data-p="I1">Пётр</a>, a smith.</p>', names)
            self.assertEqual(tr.missing, set(), names)

    def test_missing_paragraph_is_reported_whole(self):
        html = '<p>Отец — <a href="../people/I1.html">Пётр</a>, кузнец <b>в Красном</b>.</p>'
        out, tr = self.page(html, ["Пётр Иванович"], {"Отец —": "Father:"})
        self.assertEqual(tr.missing, {"Отец — <1>Пётр</1>, кузнец <2>в Красном</2>."})
        self.assertIn("Father: ", out)
        whole = {"Отец — <1>Пётр</1>, кузнец <2>в Красном</2>.": "Father: <1>Pyotr</1>, a smith <2>in Krasnoye</2>."}
        out, tr = self.page(html, [], whole)
        self.assertEqual(out, '<p>Father: <a href="../people/I1.html">Pyotr</a>, a smith <b>in Krasnoye</b>.</p>')
        with self.assertRaises(localize.Missing):
            self.page(html, [], {}, strict=True)

    def test_title_with_a_comma_in_the_name(self):
        name = "Иванова Анна, жена Петра"
        cat = {"Семейный архив": "Family archive", "Красное": "Krasnoye"}
        for title, want in (("Иванова Анна, жена Петра (~1918) — Семейный архив", "Иванова Анна, жена Петра (~1918) — Family archive"),
                            ("Иванова Анна, жена Петра (~1918), Красное — Семейный архив", "Иванова Анна, жена Петра (~1918), Krasnoye — Family archive"),
                            ("Иванова Анна, жена Петра — Семейный архив", "Иванова Анна, жена Петра — Family archive"),
                            ("Петров Иван (1890–1950) — Семейный архив", "Петров Иван (1890–1950) — Family archive")):
            out, tr = self.page(f"<html><head><title>{title}</title></head></html>", [name, "Петров Иван"], cat)
            self.assertIn(f"<title>{want}</title>", out, title)
            self.assertEqual(tr.missing, set(), title)


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



@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SiteSearch(unittest.TestCase):
    """The full-text search of app.js: endings, pre-1918 spelling and Latin letters match, run in node."""

    def test_matching(self):
        app = (ROOT / "gene_archive/engine/web/app.js").read_text(encoding="utf-8")
        block = app[app.index("  var Search = (function () {"):app.index("  function initSearch() {")]
        script = r"""
var D = { people: [
    { id: 'I1', display_name: 'Иван Колодинъ', birth: { date: 'ABT 1885', place_as_recorded: 'с. Сынково Тульской губ.' } },
    { id: 'I2', display_name: 'Józef Kołodziej', notes: ['Moved to Łódź'] }],
  sources: [{ id: 'S1', title: 'Метрика 1885', scope: 'В селе Сынкове крещён Иоаннъ' }], places: [], leads: [], questions: [] };
var SITE = {};
function T(s) { return s; } function el() { return {}; } function fmtDate(x) { return x; } function lifespan() { return ''; }
""" + block + r"""
function ids(q) { return Search.find(q).map(function (d) { return d.key; }).join(','); }
console.log(JSON.stringify([ids('Колодин'), ids('Kolodin'), ids('Сынкове'), ids('Сынково'), ids('kolodziej'), ids('Лодзь'),
  ids('Иоанн'), ids('Сынково Колодин'), ids('нет такого'), Search.fold('Щукин'), Search.fold('Schtschukin')]));
"""
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), ["I1", "I1", "I1,S1", "I1,S1", "I2", "I2", "S1", "I1", "", "shchukin", "shchukin"])

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


    def test_example_from_a_release_archive(self):   # installed from PyPI: the example is downloaded
        import io
        import tarfile
        from unittest import mock
        from gene_archive import cli
        with tempfile.TemporaryDirectory() as tmp:
            arc = Path(tmp, "release.tar.gz")
            with tarfile.open(arc, "w:gz") as tar:
                def add(name, data=b"x", kind=tarfile.REGTYPE):
                    info = tarfile.TarInfo(name)
                    info.type, info.size = kind, (len(data) if kind == tarfile.REGTYPE else 0)
                    if kind == tarfile.SYMTYPE:
                        info.linkname = "/etc/passwd"
                    tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
                add("gene_archive-9.9/README.md")
                add("gene_archive-9.9/example/family_tree.json", b'{"people": []}')
                add("gene_archive-9.9/example/sources/a.jpg")
                add("gene_archive-9.9/example/_site/index.html")
                add("gene_archive-9.9/example/../../evil.txt")
                add("gene_archive-9.9/example/link", kind=tarfile.SYMTYPE)
            dest = Path(tmp, "site")
            with mock.patch.object(cli, "EXAMPLE", Path(tmp, "missing")), \
                    mock.patch.object(cli, "EXAMPLE_URL", arc.as_uri()):
                cli.main(["init", str(dest), "--example"])
            self.assertEqual(Path(dest, "family_tree.json").read_text(), '{"people": []}')
            self.assertTrue(Path(dest, "sources", "a.jpg").exists())
            self.assertTrue(Path(dest, "AGENTS.md").exists())
            for absent in ("_site", "link", "README.md"):
                self.assertFalse(Path(dest, absent).exists(), absent)
            self.assertFalse(Path(tmp, "evil.txt").exists())


class Hints(unittest.TestCase):
    def test_hints(self):
        from gene_archive.hints import hints, text
        data = {
            "root_person_id": "I1",
            "people": [
                {"id": "I1", "display_name": "Child", "sex": "F", "birth": {"date": "1900", "source_ids": ["S1"]}, "notes": []},
                {"id": "I2", "display_name": "Mother", "sex": "F", "birth": {"date": "1890"}, "death": {"date": "1899"}, "notes": ["S1"]},
                {"id": "I3", "display_name": "Stranger", "sex": "U", "notes": []},
            ],
            "families": [{"id": "F1", "partners": ["I2"], "children": ["I1"]}],
            "sources": [{"id": "S1", "title": "Register", "kind": "church_record"}, {"id": "S2", "title": "Lost", "kind": "letter"}],
            "places": [{"slug": "x", "name": "X"}],
        }
        got = {(h["code"], h["id"]) for h in hints(data)}
        for want in [("born_after_mother_death", "I1"), ("parent_young", "I2"), ("unconnected", "I3"), ("no_documents", "I3"),
                     ("no_dates", "I3"), ("no_sex", "I3"), ("event_no_source", "I2"), ("family_no_source", "F1"),
                     ("unused_source", "S2"), ("place_no_coords", "x")]:
            self.assertIn(want, got)
        self.assertNotIn(("unused_source", "S1"), got)
        self.assertEqual(hints(data)[0]["code"], "born_after_mother_death")   # impossible facts first
        self.assertIn("Mother", text(hints(data)[0], "ru"))


class ArchiveStats(unittest.TestCase):
    def test_numbers(self):
        from gene_archive.stats import archive_stats
        data, living = build.public_data(CFG, copy.deepcopy(DATA))
        st = archive_stats(data, [("Harper", [p["id"] for p in data["people"] if p.get("surname") == "Harper"])], living)
        self.assertEqual(st["totals"]["documents"], len(data["sources"]))
        self.assertEqual(st["totals"]["people"], sum(1 for p in data["people"] if not p.get("placeholder")))
        self.assertEqual(sum(n for _, n in st["origins"]), len(data["sources"]))
        origins = dict(st["origins"])
        self.assertEqual(origins["military"], 2)
        self.assertEqual(st["branches"][0]["earliest"], "I1")       # Patrick Harper, about 1832
        self.assertIn("family_word", dict(st["proof"]))
        self.assertEqual(dict(st["centuries"])[19] + dict(st["centuries"]).get(20, 0) + dict(st["centuries"]).get(18, 0),
                         sum(1 for p in data["people"] if not p.get("placeholder") and p["id"] not in living and re.search(r"\d{4}", str((p.get("birth") or {}).get("date", "")))))
        self.assertEqual(sum(n for _, n in st["log_by_day"]), len(data["research_log"]))
        for b in st["branches"]:
            self.assertNotIn(b["earliest"], living)


class EstimateBirth(unittest.TestCase):
    def test_suggestions(self):
        from gene_archive.hints import hints, note
        P = lambda i, b=None, **kw: dict(id=i, display_name=i, sex="M", notes=[], **({"birth": {"date": b}} if b else {}), **kw)   # noqa: E731
        data = {
            "root_person_id": "K1",
            "people": [P("A"), P("B", "1860"), P("K1", "1885"), P("K2", "1883"),     # A: eldest child 1883 → ABT 1856
                       P("S"), P("W", "1890"),                                      # S: wife 1890 → 1882…1898
                       P("X"), P("Y", "1900"), P("Z", "1904"),                      # X: siblings 1900–1904
                       P("C"),                                                      # C: parents 1860 → 1878…1905
                       P("L"), P("M", "1950"),                                      # L: wife 1950 → would be living
                       P("D", birth_alternatives=[{"date": "ABT 1850"}]), P("E", "1880"),
                       P("U", research_status="unlinked_candidate")],
            "families": [{"id": "F1", "partners": ["A", "B"], "children": ["K1", "K2"]},
                         {"id": "F2", "partners": ["S", "W"], "children": []},
                         {"id": "F3", "partners": [], "children": ["X", "Y", "Z"]},
                         {"id": "F4", "partners": ["B"], "children": ["C"]},
                         {"id": "F5", "partners": ["L", "M"], "children": []},
                         {"id": "F6", "partners": ["D", "E"], "children": ["U"]}],
            "sources": [],
        }
        got = {h["id"]: h for h in hints(data) if h["code"] == "estimate_birth"}
        self.assertEqual({k: h["params"]["date"] for k, h in got.items()},
                         {"A": "ABT 1856", "S": "BET 1882 AND 1898", "X": "BET 1892 AND 1912", "C": "BET 1878 AND 1905"})
        self.assertIn("1883", note(got["A"]))
        self.assertIn("старшего ребёнка (1883)", note(got["A"], "ru"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class YearLabels(unittest.TestCase):
    """Years under names in the tree: a range is not shown as one exact year."""

    def test_labels(self):
        app = (ROOT / "gene_archive/engine/web/app.js").read_text(encoding="utf-8")
        block = app[app.index("  // год для подписи"):app.index("  function fmtStamp(")]
        script = "function T(s) { return s; }\n" + block + r"""
console.log(JSON.stringify([year('BET 1917 AND 1944'), year('ABT 1883'), year('EST 1864'), year('1883', 'estimated'), year('1883'),
  year('BEF 1950'), year('9 OCT 1899'), lifespan({ birth: { date: 'BET 1880 AND 1890', status: 'estimated' }, death: { date: '1950' } }),
  lifespan({ birth: { date: 'BET 1917 AND 1944' } })]));
"""
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), ["1917…1944", "ок. 1883", "ок. 1864", "ок. 1883", "1883", "до 1950", "1899",
                                           "1880…1890 – 1950", "р. 1917…1944"])

    def test_static_pages(self):
        from gene_archive import discovery
        pages = discovery.Pages(Path("."), {"people": [], "sources": [], "places": []}, {}, set(), False, False)
        self.assertEqual(pages.years({"birth": {"date": "BET 1880 AND 1890"}, "death": {"date": "9 OCT 1950"}}), "1880…1890–1950")
        self.assertEqual(pages.years({"birth": {"date": "1883", "status": "estimated"}}), "~1883")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Branches(unittest.TestCase):
    """Surname branches of app.js start at the earliest linked ancestor; the start person gets every ancestral line."""

    def run_js(self, people, families, start, code):
        app = (ROOT / "gene_archive/engine/web/app.js").read_text(encoding="utf-8")
        anc = app[app.index("  // предков — 5 поколений"):app.index("  // descendant unit")]
        groups = app[app.index("  function surnameKey(s) {"):app.index("  function renderBranches() {")]
        script = "var D = " + json.dumps({"people": people, "families": families, "start_focus": start, "root_person_id": start}) + r""";
var P = {}, parentFam = {}, SITE = {}, LOCALE = { lang: 'en' }, line = null;
function T(s) { return s; }
D.people.forEach(function (p) { P[p.id] = p; });
D.families.forEach(function (f) { f.children.forEach(function (c) { parentFam[c] = f; }); });
function parentsOf(id) { var f = parentFam[id]; return f ? f.partners.slice() : []; }
function childrenOf(id) { var o = []; D.families.forEach(function (f) { if (f.partners.indexOf(id) >= 0) o = o.concat(f.children); }); return o; }
function yearNum(ev) { var m = /\d{4}/.exec((ev && ev.date) || ''); return m ? +m[0] : null; }
""" + anc + groups + code
        return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)

    def test_branch_skips_possible_relatives(self):
        P = lambda i, sex, sur, **kw: dict(id=i, sex=sex, surname=sur, display_name=f"{i} {sur}", **kw)   # noqa: E731
        people = [P("Y", "M", "Smith", research_status="unlinked_candidate"), P("X", "M", "Smith", birth={"date": "1850"}),
                  P("W", "F", "Smith"), P("A", "M", "Smith"), P("B", "F", "Smith"), P("C", "M", "Smith"),
                  P("Q", "M", "Smith", birth={"date": "1800"})]
        families = [{"id": "F1", "partners": ["Y"], "children": ["X"]}, {"id": "F2", "partners": ["X", "W"], "children": ["A", "B"]},
                    {"id": "F3", "partners": ["A"], "children": ["C"]}, {"id": "F4", "partners": ["Q"], "children": []}]
        out = self.run_js(people, families, "C", "console.log(JSON.stringify(surnameGroups().map(function (g) { return g.focus; })));")
        self.assertEqual(out, ["X"])   # not Q (older, but no line) and not a random descendant

    def test_start_person_gets_every_ancestral_line(self):
        # a chain of 8 generations above the start person; the other person sees 5
        people = [{"id": f"G{i}", "sex": "M", "surname": "Long", "display_name": f"G{i}"} for i in range(9)]
        families = [{"id": f"F{i}", "partners": [f"G{i + 1}"], "children": [f"G{i}"]} for i in range(8)]
        code = r"""
function depth(n) { return n.parents.length ? 1 + Math.max.apply(null, n.parents.map(depth)) : 0; }
function count(n) { return 1 + n.parents.reduce(function (a, p) { return a + count(p); }, 0); }
ancLimit = ANC_ALL; var full = buildAnc('G0', 0);
ancLimit = ANC; var five = buildAnc('G0', 0);
console.log(JSON.stringify([depth(full), depth(five), count(full)]));
"""
        # full: 8 known generations; the missing mothers are drawn as empty places only in the two nearest generations
        self.assertEqual(self.run_js(people, families, "G0", code), [8, 5, 9 + 2])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Kinship(unittest.TestCase):
    """The «How we are related» block of app.js, run in node on a small family."""

    def test_names_and_paths(self):
        app = (ROOT / "gene_archive/engine/web/app.js").read_text(encoding="utf-8")
        block = app[app.index("// ---------- kinship"):app.index("// ---------- kinship (end)")]
        # G1+G2 → P1 (+W), P2; P1+W → A, Asis; P2 → C; C → D; A → K;  H: Asis's half-brother (G1 + other)
        script = block + r"""
var fam = { P1: ['G1', 'G2'], P2: ['G1', 'G2'], A: ['P1', 'W'], Asis: ['P1', 'W'], C: ['P2'], D: ['C'], K: ['A'], H: ['P1', 'X'] };
var sex = { G1: 'M', G2: 'F', P1: 'M', P2: 'F', W: 'F', A: 'F', Asis: 'F', C: 'M', D: 'F', K: 'M', H: 'M', X: 'F', S: 'M' };
var spouses = { A: ['S'], S: ['A'], P1: ['W', 'X'], W: ['P1'], X: ['P1'], G1: ['G2'], G2: ['G1'] };
var g = {
  parents: function (x) { return fam[x] || []; },
  children: function (x) { return Object.keys(fam).filter(function (c) { return fam[c].indexOf(x) >= 0; }); },
  spouses: function (x) { return spouses[x] || []; },
  sex: function (x) { return sex[x]; },
  sameParents: function (a, b) { return String(fam[a]) === String(fam[b]); },
  probable: function (x) { return x === 'D'; }
};
function say(a, b, lang) {
  var r = Kinship.relation(g, a, b);
  if (r.type !== 'blood') return r.type + (r.rel ? ':' + Kinship.name(lang, r.rel.up, r.rel.down, sex[r.via], false) : '');
  return Kinship.name(lang || 'ru', r.up, r.down, sex[b], r.half, r.half ? sex[r.ca] : null) + (r.probable ? '?' : '');
}
console.log(JSON.stringify([say('A', 'G1'), say('A', 'C'), say('A', 'D'), say('D', 'A'), say('A', 'Asis'), say('Asis', 'H'),
  say('K', 'G2'), say('A', 'S'), say('C', 'S', 'ru'), say('S', 'C', 'en'), say('A', 'C', 'en'), say('K', 'D', 'en'),
  Kinship.relation(g, 'A', 'D').path.join('>')]));
"""
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [
            "дед", "двоюродный брат", "двоюродная племянница?", "двоюродная тётя?", "сестра", "единокровный брат",
            "прабабушка", "spouse", "spouse_of:двоюродная сестра", "of_spouse:first cousin", "first cousin",
            "second cousin?", "A>P1>G1>P2>C>D"])
